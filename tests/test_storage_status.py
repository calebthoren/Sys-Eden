from pathlib import Path

from sys_eden.config import StorageSettings
from sys_eden.conversation_models import ConversationRole
from sys_eden.conversation_repository import ConversationRepository
from sys_eden.conversation_service import ConversationService
from sys_eden.report_models import Report
from sys_eden.report_repository import ReportRepository
from sys_eden.storage import Database
from sys_eden.storage_status import StoragePressure, StorageStatusService


def test_storage_status_attributes_shared_budget_without_changing_data(tmp_path: Path):
    database = Database(tmp_path / "eden.db")
    database.initialize()
    reports = ReportRepository(database)
    conversations = ConversationRepository(database)
    service = ConversationService(conversations, reports)
    try:
        reports.create(
            Report(
                id="rpt-storage-fixture",
                title="Storage fixture report",
                objective="Exercise read-only storage attribution.",
            )
        )
        conversation = service.create_saved(title="Storage fixture conversation")
        conversation = service.append(
            conversation.conversation.id,
            role=ConversationRole.USER,
            content="A generated fixture message used only in an isolated test database.",
        )
        conversations.set_pinned(
            conversation.conversation.id,
            expected_revision=conversation.conversation.revision,
            pinned=True,
            updated_at=conversation.conversation.updated_at,
        )
        before = conversations.get(conversation.conversation.id)

        storage = StorageStatusService(database, StorageSettings())
        status = storage.status()
        recommendations = storage.recommendations()
        after = conversations.get(conversation.conversation.id)

        assert status.pressure is StoragePressure.NORMAL
        assert status.counts.reports == 1
        assert status.counts.conversations_full == 1
        assert status.counts.pinned_conversations == 1
        assert status.attribution.structured_reports > 0
        assert status.attribution.conversation_transcripts_full > 0
        assert status.attribution.protected > 0
        assert status.attribution.structured_memory == 0
        assert status.attribution.attachments == 0
        assert not status.changed_data
        assert before == after
        assert recommendations == []
    finally:
        database.close()
