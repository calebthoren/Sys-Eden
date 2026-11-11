from datetime import UTC, datetime
from pathlib import Path

import pytest

from sys_eden.conversation_models import (
    ConversationRole,
    ReportLinkRole,
    TranscriptState,
)
from sys_eden.conversation_repository import ConversationRepository
from sys_eden.conversation_service import (
    ConversationService,
    TemporaryConversationNotFound,
)
from sys_eden.report_models import Report, ReportState, ReportStatus
from sys_eden.report_repository import ReportRepository
from sys_eden.storage import Database


@pytest.fixture
def conversation_store(tmp_path: Path):
    database = Database(tmp_path / "eden.db")
    database.initialize()
    conversations = ConversationRepository(database)
    reports = ReportRepository(database)
    try:
        yield database, conversations, reports
    finally:
        database.close()


def test_temporary_conversation_never_enters_sqlite_and_promotes_explicitly(
    conversation_store,
):
    _, repository, reports = conversation_store
    service = ConversationService(repository, reports)
    temporary = service.create_temporary(title="Temporary private discussion")
    temporary = service.append(
        temporary.conversation.id,
        role=ConversationRole.USER,
        content="Do not retain this unless I explicitly save it.",
    )

    assert temporary.conversation.id.startswith("TMP-")
    assert repository.list() == []
    restarted_service = ConversationService(repository, reports)
    with pytest.raises(TemporaryConversationNotFound):
        restarted_service.append(
            temporary.conversation.id,
            role=ConversationRole.EDEN,
            content="This active-session transcript no longer exists.",
        )

    saved = service.persist_temporary(temporary.conversation.id)
    assert saved.conversation.id.startswith("CHT-")
    assert repository.get(saved.conversation.id).messages[0].content.startswith("Do not retain")
    with pytest.raises(TemporaryConversationNotFound):
        service.discard_temporary(temporary.conversation.id)


def test_saving_temporary_chat_preserves_its_rolling_context(conversation_store):
    _, repository, reports = conversation_store
    service = ConversationService(repository, reports)
    temporary = service.create_temporary(title="Summarized temporary discussion")
    temporary = service.append(
        temporary.conversation.id,
        role=ConversationRole.USER,
        content="Remember the generated test constraint.",
    )
    service.update_rolling_summary(
        temporary.conversation.id,
        summary="The generated test constraint matters.",
        through_sequence=1,
    )

    saved = service.persist_temporary(temporary.conversation.id)

    assert saved.conversation.rolling_summary == "The generated test constraint matters."
    assert saved.conversation.summary_through_sequence == 1
    assert repository.get(saved.conversation.id).conversation.rolling_summary == (
        "The generated test constraint matters."
    )


def test_deleted_saved_chat_restores_only_during_owning_cli_session(conversation_store):
    _, repository, reports = conversation_store
    service = ConversationService(repository, reports)
    saved = service.create_saved(title="Undoable chat")
    conversation_id = saved.conversation.id
    service.append(conversation_id, role=ConversationRole.USER, content="Keep this text")

    service.delete_for_client(conversation_id, client_id="CLI-A")
    assert repository.get(conversation_id).conversation.transcript_state is TranscriptState.DELETED
    assert repository.get(conversation_id).messages == []
    assert service.restorable_for_client("CLI-B") == []
    with pytest.raises(ValueError, match="no restorable"):
        service.restore_for_client(conversation_id, client_id="CLI-B")

    restored = service.restore_for_client(conversation_id, client_id="CLI-A")
    assert restored.conversation.transcript_state is TranscriptState.FULL
    assert restored.messages[0].content == "Keep this text"
    assert service.restorable_for_client("CLI-A") == []

    service.delete_for_client(conversation_id, client_id="CLI-A")
    service.forget_deleted_for_client("CLI-A")
    with pytest.raises(ValueError, match="no restorable"):
        service.restore_for_client(conversation_id, client_id="CLI-A")
    assert repository.get(conversation_id).conversation.transcript_state is TranscriptState.DELETED


