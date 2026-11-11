"""SQLite repository for saved conversations and report links."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime
from typing import Any, cast

from sqlalchemy import text
from sqlalchemy.engine import CursorResult, RowMapping
from sqlalchemy.exc import IntegrityError

from sys_eden.conversation_models import (
    Conversation,
    ConversationAggregate,
    ConversationMessage,
    ConversationPersistence,
    ConversationRole,
    ConversationSummary,
    LinkActor,
    ReportConversationLink,
    ReportLinkRole,
    RetentionCandidate,
    StandaloneConversationContribution,
    TranscriptState,
)
from sys_eden.storage import Database


class ConversationRepositoryError(Exception):
    """Base error for conversation persistence."""


class ConversationNotFound(ConversationRepositoryError):
    pass


class ConversationConflict(ConversationRepositoryError):
    pass


class ConversationRetentionError(ConversationRepositoryError):
    pass


def _timestamp(value: datetime) -> str:
    return value.isoformat()


def _datetime(value: str | datetime) -> datetime:
    return value if isinstance(value, datetime) else datetime.fromisoformat(value)


class ConversationRepository:
    def __init__(self, database: Database):
        self.database = database

    def create(
        self, conversation: Conversation, messages: Sequence[ConversationMessage] = ()
    ) -> ConversationAggregate:
        if conversation.persistence is not ConversationPersistence.SAVED:
            raise ValueError("temporary conversations must not be written to SQLite")
        self._validate_message_set(conversation, messages)
        try:
            with self.database.session() as session:
                session.execute(
                    text(
                        """
                        INSERT INTO conversations (
                            id, schema_version, revision, title, persistence,
                            transcript_state, pinned, created_at, updated_at,
                            last_resumed_at, rolling_summary, summary_through_sequence,
                            retention_policy, last_message_sequence, generated_test_data
                        ) VALUES (
                            :id, :schema_version, :revision, :title, :persistence,
                            :transcript_state, :pinned, :created_at, :updated_at,
                            :last_resumed_at, :rolling_summary, :summary_through_sequence,
                            :retention_policy, :last_message_sequence, :generated_test_data
                        )
                        """
                    ),
                    self._conversation_parameters(conversation),
                )
                for message in messages:
                    self._insert_message(session, message)
        except IntegrityError as error:
            raise ConversationConflict(
                f"Conversation could not be created: {conversation.id}"
            ) from error
        return ConversationAggregate(conversation=conversation, messages=list(messages))

    def get(self, conversation_id: str) -> ConversationAggregate:
        with self.database.session() as session:
            row = (
                session.execute(
                    text("SELECT * FROM conversations WHERE id = :id"),
                    {"id": conversation_id},
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise ConversationNotFound(f"Conversation not found: {conversation_id}")
            messages = session.execute(
                text(
                    "SELECT * FROM conversation_messages "
                    "WHERE conversation_id = :id ORDER BY sequence"
                ),
                {"id": conversation_id},
            ).mappings()
            return ConversationAggregate(
                conversation=self._conversation_from_row(row),
                messages=[self._message_from_row(item) for item in messages],
            )

    def list(self, *, limit: int = 100) -> list[ConversationSummary]:
        if limit < 1 or limit > 1000:
            raise ValueError("conversation list limit must be between 1 and 1000")
        with self.database.session() as session:
            rows = session.execute(
                text(
                    """
                    SELECT c.*, links.report_id AS primary_report_id
                    FROM conversations c
                    LEFT JOIN report_conversation_links links
                      ON links.conversation_id = c.id
                     AND links.relationship_role = 'primary'
                    ORDER BY c.updated_at DESC, c.id
                    LIMIT :limit
                    """
                ),
                {"limit": limit},
            ).mappings()
            return [
                ConversationSummary(
                    id=row["id"],
                    title=row["title"],
                    transcript_state=TranscriptState(row["transcript_state"]),
                    pinned=bool(row["pinned"]),
                    updated_at=_datetime(row["updated_at"]),
                    last_message_sequence=row["last_message_sequence"],
                    primary_report_id=row["primary_report_id"],
                    generated_test_data=bool(row["generated_test_data"]),
                )
                for row in rows
            ]

    def append(
        self,
        conversation_id: str,
        *,
        expected_revision: int,
        role: ConversationRole,
        content: str,
        created_at: datetime,
        metadata: dict[str, str | int | float | bool | None] | None = None,
        generated_test_data: bool = False,
    ) -> ConversationAggregate:
        aggregate = self.get(conversation_id)
        conversation = aggregate.conversation
        if conversation.revision != expected_revision:
            raise ConversationConflict(f"Conversation revision changed: {conversation_id}")
        if conversation.transcript_state is TranscriptState.DELETED:
            raise ConversationRetentionError("deleted conversations cannot be resumed")
        if generated_test_data != conversation.generated_test_data:
            raise ConversationRetentionError(
                "generated test messages cannot be mixed with ordinary conversation data"
            )
        message = ConversationMessage(
            conversation_id=conversation_id,
            sequence=conversation.last_message_sequence + 1,
            role=role,
            content=content,
            created_at=created_at,
            generated_test_data=generated_test_data,
            metadata=metadata or {},
        )
        revised = conversation.model_copy(
            update={
                "revision": conversation.revision + 1,
                "updated_at": created_at,
                "last_message_sequence": message.sequence,
            }
        )
        try:
            with self.database.session() as session:
                self._update_conversation(
                    session, revised, expected_revision=expected_revision
                )
                self._insert_message(session, message)
                session.execute(text("""
                    UPDATE conversation_retention_candidates
                    SET eligible = 0, reason = :reason, reviewed_at = :changed
                    WHERE conversation_id = :conversation
                """), {
                    "reason": "Protected because the transcript changed after its evidence review.",
                    "changed": _timestamp(created_at), "conversation": conversation_id,
                })
        except IntegrityError as error:
            raise ConversationConflict(
                f"Conversation message could not be appended: {conversation_id}"
            ) from error
        return ConversationAggregate(
            conversation=revised, messages=[*aggregate.messages, message]
        )

    def update_summary(
        self,
        conversation_id: str,
        *,
        expected_revision: int,
        summary: str,
        through_sequence: int,
        updated_at: datetime,
    ) -> Conversation:
        conversation = self.get(conversation_id).conversation
        if conversation.transcript_state is TranscriptState.DELETED:
            raise ConversationRetentionError("deleted transcripts cannot be summarized")
        if through_sequence > conversation.last_message_sequence:
            raise ValueError("summary sequence exceeds stored conversation history")
        revised = conversation.model_copy(
            update={
                "revision": conversation.revision + 1,
                "rolling_summary": summary,
                "summary_through_sequence": through_sequence,
                "updated_at": updated_at,
            }
        )
        with self.database.session() as session:
            self._update_conversation(session, revised, expected_revision=expected_revision)
        return revised

    def touch_resumed(
        self, conversation_id: str, *, expected_revision: int, resumed_at: datetime
    ) -> Conversation:
        conversation = self.get(conversation_id).conversation
        if conversation.transcript_state is TranscriptState.DELETED:
            raise ConversationRetentionError("deleted conversations cannot be resumed")
        revised = conversation.model_copy(
            update={
                "revision": conversation.revision + 1,
                "last_resumed_at": resumed_at,
                "updated_at": resumed_at,
            }
        )
        with self.database.session() as session:
            self._update_conversation(session, revised, expected_revision=expected_revision)
        return revised

    def set_pinned(
        self,
        conversation_id: str,
        *,
        expected_revision: int,
        pinned: bool,
        updated_at: datetime,
    ) -> Conversation:
        conversation = self.get(conversation_id).conversation
        if conversation.transcript_state is TranscriptState.DELETED and pinned:
            raise ConversationRetentionError("deleted conversations cannot be pinned")
        revised = conversation.model_copy(
            update={
                "revision": conversation.revision + 1,
                "pinned": pinned,
                "updated_at": updated_at,
            }
        )
        with self.database.session() as session:
            self._update_conversation(session, revised, expected_revision=expected_revision)
        return revised

    def compact(
        self,
        conversation_id: str,
        *,
        expected_revision: int,
        rolling_summary: str,
        key_message_sequences: set[int],
        updated_at: datetime,
    ) -> ConversationAggregate:
        aggregate = self.get(conversation_id)
        conversation = aggregate.conversation
        if conversation.transcript_state is not TranscriptState.FULL:
            raise ConversationRetentionError("only full transcripts can be compacted")
        available = {message.sequence for message in aggregate.messages}
        if not key_message_sequences.issubset(available):
            raise ValueError("key message selection contains an unknown sequence")
        revised = conversation.model_copy(
            update={
                "revision": conversation.revision + 1,
                "transcript_state": TranscriptState.COMPACT,
                "rolling_summary": rolling_summary,
                "summary_through_sequence": conversation.last_message_sequence,
                "updated_at": updated_at,
            }
        )
        with self.database.session() as session:
            self._update_conversation(session, revised, expected_revision=expected_revision)
            if key_message_sequences:
                parameters = {
                    "conversation_id": conversation_id,
                    **{
                        f"sequence_{index}": sequence
                        for index, sequence in enumerate(sorted(key_message_sequences))
                    },
                }
                placeholders = ", ".join(
                    f":sequence_{index}" for index in range(len(key_message_sequences))
                )
                session.execute(
                    text(
                        "DELETE FROM conversation_messages WHERE conversation_id = "
                        f":conversation_id AND sequence NOT IN ({placeholders})"
                    ),
                    parameters,
                )
                session.execute(
                    text(
                        "UPDATE conversation_messages SET retained_in_compact = 1 "
                        "WHERE conversation_id = :conversation_id"
                    ),
                    {"conversation_id": conversation_id},
                )
            else:
                session.execute(
                    text(
                        "DELETE FROM conversation_messages WHERE conversation_id = :id"
                    ),
                    {"id": conversation_id},
                )
        return self.get(conversation_id)

    def delete_transcript(
        self, conversation_id: str, *, expected_revision: int, updated_at: datetime
    ) -> Conversation:
        conversation = self.get(conversation_id).conversation
        if conversation.transcript_state is TranscriptState.DELETED:
            return conversation
        revised = conversation.model_copy(
            update={
                "revision": conversation.revision + 1,
                "transcript_state": TranscriptState.DELETED,
                "pinned": False,
                "rolling_summary": None,
                "summary_through_sequence": 0,
                "updated_at": updated_at,
            }
        )
        with self.database.session() as session:
            self._update_conversation(session, revised, expected_revision=expected_revision)
            session.execute(
                text("DELETE FROM conversation_messages WHERE conversation_id = :id"),
                {"id": conversation_id},
            )
        return revised

    def restore_transcript(
        self, original: ConversationAggregate, *, updated_at: datetime
    ) -> ConversationAggregate:
        """Restore a session-held snapshot only while its durable tombstone is unchanged."""
        conversation_id = original.conversation.id
        current = self.get(conversation_id).conversation
        if current.transcript_state is not TranscriptState.DELETED:
            raise ConversationRetentionError("only a deleted transcript can be restored")
        if current.revision != original.conversation.revision + 1:
            raise ConversationConflict("deleted conversation changed since this session's deletion")
        revised = original.conversation.model_copy(
            update={"revision": current.revision + 1, "updated_at": updated_at}
        )
        try:
            with self.database.session() as session:
                self._update_conversation(session, revised, expected_revision=current.revision)
                for message in original.messages:
                    self._insert_message(session, message)
        except IntegrityError as error:
            raise ConversationConflict(
                f"Conversation transcript could not be restored: {conversation_id}"
            ) from error
        return self.get(conversation_id)

    def link_report(
        self, link: ReportConversationLink, *, replace_primary: bool = False
    ) -> ReportConversationLink:
        try:
            with self.database.session() as session:
                if replace_primary and link.role is ReportLinkRole.PRIMARY:
                    session.execute(text("""
                        DELETE FROM report_conversation_links
                        WHERE conversation_id = :conversation
                            AND relationship_role = 'primary' AND report_id != :report
                    """), {"conversation": link.conversation_id, "report": link.report_id})
                session.execute(
                    text(
                        """
                        INSERT INTO report_conversation_links (
                            report_id, conversation_id, relationship_role,
                            contribution_summary, contribution_through_sequence,
                            contribution_updated_at, linked_at, linked_by
                        ) VALUES (
                            :report_id, :conversation_id, :relationship_role,
                            :contribution_summary, :contribution_through_sequence,
                            :contribution_updated_at, :linked_at, :linked_by
                        )
                        ON CONFLICT(report_id, conversation_id) DO UPDATE SET
                            relationship_role = excluded.relationship_role
                        """
                    ),
                    {
                        "report_id": link.report_id,
                        "conversation_id": link.conversation_id,
                        "relationship_role": link.role.value,
                        "contribution_summary": link.contribution_summary,
                        "contribution_through_sequence": link.contribution_through_sequence,
                        "contribution_updated_at": (
                            _timestamp(link.contribution_updated_at) if link.contribution_updated_at else None
                        ),
                        "linked_at": _timestamp(link.linked_at),
                        "linked_by": link.linked_by.value,
                    },
                )
        except IntegrityError as error:
            raise ConversationConflict(
                "Report link is invalid, duplicated, or conflicts with the existing primary report"
            ) from error
        return link

    def unlink_report(self, report_id: str, conversation_id: str) -> None:
        with self.database.session() as session:
            session.execute(
                text(
                    "DELETE FROM report_conversation_links "
                    "WHERE report_id = :report_id AND conversation_id = :conversation_id"
                ),
                {"report_id": report_id, "conversation_id": conversation_id},
            )

    def update_contribution(
        self, link: ReportConversationLink, *, summary: str | None,
        through_sequence: int, updated_at: datetime,
    ) -> bool:
        """Do not replace a newer contribution or recreate an unlinked relationship."""
        with self.database.session() as session:
            result = session.execute(text("""
                UPDATE report_conversation_links
                SET contribution_summary = :summary,
                    contribution_through_sequence = :sequence,
                    contribution_updated_at = :updated
                WHERE report_id = :report AND conversation_id = :conversation
                    AND contribution_through_sequence = :previous
                    AND (SELECT last_message_sequence FROM conversations
                         WHERE id = :conversation) = :sequence
            """), {
                "summary": summary, "sequence": through_sequence,
                "updated": _timestamp(updated_at), "report": link.report_id,
                "conversation": link.conversation_id,
                "previous": link.contribution_through_sequence,
            })
            return cast(CursorResult[Any], result).rowcount == 1

    def links_for_conversation(self, conversation_id: str) -> list[ReportConversationLink]:
        return self._links("conversation_id", conversation_id)

    def links_for_report(self, report_id: str) -> list[ReportConversationLink]:
        return self._links("report_id", report_id)

    def record_retention_candidate(self, candidate: RetentionCandidate) -> None:
        with self.database.session() as session:
            session.execute(
                text(
                    """
                    INSERT INTO conversation_retention_candidates (
                        report_id, conversation_id, eligible, reason, reviewed_at
                    ) VALUES (
                        :report_id, :conversation_id, :eligible, :reason, :reviewed_at
                    )
                    ON CONFLICT(report_id, conversation_id) DO UPDATE SET
                        eligible = excluded.eligible,
                        reason = excluded.reason,
                        reviewed_at = excluded.reviewed_at
                    """
                ),
                {
                    "report_id": candidate.report_id,
                    "conversation_id": candidate.conversation_id,
                    "eligible": candidate.eligible,
                    "reason": candidate.reason,
                    "reviewed_at": _timestamp(candidate.reviewed_at),
                },
            )

    def retention_candidates(self, report_id: str) -> list[RetentionCandidate]:
        with self.database.session() as session:
            rows = session.execute(
                text(
                    "SELECT * FROM conversation_retention_candidates "
                    "WHERE report_id = :report_id ORDER BY conversation_id"
                ),
                {"report_id": report_id},
            ).mappings()
            return [
                RetentionCandidate(
                    report_id=row["report_id"],
                    conversation_id=row["conversation_id"],
                    eligible=bool(row["eligible"]),
                    reason=row["reason"],
                    reviewed_at=_datetime(row["reviewed_at"]),
                )
                for row in rows
            ]

    def add_standalone_contribution(
        self, contribution: StandaloneConversationContribution
    ) -> StandaloneConversationContribution:
        try:
            with self.database.session() as session:
                session.execute(
                    text(
                        """
                        INSERT INTO standalone_conversation_contributions (
                            id, report_id, source_temporary_conversation_id, summary,
                            created_at, transcript_retained
                        ) VALUES (
                            :id, :report_id, :source_temporary_conversation_id, :summary,
                            :created_at, :transcript_retained
                        )
                        """
                    ),
                    {
                        "id": contribution.id,
                        "report_id": contribution.report_id,
                        "source_temporary_conversation_id": (
                            contribution.source_temporary_conversation_id
                        ),
                        "summary": contribution.summary,
                        "created_at": _timestamp(contribution.created_at),
                        "transcript_retained": contribution.transcript_retained,
                    },
                )
        except IntegrityError as error:
            raise ConversationConflict("Standalone report contribution is invalid") from error
        return contribution

    def standalone_contributions_for_report(
        self, report_id: str
    ) -> list[StandaloneConversationContribution]:
        with self.database.session() as session:
            rows = session.execute(
                text(
                    "SELECT * FROM standalone_conversation_contributions "
                    "WHERE report_id = :report_id ORDER BY created_at, id"
                ),
                {"report_id": report_id},
            ).mappings()
            return [
                StandaloneConversationContribution(
                    id=row["id"],
                    report_id=row["report_id"],
                    source_temporary_conversation_id=row[
                        "source_temporary_conversation_id"
                    ],
                    summary=row["summary"],
                    created_at=_datetime(row["created_at"]),
                    transcript_retained=bool(row["transcript_retained"]),
                )
                for row in rows
            ]

    def _links(self, field: str, value: str) -> list[ReportConversationLink]:
        if field not in {"report_id", "conversation_id"}:
            raise ValueError("unsupported report-link query")
        with self.database.session() as session:
            rows = session.execute(
                text(
                    "SELECT * FROM report_conversation_links "
                    f"WHERE {field} = :value ORDER BY linked_at, report_id, conversation_id"
                ),
                {"value": value},
            ).mappings()
            return [
                ReportConversationLink(
                    report_id=row["report_id"],
                    conversation_id=row["conversation_id"],
                    role=ReportLinkRole(row["relationship_role"]),
                    contribution_summary=row["contribution_summary"],
                    contribution_through_sequence=row["contribution_through_sequence"],
                    contribution_updated_at=(
                        _datetime(row["contribution_updated_at"])
                        if row["contribution_updated_at"] else None
                    ),
                    linked_at=_datetime(row["linked_at"]),
                    linked_by=LinkActor(row["linked_by"]),
                )
                for row in rows
            ]

    @staticmethod
    def _conversation_parameters(conversation: Conversation) -> dict[str, object]:
        return {
            "id": conversation.id,
            "schema_version": conversation.schema_version,
            "revision": conversation.revision,
            "title": conversation.title,
            "persistence": conversation.persistence.value,
            "transcript_state": conversation.transcript_state.value,
            "pinned": conversation.pinned,
            "created_at": _timestamp(conversation.created_at),
            "updated_at": _timestamp(conversation.updated_at),
            "last_resumed_at": (
                _timestamp(conversation.last_resumed_at)
                if conversation.last_resumed_at
                else None
            ),
            "rolling_summary": conversation.rolling_summary,
            "summary_through_sequence": conversation.summary_through_sequence,
            "retention_policy": conversation.retention_policy,
            "last_message_sequence": conversation.last_message_sequence,
            "generated_test_data": conversation.generated_test_data,
        }

    @staticmethod
    def _insert_message(session: Any, message: ConversationMessage) -> None:
        session.execute(
            text(
                """
                INSERT INTO conversation_messages (
                    conversation_id, sequence, role, content, created_at,
                    retained_in_compact, generated_test_data, metadata_json
                ) VALUES (
                    :conversation_id, :sequence, :role, :content, :created_at,
                    :retained_in_compact, :generated_test_data, :metadata_json
                )
                """
            ),
            {
                "conversation_id": message.conversation_id,
                "sequence": message.sequence,
                "role": message.role.value,
                "content": message.content,
                "created_at": _timestamp(message.created_at),
                "retained_in_compact": message.retained_in_compact,
                "generated_test_data": message.generated_test_data,
                "metadata_json": json.dumps(message.metadata, sort_keys=True),
            },
        )

    @classmethod
    def _update_conversation(
        cls, session: Any, conversation: Conversation, *, expected_revision: int
    ) -> None:
        result = cast(
            CursorResult[Any],
            session.execute(
                text(
                    """
                    UPDATE conversations SET
                        schema_version = :schema_version,
                        revision = :revision,
                        title = :title,
                        persistence = :persistence,
                        transcript_state = :transcript_state,
                        pinned = :pinned,
                        updated_at = :updated_at,
                        last_resumed_at = :last_resumed_at,
                        rolling_summary = :rolling_summary,
                        summary_through_sequence = :summary_through_sequence,
                        retention_policy = :retention_policy,
                        last_message_sequence = :last_message_sequence,
                        generated_test_data = :generated_test_data
                    WHERE id = :id AND revision = :expected_revision
                    """
                ),
                {
                    **cls._conversation_parameters(conversation),
                    "expected_revision": expected_revision,
                },
            ),
        )
        if result.rowcount != 1:
            raise ConversationConflict(
                f"Conversation revision changed or conversation is missing: {conversation.id}"
            )

    @staticmethod
    def _conversation_from_row(row: RowMapping) -> Conversation:
        return Conversation(
            id=row["id"],
            schema_version=row["schema_version"],
            revision=row["revision"],
            title=row["title"],
            persistence=ConversationPersistence(row["persistence"]),
            transcript_state=TranscriptState(row["transcript_state"]),
            pinned=bool(row["pinned"]),
            created_at=_datetime(row["created_at"]),
            updated_at=_datetime(row["updated_at"]),
            last_resumed_at=(
                _datetime(row["last_resumed_at"]) if row["last_resumed_at"] else None
            ),
            rolling_summary=row["rolling_summary"],
            summary_through_sequence=row["summary_through_sequence"],
            retention_policy=row["retention_policy"],
            last_message_sequence=row["last_message_sequence"],
            generated_test_data=bool(row["generated_test_data"]),
        )

    @staticmethod
    def _message_from_row(row: RowMapping) -> ConversationMessage:
        return ConversationMessage(
            conversation_id=row["conversation_id"],
            sequence=row["sequence"],
            role=ConversationRole(row["role"]),
            content=row["content"],
            created_at=_datetime(row["created_at"]),
            retained_in_compact=bool(row["retained_in_compact"]),
            generated_test_data=bool(row["generated_test_data"]),
            metadata=json.loads(row["metadata_json"]),
        )

    @staticmethod
    def _validate_message_set(
        conversation: Conversation, messages: Sequence[ConversationMessage]
    ) -> None:
        sequences = [message.sequence for message in messages]
        if sequences != list(range(1, len(messages) + 1)):
            raise ValueError("initial conversation messages must use contiguous sequences")
        if conversation.last_message_sequence != len(messages):
            raise ValueError("conversation message count does not match last sequence")
        for message in messages:
            if message.conversation_id != conversation.id:
                raise ValueError("message belongs to a different conversation")
            if message.generated_test_data != conversation.generated_test_data:
                raise ValueError("generated-test marker must match the conversation")
