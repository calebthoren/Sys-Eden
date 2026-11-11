"""Conversation lifetimes, bounded resumption context, and report retention coordination."""

from __future__ import annotations

from threading import RLock

from sys_eden.conversation_models import (
    Conversation,
    ConversationAggregate,
    ConversationContext,
    ConversationMessage,
    ConversationPersistence,
    ConversationRole,
    ConversationWorkStatus,
    LinkActor,
    ReportConversationLink,
    ReportLinkRole,
    RetentionCandidate,
    StandaloneConversationContribution,
    TranscriptState,
    new_conversation_id,
    new_temporary_conversation_id,
)
from sys_eden.conversation_repository import ConversationRepository
from sys_eden.report_models import ReportState
from sys_eden.report_repository import ReportRepository
from sys_eden.task_models import TERMINAL_TASK_STATES, Clock, SystemClock
from sys_eden.task_repository import TaskRepository


class TemporaryConversationNotFound(KeyError):
    pass


class ConversationService:
    """Keep temporary chat memory-only and saved chat behind one service boundary."""

    def __init__(
        self,
        repository: ConversationRepository,
        reports: ReportRepository,
        tasks: TaskRepository | None = None,
        *,
        clock: Clock | None = None,
        recent_message_limit: int = 12,
    ) -> None:
        if recent_message_limit < 1:
            raise ValueError("recent-message limit must be positive")
        self.repository = repository
        self.reports = reports
        self.tasks = tasks
        self.clock = clock or SystemClock()
        self.recent_message_limit = recent_message_limit
        self._temporary: dict[str, ConversationAggregate] = {}
        self._temporary_working: set[str] = set()
        self._work_status: dict[str, ConversationWorkStatus] = {}
        self._deleted_by_client: dict[str, dict[str, ConversationAggregate]] = {}
        self._promotion_lock = RLock()
        self._promoted: dict[str, str] = {}

    def resolve_id(self, conversation_id: str) -> str:
        return self._promoted.get(conversation_id, conversation_id)

    def finish_promotion(self, original_id: str) -> None:
        self._promoted.pop(original_id, None)

    def delete_for_client(
        self, conversation_id: str, *, client_id: str
    ) -> ConversationAggregate:
        """Delete immediately, retaining a private undo copy for this CLI session."""
        if self.work_status(conversation_id) is not None or conversation_id in self._temporary_working:
            raise ValueError("wait for conversation work to finish before deleting it")
        aggregate = self.get_current(conversation_id, owner_client_id=client_id)
        if aggregate.conversation.transcript_state is TranscriptState.DELETED:
            raise ValueError("this conversation is already deleted")
        if conversation_id.startswith("TMP-"):
            self.discard_temporary(conversation_id)
        else:
            self.repository.delete_transcript(
                conversation_id,
                expected_revision=aggregate.conversation.revision,
                updated_at=self.clock.now(),
            )
        self._deleted_by_client.setdefault(client_id, {})[conversation_id] = aggregate
        return aggregate

    def restorable_for_client(self, client_id: str) -> list[Conversation]:
        return [
            aggregate.conversation
            for aggregate in self._deleted_by_client.get(client_id, {}).values()
        ]

    def restore_for_client(
        self, conversation_id: str, *, client_id: str
    ) -> ConversationAggregate:
        try:
            aggregate = self._deleted_by_client[client_id][conversation_id]
        except KeyError as error:
            raise ValueError("no restorable chat with that ID in this CLI session") from error
        if conversation_id.startswith("TMP-"):
            self._temporary[conversation_id] = aggregate
            restored = aggregate
        else:
            restored = self.repository.restore_transcript(aggregate, updated_at=self.clock.now())
        del self._deleted_by_client[client_id][conversation_id]
        return restored

    def forget_deleted_for_client(self, client_id: str) -> None:
        self._deleted_by_client.pop(client_id, None)

    def create_temporary(
        self, *, title: str, owner_client_id: str = "local-client"
    ) -> ConversationAggregate:
        now = self.clock.now()
        conversation = Conversation(
            id=new_temporary_conversation_id(),
            title=title,
            persistence=ConversationPersistence.TEMPORARY,
            transcript_state=TranscriptState.FULL,
            created_at=now,
            updated_at=now,
            owner_client_id=owner_client_id,
        )
        aggregate = ConversationAggregate(conversation=conversation)
        self._temporary[conversation.id] = aggregate
        return aggregate

    def create_saved(
        self,
        *,
        title: str,
        generated_test_data: bool = False,
    ) -> ConversationAggregate:
        now = self.clock.now()
        conversation = Conversation(
            id=new_conversation_id(generated_test_data=generated_test_data),
            title=title,
            persistence=ConversationPersistence.SAVED,
            transcript_state=TranscriptState.FULL,
            created_at=now,
            updated_at=now,
            generated_test_data=generated_test_data,
        )
        return self.repository.create(conversation)

    def append(
        self,
        conversation_id: str,
        *,
        role: ConversationRole,
        content: str,
        metadata: dict[str, str | int | float | bool | None] | None = None,
    ) -> ConversationAggregate:
        with self._promotion_lock:
            return self._append(self.resolve_id(conversation_id), role=role, content=content,
                                metadata=metadata)

    def _append(
        self, conversation_id: str, *, role: ConversationRole, content: str,
        metadata: dict[str, str | int | float | bool | None] | None,
    ) -> ConversationAggregate:
        now = self.clock.now()
        if conversation_id.startswith("TMP-"):
            aggregate = self._temporary_conversation(conversation_id)
            conversation = aggregate.conversation
            message = ConversationMessage(
                conversation_id=conversation_id,
                sequence=conversation.last_message_sequence + 1,
                role=role,
                content=content,
                created_at=now,
                metadata=metadata or {},
            )
            revised = conversation.model_copy(
                update={
                    "revision": conversation.revision + 1,
                    "updated_at": now,
                    "last_message_sequence": message.sequence,
                }
            )
            result = ConversationAggregate(
                conversation=revised, messages=[*aggregate.messages, message]
            )
            self._temporary[conversation_id] = result
            return result
        aggregate = self.repository.get(conversation_id)
        return self.repository.append(
            conversation_id,
            expected_revision=aggregate.conversation.revision,
            role=role,
            content=content,
            created_at=now,
            metadata=metadata,
            generated_test_data=aggregate.conversation.generated_test_data,
        )

    def persist_temporary(
        self, conversation_id: str, *, active_request: bool = False
    ) -> ConversationAggregate:
        with self._promotion_lock:
            resolved = self.resolve_id(conversation_id)
            if resolved != conversation_id:
                return self.repository.get(resolved)
            return self._persist_temporary(conversation_id, active_request=active_request)

    def _persist_temporary(
        self, conversation_id: str, *, active_request: bool
    ) -> ConversationAggregate:
        temporary = self._temporary_conversation(conversation_id)
        now = self.clock.now()
        durable_id = new_conversation_id()
        messages = [
            message.model_copy(update={"conversation_id": durable_id})
            for message in temporary.messages
        ]
        conversation = Conversation(
            id=durable_id,
            title=temporary.conversation.title,
            persistence=ConversationPersistence.SAVED,
            transcript_state=TranscriptState.FULL,
            created_at=temporary.conversation.created_at,
            updated_at=now,
            last_message_sequence=temporary.conversation.last_message_sequence,
            rolling_summary=temporary.conversation.rolling_summary,
            summary_through_sequence=temporary.conversation.summary_through_sequence,
        )
        saved = self.repository.create(conversation, messages)
        if self.tasks is not None:
            self.tasks.relink_conversation_identity(conversation_id, durable_id)
        if active_request or conversation_id in self._temporary_working:
            self._promoted[conversation_id] = durable_id
        del self._temporary[conversation_id]
        self._temporary_working.discard(conversation_id)
        status = self._work_status.pop(conversation_id, None)
        if status is not None:
            self._work_status[durable_id] = status.model_copy(
                update={"conversation_id": durable_id}
            )
        return saved

    def discard_temporary(self, conversation_id: str) -> None:
        if self._temporary.pop(conversation_id, None) is None:
            raise TemporaryConversationNotFound(conversation_id)
        self._temporary_working.discard(conversation_id)
        self._work_status.pop(conversation_id, None)

    def set_temporary_working(self, conversation_id: str, *, working: bool) -> None:
        conversation_id = self.resolve_id(conversation_id)
        if not conversation_id.startswith("TMP-"):
            return
        self._temporary_conversation(conversation_id)
        if working:
            self._temporary_working.add(conversation_id)
        else:
            self._temporary_working.discard(conversation_id)

    def set_work_status(self, conversation_id: str, *, phase: str, detail: str) -> None:
        conversation_id = self.resolve_id(conversation_id)
        previous = self._work_status.get(conversation_id)
        self._work_status[conversation_id] = ConversationWorkStatus(
            conversation_id=conversation_id,
            phase=phase,
            detail=detail,
            started_at=previous.started_at if previous is not None else self.clock.now(),
        )

    def clear_work_status(self, conversation_id: str) -> None:
        conversation_id = self.resolve_id(conversation_id)
        self._work_status.pop(conversation_id, None)

    def work_status(self, conversation_id: str) -> ConversationWorkStatus | None:
        conversation_id = self.resolve_id(conversation_id)
        return self._work_status.get(conversation_id)

    def temporary_for_client(self, client_id: str) -> list[ConversationAggregate]:
        return [
            aggregate
            for aggregate in self._temporary.values()
            if aggregate.conversation.owner_client_id == client_id
        ]

    def active_temporary_for_client(self, client_id: str) -> list[ConversationAggregate]:
        return [
            aggregate
            for aggregate in self.temporary_for_client(client_id)
            if aggregate.conversation.id in self._temporary_working
        ]

    def temporary_is_working(self, conversation_id: str) -> bool:
        self._temporary_conversation(conversation_id)
        return conversation_id in self._temporary_working

    def discard_client_temporary(self, client_id: str, *, include_working: bool) -> list[str]:
        targets = self.temporary_for_client(client_id)
        discarded: list[str] = []
        for aggregate in targets:
            conversation_id = aggregate.conversation.id
            if not include_working and conversation_id in self._temporary_working:
                continue
            self.discard_temporary(conversation_id)
            discarded.append(conversation_id)
        return discarded

    def context_for_resume(self, conversation_id: str) -> ConversationContext:
        aggregate = self.repository.get(conversation_id)
        conversation = aggregate.conversation
        resumed = self.repository.touch_resumed(
            conversation_id,
            expected_revision=conversation.revision,
            resumed_at=self.clock.now(),
        )
        links = self.repository.links_for_conversation(conversation_id)
        primary = next(
            (link.report_id for link in links if link.role is ReportLinkRole.PRIMARY), None
        )
        return ConversationContext(
            conversation_id=conversation_id,
            rolling_summary=resumed.rolling_summary,
            recent_messages=aggregate.messages[-self.recent_message_limit :],
            transcript_state=resumed.transcript_state,
            primary_report_id=primary,
        )

    def context_for_current(self, conversation_id: str) -> ConversationContext:
        conversation_id = self.resolve_id(conversation_id)
        if conversation_id.startswith("TMP-"):
            aggregate = self._temporary_conversation(conversation_id)
            return ConversationContext(
                conversation_id=conversation_id,
                rolling_summary=aggregate.conversation.rolling_summary,
                recent_messages=aggregate.messages[-self.recent_message_limit :],
                transcript_state=TranscriptState.FULL,
            )
        aggregate = self.repository.get(conversation_id)
        links = self.repository.links_for_conversation(conversation_id)
        primary = next(
            (link.report_id for link in links if link.role is ReportLinkRole.PRIMARY), None
        )
        return ConversationContext(
            conversation_id=conversation_id,
            rolling_summary=aggregate.conversation.rolling_summary,
            recent_messages=aggregate.messages[-self.recent_message_limit :],
            transcript_state=aggregate.conversation.transcript_state,
            primary_report_id=primary,
        )

    def get_current(
        self,
        conversation_id: str,
        *,
        owner_client_id: str | None = None,
    ) -> ConversationAggregate:
        """Return the complete active transcript for its owning UI surface."""
        if conversation_id.startswith("TMP-"):
            aggregate = self._temporary_conversation(conversation_id)
            if owner_client_id != aggregate.conversation.owner_client_id:
                raise TemporaryConversationNotFound(conversation_id)
            return aggregate
        return self.repository.get(conversation_id)

    def get_for_core(self, conversation_id: str) -> ConversationAggregate:
        """Return a conversation to trusted Core services without bypassing storage rules."""
        conversation_id = self.resolve_id(conversation_id)
        if conversation_id.startswith("TMP-"):
            return self._temporary_conversation(conversation_id)
        return self.repository.get(conversation_id)

    def update_rolling_summary(
        self, conversation_id: str, *, summary: str, through_sequence: int
    ) -> Conversation:
        with self._promotion_lock:
            return self._update_rolling_summary(self.resolve_id(conversation_id), summary=summary,
                                                through_sequence=through_sequence)

    def _update_rolling_summary(
        self, conversation_id: str, *, summary: str, through_sequence: int
    ) -> Conversation:
        if conversation_id.startswith("TMP-"):
            aggregate = self._temporary_conversation(conversation_id)
            conversation = aggregate.conversation
            if through_sequence > conversation.last_message_sequence:
                raise ValueError("summary sequence exceeds temporary conversation history")
            revised = conversation.model_copy(
                update={
                    "revision": conversation.revision + 1,
                    "rolling_summary": summary,
                    "summary_through_sequence": through_sequence,
                    "updated_at": self.clock.now(),
                }
            )
            self._temporary[conversation_id] = ConversationAggregate(
                conversation=revised,
                messages=aggregate.messages,
            )
            return revised
        conversation = self.repository.get(conversation_id).conversation
        return self.repository.update_summary(
            conversation_id,
            expected_revision=conversation.revision,
            summary=summary,
            through_sequence=through_sequence,
            updated_at=self.clock.now(),
        )

    def compact_current(
        self,
        conversation_id: str,
        *,
        rolling_summary: str,
        key_message_sequences: set[int],
    ) -> ConversationAggregate:
        """Explicitly compact retained context; the caller supplies a validated summary."""
        if conversation_id.startswith("TMP-"):
            aggregate = self._temporary_conversation(conversation_id)
            retained = [
                message.model_copy(update={"retained_in_compact": True})
                for message in aggregate.messages
                if message.sequence in key_message_sequences
            ]
            conversation = aggregate.conversation.model_copy(
                update={
                    "revision": aggregate.conversation.revision + 1,
                    "rolling_summary": rolling_summary,
                    "summary_through_sequence": aggregate.conversation.last_message_sequence,
                    "updated_at": self.clock.now(),
                }
            )
            compacted = ConversationAggregate(conversation=conversation, messages=retained)
            self._temporary[conversation_id] = compacted
            return compacted
        aggregate = self.repository.get(conversation_id)
        if aggregate.conversation.transcript_state is TranscriptState.COMPACT:
            self.update_rolling_summary(
                conversation_id,
                summary=rolling_summary,
                through_sequence=aggregate.conversation.last_message_sequence,
            )
            return self.repository.get(conversation_id)
        return self.repository.compact(
            conversation_id,
            expected_revision=aggregate.conversation.revision,
            rolling_summary=rolling_summary,
            key_message_sequences=key_message_sequences,
            updated_at=self.clock.now(),
        )

    def link_saved_conversation(
        self,
        conversation_id: str,
        report_id: str,
        *,
        role: ReportLinkRole,
        contribution_summary: str | None,
        linked_by: LinkActor = LinkActor.USER,
    ) -> ReportConversationLink:
        conversation = self.repository.get(conversation_id).conversation
        if conversation.transcript_state is TranscriptState.DELETED:
            raise ValueError("a deleted transcript cannot be newly linked")
        self.reports.get(report_id)
        link = ReportConversationLink(
            report_id=report_id,
            conversation_id=conversation_id,
            role=role,
            contribution_summary=contribution_summary,
            contribution_through_sequence=(conversation.last_message_sequence if contribution_summary else 0),
            contribution_updated_at=(self.clock.now() if contribution_summary else None),
            linked_at=self.clock.now(),
            linked_by=linked_by,
        )
        self.repository.link_report(link, replace_primary=linked_by is LinkActor.USER)
        return next(item for item in self.repository.links_for_conversation(conversation_id)
                    if item.report_id == report_id)

    def save_and_link_temporary(
        self,
        temporary_conversation_id: str,
        report_id: str,
        *,
        contribution_summary: str | None,
        linked_by: LinkActor = LinkActor.USER,
    ) -> tuple[ConversationAggregate, ReportConversationLink]:
        """The method name makes the transcript-persistence effect explicit."""
        self.reports.get(report_id)
        saved = self.persist_temporary(temporary_conversation_id)
        link = self.link_saved_conversation(
            saved.conversation.id,
            report_id,
            role=ReportLinkRole.PRIMARY,
            contribution_summary=contribution_summary,
            linked_by=linked_by,
        )
        return saved, link

    def contribute_temporary_without_saving(
        self,
        temporary_conversation_id: str,
        report_id: str,
        *,
        material_summary: str,
    ) -> StandaloneConversationContribution:
        """Retain a distilled report contribution while leaving the transcript temporary."""
        self._temporary_conversation(temporary_conversation_id)
        self.reports.get(report_id)
        contribution = StandaloneConversationContribution(
            report_id=report_id,
            source_temporary_conversation_id=temporary_conversation_id,
            summary=material_summary,
            created_at=self.clock.now(),
        )
        return self.repository.add_standalone_contribution(contribution)

    def review_closed_report_retention(
        self,
        report_id: str,
        *,
        unique_evidence_conversation_ids: set[str] | None = None,
    ) -> list[RetentionCandidate]:
        report = self.reports.get(report_id)
        if report.state is not ReportState.CLOSED:
            raise ValueError("retention review requires a closed report")
        evidence_reviewed = unique_evidence_conversation_ids is not None
        unique_evidence = unique_evidence_conversation_ids or set()
        candidates: list[RetentionCandidate] = []
        for link in self.repository.links_for_report(report_id):
            conversation = self.repository.get(link.conversation_id).conversation
            eligible, reason = self._retention_eligibility(
                conversation,
                link,
                closed_report_id=report_id,
                contains_unique_evidence=link.conversation_id in unique_evidence,
                evidence_reviewed=evidence_reviewed,
            )
            candidate = RetentionCandidate(
                report_id=report_id,
                conversation_id=link.conversation_id,
                eligible=eligible,
                reason=reason,
                reviewed_at=self.clock.now(),
            )
            self.repository.record_retention_candidate(candidate)
            candidates.append(candidate)
        return candidates

    def _retention_eligibility(
        self,
        conversation: Conversation,
        link: ReportConversationLink,
        *,
        closed_report_id: str,
        contains_unique_evidence: bool,
        evidence_reviewed: bool,
    ) -> tuple[bool, str]:
        if conversation.pinned:
            return False, "Protected because the conversation is pinned."
        if self.tasks is not None and any(
            task.state not in TERMINAL_TASK_STATES
            for task in self.tasks.tasks_for_conversation(conversation.id)
        ):
            return False, "Protected because the conversation is linked to unfinished work."
        if conversation.transcript_state is not TranscriptState.FULL:
            return False, "No Full transcript is available for compaction."
        if not self.reports.get(closed_report_id).summary:
            return False, "Protected until the closed report has a structured summary."
        if contains_unique_evidence:
            return False, "Protected because the transcript contains unextracted unique evidence."
        if not evidence_reviewed:
            return False, "Protected until unique transcript evidence is explicitly reviewed."
        if not link.contribution_summary:
            return False, "Protected until its report contribution has a summary."
        if link.contribution_through_sequence < conversation.last_message_sequence:
            return False, "Protected until its report contribution includes the latest conversation."
        for other in self.repository.links_for_conversation(conversation.id):
            if other.report_id == closed_report_id:
                continue
            if self.reports.get(other.report_id).state is ReportState.OPEN:
                return False, "Protected because it is linked to another open report."
        return True, "Eligible for user-reviewed compaction; no data was changed."

    def _temporary_conversation(self, conversation_id: str) -> ConversationAggregate:
        try:
            return self._temporary[conversation_id]
        except KeyError as error:
            promoted = self._promoted.get(conversation_id)
            if promoted is not None:
                return self.repository.get(promoted)
            raise TemporaryConversationNotFound(conversation_id) from error