def test_deleted_temporary_chat_restores_only_during_owning_cli_session(conversation_store):
    _, repository, reports = conversation_store
    service = ConversationService(repository, reports)
    temporary = service.create_temporary(title="Private", owner_client_id="CLI-A")
    conversation_id = temporary.conversation.id
    service.append(conversation_id, role=ConversationRole.USER, content="Private text")

    with pytest.raises(TemporaryConversationNotFound):
        service.delete_for_client(conversation_id, client_id="CLI-B")
    service.delete_for_client(conversation_id, client_id="CLI-A")
    with pytest.raises(TemporaryConversationNotFound):
        service.get_current(conversation_id, owner_client_id="CLI-A")
    restored = service.restore_for_client(conversation_id, client_id="CLI-A")
    assert restored.messages[0].content == "Private text"
    assert repository.list() == []


def test_restore_keeps_compact_transcript_and_summary(conversation_store):
    _, repository, reports = conversation_store
    service = ConversationService(repository, reports)
    conversation_id = service.create_saved(title="Compact undo").conversation.id
    for content in ("First", "Middle", "Last"):
        service.append(conversation_id, role=ConversationRole.USER, content=content)
    current = repository.get(conversation_id)
    repository.compact(
        conversation_id,
        expected_revision=current.conversation.revision,
        rolling_summary="A three-message conversation.",
        key_message_sequences={1, 3},
        updated_at=datetime.now(UTC),
    )

    service.delete_for_client(conversation_id, client_id="CLI-A")
    restored = service.restore_for_client(conversation_id, client_id="CLI-A")

    assert restored.conversation.transcript_state is TranscriptState.COMPACT
    assert restored.conversation.rolling_summary == "A three-message conversation."
    assert [message.sequence for message in restored.messages] == [1, 3]


def test_saved_conversation_resumes_with_summary_and_bounded_recent_context(
    conversation_store,
):
    _, repository, reports = conversation_store
    service = ConversationService(repository, reports, recent_message_limit=2)
    conversation = service.create_saved(title="Resumable discussion")
    for role, content in (
        (ConversationRole.USER, "First message"),
        (ConversationRole.EDEN, "First response"),
        (ConversationRole.USER, "Newest message"),
    ):
        conversation = service.append(conversation.conversation.id, role=role, content=content)
    service.update_rolling_summary(
        conversation.conversation.id,
        summary="The user began a resumable test discussion.",
        through_sequence=2,
    )

    after_restart = ConversationService(repository, reports, recent_message_limit=2)
    context = after_restart.context_for_resume(conversation.conversation.id)

    assert context.rolling_summary == "The user began a resumable test discussion."
    assert [message.sequence for message in context.recent_messages] == [2, 3]
    assert repository.get(conversation.conversation.id).conversation.last_resumed_at is not None


def test_current_transcript_access_uses_the_same_boundary_for_temporary_and_saved_chat(
    conversation_store,
):
    _, repository, reports = conversation_store
    service = ConversationService(repository, reports)
    temporary = service.create_temporary(title="Current temporary thread")
    service.append(temporary.conversation.id, role=ConversationRole.USER, content="Temporary")
    saved = service.create_saved(title="Current saved thread")
    service.append(saved.conversation.id, role=ConversationRole.USER, content="Saved")

    assert (
        service.get_current(
            temporary.conversation.id,
            owner_client_id=temporary.conversation.owner_client_id,
        )
        .messages[0]
        .content
        == "Temporary"
    )
    assert service.get_current(saved.conversation.id).messages[0].content == "Saved"

    with pytest.raises(TemporaryConversationNotFound):
        service.get_current(temporary.conversation.id, owner_client_id="another-client")


