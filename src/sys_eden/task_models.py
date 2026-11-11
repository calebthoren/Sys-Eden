"""Durable task, progress, checkpoint, and Core runtime domain models."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12].upper()}"


def new_task_id(*, synthetic: bool = False) -> str:
    """Use a visibly different namespace for generated test work."""
    return _new_id("TST" if synthetic else "TSK")


def new_event_id() -> str:
    return _new_id("TEV")


def new_checkpoint_id() -> str:
    return _new_id("TCP")


def new_runtime_session_id() -> str:
    return _new_id("RUN")


class Clock(Protocol):
    def now(self) -> datetime: ...

    def monotonic(self) -> float: ...


class SystemClock:
    def now(self) -> datetime:
        return utc_now()

    def monotonic(self) -> float:
        return time.monotonic()


class TaskOrigin(StrEnum):
    USER = "user"
    SYSTEM = "system"
    SYNTHETIC_TEST = "synthetic_test"


class TaskConversationRole(StrEnum):
    PRIMARY = "primary"
    SUPPORTING = "supporting"


class TaskState(StrEnum):
    CREATED = "created"
    OBSERVING = "observing"
    AWAITING_CLARIFICATION = "awaiting_clarification"
    RESEARCHING = "researching"
    DIAGNOSING = "diagnosing"
    PLANNING = "planning"
    AWAITING_APPROVAL = "awaiting_approval"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    MONITORING = "monitoring"
    PAUSED = "paused"
    WAITING_CONDITION = "waiting_condition"
    WAITING_USER = "waiting_user"
    RECOVERY_REQUIRED = "recovery_required"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


TERMINAL_TASK_STATES = frozenset(
    {TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELED}
)

ACTIVE_TASK_STATES = frozenset(
    {
        TaskState.OBSERVING,
        TaskState.RESEARCHING,
        TaskState.DIAGNOSING,
        TaskState.PLANNING,
        TaskState.EXECUTING,
        TaskState.VERIFYING,
        TaskState.MONITORING,
    }
)


class TaskControlRequest(StrEnum):
    PAUSE = "pause"
    CANCEL = "cancel"


class TaskEventType(StrEnum):
    CREATED = "created"
    STATE_CHANGED = "state_changed"
    PROGRESS = "progress"
    CONTROL_REQUESTED = "control_requested"
    CHECKPOINTED = "checkpointed"
    RECOVERY_REQUIRED = "recovery_required"
    NON_STOPPABLE_SEGMENT_ANNOUNCED = "non_stoppable_segment_announced"
    NON_STOPPABLE_SEGMENT_ENTERED = "non_stoppable_segment_entered"


class CheckpointReason(StrEnum):
    SAFE_BOUNDARY = "safe_boundary"
    PROGRESS = "progress"
    INTENTIONAL_SHUTDOWN = "intentional_shutdown"
    RECOVERY = "recovery"


class EtaStatus(StrEnum):
    ESTIMATING = "estimating"
    RANGE = "range"
    UNAVAILABLE = "unavailable"


class RuntimeSessionStatus(StrEnum):
    RUNNING = "running"
    CLEAN_STOPPED = "clean_stopped"
    INTERRUPTED = "interrupted"


class RuntimeStopReason(StrEnum):
    USER_REQUESTED = "user_requested"
    DEVELOPMENT = "development"
    TEST = "test"


class InterruptionMode(StrEnum):
    """How promptly an in-progress technical operation can stop safely."""

    IMMEDIATE = "immediate"
    SAFE_BOUNDARY_ONLY = "safe_boundary_only"


class TechnicalOperation(BaseModel):
    """Only pre-sanitized technical detail safe for display and persistence."""

    model_config = ConfigDict(extra="forbid")

    kind: str = Field(min_length=1, max_length=100)
    provider: str | None = Field(default=None, max_length=100)
    tool: str | None = Field(default=None, max_length=200)
    sanitized_command: str | None = Field(default=None, max_length=4000)
    summary: str = Field(min_length=1, max_length=2000)
    interruption_mode: InterruptionMode = InterruptionMode.IMMEDIATE
    non_stoppable_reason: str | None = Field(default=None, max_length=2000)
    generated_test_data: bool = False

    model_id: str | None = Field(default=None, max_length=500)
    workload_key: str | None = Field(default=None, max_length=200)
    context_characters: int | None = Field(default=None, ge=0)
    model_loaded: bool | None = None

    @model_validator(mode="after")
    def validate_interruption_mode(self) -> TechnicalOperation:
        if self.interruption_mode is InterruptionMode.SAFE_BOUNDARY_ONLY:
            if not self.non_stoppable_reason:
                raise ValueError("safe-boundary-only operations require a reason")
        elif self.non_stoppable_reason is not None:
            raise ValueError("only safe-boundary-only operations may have a stop warning")
        return self


class TaskProgress(BaseModel):
    model_config = ConfigDict(extra="forbid")

    started_at: datetime
    current_phase: str = Field(min_length=1, max_length=200)
    completed_major_steps: list[str] = Field(default_factory=list, max_length=200)
    current_operation: str | None = Field(default=None, max_length=2000)
    waiting_reason: str | None = Field(default=None, max_length=2000)
    throttled: bool = False
    active_elapsed_seconds: float = Field(default=0, ge=0)
    operation_started_elapsed_seconds: float | None = Field(default=None, ge=0)
    eta_status: EtaStatus = EtaStatus.ESTIMATING
    eta_min_seconds: float | None = Field(default=None, ge=0)
    eta_max_seconds: float | None = Field(default=None, ge=0)
    eta_basis: str | None = Field(default=None, max_length=2000)
    technical_operation: TechnicalOperation | None = None
    recorded_at: datetime

    @model_validator(mode="after")
    def validate_eta(self) -> TaskProgress:
        if self.eta_status is EtaStatus.RANGE:
            if self.eta_min_seconds is None or self.eta_max_seconds is None:
                raise ValueError("ETA range requires minimum and maximum seconds")
            if self.eta_min_seconds > self.eta_max_seconds:
                raise ValueError("ETA minimum cannot exceed maximum")
        elif self.eta_min_seconds is not None or self.eta_max_seconds is not None:
            raise ValueError("ETA values are only valid when eta_status is range")
        return self


class Task(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=100)
    schema_version: int = Field(default=1, ge=1)
    revision: int = Field(default=1, ge=1)
    title: str = Field(min_length=1, max_length=300)
    objective: str = Field(min_length=1, max_length=8000)
    origin: TaskOrigin = TaskOrigin.USER
    state: TaskState = TaskState.CREATED
    resume_state: TaskState | None = None
    control_request: TaskControlRequest | None = None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    active_elapsed_seconds: float = Field(default=0, ge=0)
    progress: TaskProgress | None = None
    active_report_id: str | None = Field(default=None, max_length=100)
    runtime_session_id: str | None = Field(default=None, max_length=100)
    last_event_sequence: int = Field(default=0, ge=0)
    last_checkpoint_sequence: int = Field(default=0, ge=0)
    final_summary: str | None = Field(default=None, max_length=8000)

    @property
    def synthetic(self) -> bool:
        return self.origin is TaskOrigin.SYNTHETIC_TEST

    @model_validator(mode="after")
    def validate_lifecycle(self) -> Task:
        if self.synthetic and not self.id.startswith("TST-"):
            raise ValueError("synthetic test tasks must use a TST identifier")
        if not self.synthetic and self.id.startswith("TST-"):
            raise ValueError("TST identifiers are reserved for synthetic test tasks")
        if self.state in TERMINAL_TASK_STATES and self.completed_at is None:
            raise ValueError("terminal tasks require completed_at")
        if self.state not in TERMINAL_TASK_STATES and self.completed_at is not None:
            raise ValueError("non-terminal tasks cannot have completed_at")
        if self.state in TERMINAL_TASK_STATES and not self.final_summary:
            raise ValueError("terminal tasks require a final summary")
        if self.state not in TERMINAL_TASK_STATES and self.final_summary is not None:
            raise ValueError("non-terminal tasks cannot have a final summary")
        if self.resume_state in TERMINAL_TASK_STATES:
            raise ValueError("resume_state cannot be terminal")
        return self


class TaskEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=new_event_id, min_length=1, max_length=100)
    task_id: str = Field(min_length=1, max_length=100)
    sequence: int = Field(ge=1)
    event_type: TaskEventType
    occurred_at: datetime
    message: str = Field(min_length=1, max_length=4000)
    from_state: TaskState | None = None
    to_state: TaskState | None = None
    progress: TaskProgress | None = None
    runtime_session_id: str | None = Field(default=None, max_length=100)
    generated_test_data: bool = False


class TaskCheckpoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=new_checkpoint_id, min_length=1, max_length=100)
    task_id: str = Field(min_length=1, max_length=100)
    sequence: int = Field(ge=1)
    reason: CheckpointReason
    state: TaskState
    created_at: datetime
    completed_steps: list[str] = Field(default_factory=list, max_length=200)
    pending_steps: list[str] = Field(default_factory=list, max_length=200)
    wait_condition: str | None = Field(default=None, max_length=4000)
    evidence_references: list[str] = Field(default_factory=list, max_length=200)
    active_report_id: str | None = Field(default=None, max_length=100)
    plan_version: str | None = Field(default=None, max_length=100)
    execution_ids: list[str] = Field(default_factory=list, max_length=200)
    verification_status: str | None = Field(default=None, max_length=200)
    last_model_summary: str | None = Field(default=None, max_length=8000)
    generated_test_data: bool = False


class TaskConversationLink(BaseModel):
    """Associate live work with the thread where it is visible to the user."""

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=1, max_length=100)
    conversation_id: str = Field(min_length=1, max_length=100)
    role: TaskConversationRole = TaskConversationRole.PRIMARY
    linked_at: datetime


class RuntimeSession(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=new_runtime_session_id, min_length=1, max_length=100)
    status: RuntimeSessionStatus = RuntimeSessionStatus.RUNNING
    started_at: datetime
    stopped_at: datetime | None = None
    stop_reason: RuntimeStopReason | None = None
    interrupted_at: datetime | None = None

    @model_validator(mode="after")
    def validate_status(self) -> RuntimeSession:
        if self.status is RuntimeSessionStatus.RUNNING:
            if self.stopped_at is not None or self.stop_reason is not None:
                raise ValueError("running runtime session cannot have stop metadata")
        elif self.status is RuntimeSessionStatus.CLEAN_STOPPED:
            if self.stopped_at is None or self.stop_reason is None:
                raise ValueError("clean stop requires time and reason")
        elif self.interrupted_at is None:
            raise ValueError("interrupted runtime session requires detection time")
        return self
