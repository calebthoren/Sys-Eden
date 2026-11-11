"""Minimal long-running, user-context Core assembled from domain services."""

from __future__ import annotations

from contextlib import nullcontext
from enum import StrEnum
from threading import RLock

from pydantic import BaseModel, ConfigDict, Field

from sys_eden.chat_service import ChatService
from sys_eden.client_sessions import ClientSessionRegistry
from sys_eden.config import Settings
from sys_eden.conversation_contributions import ConversationContributionService
from sys_eden.conversation_models import RetentionCandidate
from sys_eden.conversation_repository import ConversationRepository
from sys_eden.conversation_service import ConversationService
from sys_eden.conversation_work import ConversationWorkSession
from sys_eden.core_presence import record_presence
from sys_eden.inspection import InspectionProvider
from sys_eden.inspection_service import InspectionService, create_windows_inspection_provider
from sys_eden.model_routing import RoutingPreference
from sys_eden.model_runtime import create_model_provider
from sys_eden.model_service import ModelService
from sys_eden.models import ModelProvider
from sys_eden.report_knowledge import ReportKnowledgeService
from sys_eden.report_models import Report, ReportStatus
from sys_eden.report_repository import ReportRepository
from sys_eden.report_service import ReportService
from sys_eden.storage import Database
from sys_eden.storage_status import StorageStatusService
from sys_eden.synthetic_tasks import SyntheticTaskService
from sys_eden.task_engine import TaskEngine
from sys_eden.task_models import TERMINAL_TASK_STATES, RuntimeStopReason
from sys_eden.task_repository import RuntimeSessionRepository, TaskRepository


class CoreLifecycleState(StrEnum):
    STOPPED = "stopped"
    RUNNING = "running"
    UNAVAILABLE = "unavailable"


class SystemServiceState(StrEnum):
    NOT_IMPLEMENTED = "not_implemented"


class CoreRuntimeStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: CoreLifecycleState
    runtime_session_id: str | None = None
    interrupted_previous_session_id: str | None = None
    recovered_task_ids: list[str] = Field(default_factory=list)
    system_service: SystemServiceState = SystemServiceState.NOT_IMPLEMENTED