def test_report_link_survives_transcript_deletion_without_embedding_messages(
    conversation_store,
):
    _, repository, reports = conversation_store
    report = reports.create(
        Report(
            id="rpt-conversation-link",
            title="Conversation link fixture",
            objective="Verify that reports reference rather than embed transcripts.",
        )
    )
    service = ConversationService(repository, reports)
    conversation = service.create_saved(title="Supporting discussion")
    conversation = service.append(
        conversation.conversation.id,
        role=ConversationRole.USER,
        content="A material symptom clarification.",
    )
    link = service.link_saved_conversation(
        conversation.conversation.id,
        report.id,
        role=ReportLinkRole.PRIMARY,
        contribution_summary="The user clarified the material symptom.",
    )

    deleted = repository.delete_transcript(
        conversation.conversation.id,
        expected_revision=conversation.conversation.revision,
        updated_at=datetime.now(UTC),
    )

    assert deleted.transcript_state is TranscriptState.DELETED
    assert repository.get(conversation.conversation.id).messages == []
    assert repository.links_for_report(report.id) == [link]
    assert "material symptom" not in reports.get(report.id).model_dump_json()


def test_temporary_chat_can_contribute_to_report_without_saving_transcript(
    conversation_store,
):
    _, repository, reports = conversation_store
    report = reports.create(
        Report(
            id="rpt-temporary-contribution",
            title="Temporary contribution fixture",
            objective="Retain only explicitly distilled material information.",
        )
    )
    service = ConversationService(repository, reports)
    temporary = service.create_temporary(title="Unsaved source discussion")
    temporary = service.append(
        temporary.conversation.id,
        role=ConversationRole.USER,
        content="Raw private wording that must remain temporary.",
    )

    contribution = service.contribute_temporary_without_saving(
        temporary.conversation.id,
        report.id,
        material_summary="The user supplied a material constraint without retaining the chat.",
    )

    assert contribution.source_temporary_conversation_id == temporary.conversation.id
    assert not contribution.transcript_retained
    assert repository.list() == []
    assert repository.links_for_report(report.id) == []
    assert repository.standalone_contributions_for_report(report.id) == [contribution]


def test_compaction_and_closed_report_review_are_explicit_and_non_destructive(
    conversation_store,
):
    _, repository, reports = conversation_store
    report = reports.create(
        Report(
            id="rpt-closed-retention",
            title="Closed retention fixture",
            objective="Identify reviewable transcript compaction candidates.",
        )
    )
    service = ConversationService(repository, reports)
    aggregate = service.create_saved(title="Full transcript")
    for role, content in (
        (ConversationRole.USER, "Important initial constraint"),
        (ConversationRole.EDEN, "Routine explanation"),
        (ConversationRole.USER, "Important final correction"),
    ):
        aggregate = service.append(aggregate.conversation.id, role=role, content=content)
    service.link_saved_conversation(
        aggregate.conversation.id,
        report.id,
        role=ReportLinkRole.PRIMARY,
        contribution_summary="The transcript contributed the initial constraint and correction.",
    )
    closed_values = report.model_dump(mode="python")
    closed_values.update(
        {
            "state": ReportState.CLOSED,
            "status": ReportStatus.FAILED,
            "activity": None,
            "summary": "The initial constraint and final correction were preserved.",
            "outcome": "The generated retention fixture ended without resolution.",
            "closed_at": datetime.now(UTC),
        }
    )
    reports.update(Report.model_validate(closed_values))

    candidates = service.review_closed_report_retention(
        report.id, unique_evidence_conversation_ids=set()
    )
    assert candidates[0].eligible
    assert (
        repository.get(aggregate.conversation.id).conversation.transcript_state
        is TranscriptState.FULL
    )

    compacted = repository.compact(
        aggregate.conversation.id,
        expected_revision=aggregate.conversation.revision,
        rolling_summary="Initial constraint and final correction were preserved.",
        key_message_sequences={1, 3},
        updated_at=datetime.now(UTC),
    )
    assert compacted.conversation.transcript_state is TranscriptState.COMPACT
    assert [message.sequence for message in compacted.messages] == [1, 3]
    assert all(message.retained_in_compact for message in compacted.messages)