class CoreApplication:
    """Own database access and application services; it has no privileged authority."""

    def __init__(
        self,
        settings: Settings,
        provider: ModelProvider | None = None,
        inspection_provider: InspectionProvider | None = None,
    ):
        self.settings = settings
        self.provider = provider if provider is not None else create_model_provider(settings)
        self.database = Database(settings.data_directory / "eden.db")
        self.reports = ReportRepository(self.database)
        self.tasks = TaskRepository(self.database)
        self.runtime_sessions = RuntimeSessionRepository(self.database)
        self.task_engine = TaskEngine(self.tasks, self.runtime_sessions)
        self.conversations = ConversationRepository(self.database)
        self.conversation_service = ConversationService(
            self.conversations, self.reports, self.tasks
        )
        self.client_sessions = ClientSessionRegistry(
            self.conversation_service,
            stop_temporary_work=self._stop_temporary_work,
        )
        self.report_knowledge = ReportKnowledgeService(self.reports, self.conversations)
        self.report_service = ReportService(self.reports, self.report_knowledge)
        self.contributions = ConversationContributionService(
            self.conversations, self.reports, self.provider,
            context_max_characters=settings.model.context_max_characters,
            preferred_model=settings.model.default_model,
        )
        self.inspection = InspectionService(
            inspection_provider or create_windows_inspection_provider()
        )
        self.model_service = ModelService(self.provider, self.inspection, settings.model)
        self.storage_status = StorageStatusService(self.database, settings.storage)
        self.chat = ChatService(
            self.conversation_service,
            self.provider,
            preferred_model=settings.model.default_model,
            routing_preference=RoutingPreference(settings.model.routing_preference),
            max_output_tokens=settings.model.max_output_tokens,
            context_max_characters=settings.model.context_max_characters,
            diagnostics=self.model_service,
            contributions=self.contributions,
            report_knowledge=self.report_knowledge,
        )
        self.synthetic_tasks = SyntheticTaskService(self.task_engine)
        self._conversation_work: dict[str, ConversationWorkSession] = {}
        self._conversation_work_lock = RLock()
        self._status = CoreRuntimeStatus(state=CoreLifecycleState.STOPPED)
        self._stopping = False

    @property
    def status(self) -> CoreRuntimeStatus:
        return self._status

    def start(self) -> CoreRuntimeStatus:
        if self._status.state is CoreLifecycleState.RUNNING:
            return self._status
        self.database.initialize()
        self._stopping = False
        session, interrupted, recovered = self.task_engine.start_runtime()
        self._status = CoreRuntimeStatus(
            state=CoreLifecycleState.RUNNING,
            runtime_session_id=session.id,
            interrupted_previous_session_id=interrupted.id if interrupted else None,
            recovered_task_ids=[task.id for task in recovered],
        )
        record_presence(self.settings.data_directory, state="running")
        return self._status

    def stop(
        self, reason: RuntimeStopReason = RuntimeStopReason.USER_REQUESTED
    ) -> CoreRuntimeStatus:
        if self._status.state is CoreLifecycleState.STOPPED:
            return self._status
        self.prepare_stop()
        self.task_engine.clean_shutdown(reason)
        self._status = CoreRuntimeStatus(state=CoreLifecycleState.STOPPED)
        record_presence(self.settings.data_directory, state="stopped")
        return self._status

    def prepare_stop(self) -> None:
        """Reject new work and wake paused continuations before the host drains RPCs."""
        with self._conversation_work_lock:
            self._stopping = True
            for session in self._conversation_work.values():
                session.request_shutdown()

    def close(self) -> None:
        """Release local resources; callers should stop first when Core is running."""
        self.database.close()

    def close_report(
        self, report_id: str, *, status: ReportStatus, summary: str, outcome: str
    ) -> tuple[Report, list[RetentionCandidate]]:
        report = self.report_service.close(
            report_id, status=status, summary=summary, outcome=outcome
        )
        candidates = self.conversation_service.review_closed_report_retention(report.id)
        return report, candidates

    def _stop_temporary_work(self, conversation_id: str) -> None:
        self.stop_conversation_work(conversation_id, hard=False)

    def begin_conversation_work(self, conversation_id: str) -> ConversationWorkSession:
        with self._conversation_work_lock:
            if self._stopping:
                raise ValueError("Core is stopping; no new conversation work was started")
            if conversation_id in self._conversation_work:
                raise ValueError("this conversation is already working")
            session = ConversationWorkSession(self.task_engine, conversation_id)
            self._conversation_work[conversation_id] = session
            return session

    def end_conversation_work(self, session: ConversationWorkSession) -> None:
        with self._conversation_work_lock:
            if self._conversation_work.get(session.conversation_id) is session:
                del self._conversation_work[session.conversation_id]

    def active_conversation_task_id(self, conversation_id: str) -> str | None:
        with self._conversation_work_lock:
            session = self._conversation_work.get(conversation_id)
            return session.task_id if session is not None else None

    def is_conversation_working(self, conversation_id: str) -> bool:
        with self._conversation_work_lock:
            return conversation_id in self._conversation_work

    def conversation_operation(self, conversation_id: str) -> dict[str, object] | None:
        with self._conversation_work_lock:
            session = self._conversation_work.get(conversation_id)
            operation = session.technical_operation if session else None
            return operation.model_dump(mode="json") if operation else None

    def persist_conversation(self, conversation_id: str):
        """Keep a live request attached while its transcript becomes durable."""
        with self._conversation_work_lock:
            session = self._conversation_work.get(conversation_id)
            with session.promotion_boundary() if session else nullcontext():
                saved = self.conversation_service.persist_temporary(
                    conversation_id, active_request=session is not None
                )
                if session is not None:
                    session.conversation_id = saved.conversation.id
                    del self._conversation_work[conversation_id]
                    self._conversation_work[saved.conversation.id] = session
            return saved

    def stop_conversation_work(self, conversation_id: str, *, hard: bool) -> list[str]:
        affected: list[str] = []
        with self._conversation_work_lock:
            session = self._conversation_work.get(conversation_id)
        if session is not None:
            session.request_stop(hard=hard)
        for task in self.tasks.tasks_for_conversation(conversation_id):
            if session is not None and task.id == session.task_id:
                affected.append(task.id)
                continue
            if task.state in TERMINAL_TASK_STATES:
                continue
            if hard:
                self.task_engine.hard_stop(
                    task.id,
                    message=(
                        "Hard stop requested from the linked conversation; uncertain "
                        "safe-boundary-only work requires recovery."
                    ),
                )
            else:
                self.task_engine.request_cancel(task.id)
            affected.append(task.id)
        return affected
