"""State-machine and checkpoint coordination for durable Eden tasks."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from functools import wraps
from threading import RLock
from typing import Concatenate

from sys_eden.task_models import (
    ACTIVE_TASK_STATES,
    TERMINAL_TASK_STATES,
    CheckpointReason,
    Clock,
    EtaStatus,
    InterruptionMode,
    RuntimeSession,
    RuntimeStopReason,
    SystemClock,
    Task,
    TaskCheckpoint,
    TaskControlRequest,
    TaskEvent,
    TaskEventType,
    TaskOrigin,
    TaskProgress,
    TaskState,
    TechnicalOperation,
    new_task_id,
)
from sys_eden.task_repository import RuntimeSessionRepository, TaskRepository


class TaskTransitionError(ValueError):
    """A requested state change would violate durable task semantics."""


def _serialized[**Parameters, Result](
    method: Callable[Concatenate[TaskEngine, Parameters], Result],
) -> Callable[Concatenate[TaskEngine, Parameters], Result]:
    @wraps(method)
    def call(self: TaskEngine, *args: Parameters.args, **kwargs: Parameters.kwargs) -> Result:
        with self._lock:
            return method(self, *args, **kwargs)
    return call


@dataclass(frozen=True)
class ProgressUpdate:
    current_phase: str
    completed_major_steps: list[str]
    current_operation: str | None = None
    waiting_reason: str | None = None
    throttled: bool = False
    eta_status: EtaStatus = EtaStatus.ESTIMATING
    eta_min_seconds: float | None = None
    eta_max_seconds: float | None = None
    eta_basis: str | None = None
    technical_operation: TechnicalOperation | None = None


class TaskEngine:
    def __init__(
        self,
        repository: TaskRepository,
        runtime_sessions: RuntimeSessionRepository,
        *,
        clock: Clock | None = None,
    ) -> None:
        self.repository = repository
        self.runtime_sessions = runtime_sessions
        self.clock = clock or SystemClock()
        self.runtime_session: RuntimeSession | None = None
        self._active_segments: dict[str, float] = {}
        self._lock = RLock()

    @_serialized
    def start_runtime(self) -> tuple[RuntimeSession, RuntimeSession | None, list[Task]]:
        now = self.clock.now()
        session = RuntimeSession(started_at=now)
        current, interrupted = self.runtime_sessions.begin(session)
        self.runtime_session = current
        recovered: list[Task] = []
        if interrupted is not None:
            for task in self.repository.list_for_runtime(
                interrupted.id, states=set(ACTIVE_TASK_STATES)
            ):
                recovered.append(
                    self._transition_existing(
                        task,
                        TaskState.RECOVERY_REQUIRED,
                        message=(
                            "The previous Core session ended without a clean stop; "
                            "the task requires reconciliation before it can continue."
                        ),
                        checkpoint_reason=CheckpointReason.RECOVERY,
                        event_type=TaskEventType.RECOVERY_REQUIRED,
                    )
                )
        return current, interrupted, recovered

    @_serialized
    def create_task(
        self,
        *,
        title: str,
        objective: str,
        origin: TaskOrigin = TaskOrigin.USER,
        active_report_id: str | None = None,
    ) -> Task:
        runtime_id = self._runtime_id()
        now = self.clock.now()
        synthetic = origin is TaskOrigin.SYNTHETIC_TEST
        task = Task(
            id=new_task_id(synthetic=synthetic),
            title=title,
            objective=objective,
            origin=origin,
            state=TaskState.CREATED,
            created_at=now,
            updated_at=now,
            active_report_id=active_report_id,
            runtime_session_id=runtime_id,
            last_event_sequence=1,
        )
        event = TaskEvent(
            task_id=task.id,
            sequence=1,
            event_type=TaskEventType.CREATED,
            occurred_at=now,
            message=(
                "Created a generated synthetic test task; it contains no real machine evidence."
                if synthetic
                else "Task created."
            ),
            to_state=TaskState.CREATED,
            runtime_session_id=runtime_id,
            generated_test_data=synthetic,
        )
        return self.repository.create(task, event)

    @_serialized
    def transition(
        self,
        task_id: str,
        new_state: TaskState,
        *,
        message: str,
        progress: ProgressUpdate | None = None,
        final_summary: str | None = None,
    ) -> Task:
        return self._transition_existing(
            self.repository.get(task_id),
            new_state,
            message=message,
            progress=progress,
            final_summary=final_summary,
        )

    @_serialized
    def record_progress(
        self, task_id: str, update: ProgressUpdate, *, message: str
    ) -> Task:
        task = self.repository.get(task_id)
        if task.state in TERMINAL_TASK_STATES:
            raise TaskTransitionError("terminal tasks cannot record new progress")
        if task.state not in ACTIVE_TASK_STATES:
            raise TaskTransitionError("only active tasks can record operation progress")
        if (
            update.technical_operation is not None
            and update.technical_operation.interruption_mode
            is InterruptionMode.SAFE_BOUNDARY_ONLY
        ):
            events = self.repository.events(task_id)
            if (
                not events
                or events[-1].event_type is not TaskEventType.NON_STOPPABLE_SEGMENT_ANNOUNCED
                or update.technical_operation.summary not in events[-1].message
            ):
                raise TaskTransitionError(
                    "announce the non-stoppable segment before entering it"
                )
        now = self.clock.now()
        elapsed = self._capture_elapsed(task)
        progress = self._build_progress(task, update, now=now, elapsed=elapsed)
        revised = task.model_copy(
            update={
                "revision": task.revision + 1,
                "updated_at": now,
                "active_elapsed_seconds": elapsed,
                "progress": progress,
                "runtime_session_id": self._runtime_id(),
                "last_event_sequence": task.last_event_sequence + 1,
            }
        )
        event_type = TaskEventType.PROGRESS
        if (
            update.technical_operation is not None
            and update.technical_operation.interruption_mode
            is InterruptionMode.SAFE_BOUNDARY_ONLY
        ):
            event_type = TaskEventType.NON_STOPPABLE_SEGMENT_ENTERED
        event = self._event(
            revised,
            event_type,
            message,
            from_state=task.state,
            to_state=task.state,
        )
        stored = self.repository.update(revised, expected_revision=task.revision, event=event)
        self._begin_segment_if_active(stored)
        return stored

    @_serialized
    def announce_non_stoppable_segment(
        self, task_id: str, operation: TechnicalOperation
    ) -> Task:
        """Persist a visible warning before the caller starts a hard-to-stop step."""
        if operation.interruption_mode is not InterruptionMode.SAFE_BOUNDARY_ONLY:
            raise TaskTransitionError("only safe-boundary-only steps need this warning")
        task = self.repository.get(task_id)
        if task.state not in ACTIVE_TASK_STATES:
            raise TaskTransitionError("only active tasks can announce a work segment")
        if task.control_request is not None:
            return self.reach_safe_boundary(task_id)
        now = self.clock.now()
        elapsed = self._capture_elapsed(task)
        revised = task.model_copy(update={
            "revision": task.revision + 1,
            "updated_at": now,
            "active_elapsed_seconds": elapsed,
            "progress": self._progress_with_elapsed(task.progress, elapsed, now),
            "runtime_session_id": self._runtime_id(),
            "last_event_sequence": task.last_event_sequence + 1,
        })
        event = self._event(
            revised,
            TaskEventType.NON_STOPPABLE_SEGMENT_ANNOUNCED,
            "WARNING: Upcoming non-stoppable step: " + operation.summary + " "
            + str(operation.non_stoppable_reason)[:1700]
            + " A stop request will take effect at the next safe boundary.",
            from_state=task.state,
            to_state=task.state,
        )
        stored = self.repository.update(revised, expected_revision=task.revision, event=event)
        self._begin_segment_if_active(stored)
        return stored

    @_serialized
    def checkpoint(
        self,
        task_id: str,
        *,
        reason: CheckpointReason = CheckpointReason.PROGRESS,
        pending_steps: list[str] | None = None,
        wait_condition: str | None = None,
        message: str = "Task checkpoint recorded.",
    ) -> Task:
        task = self.repository.get(task_id)
        now = self.clock.now()
        elapsed = self._capture_elapsed(task)
        revised = task.model_copy(
            update={
                "revision": task.revision + 1,
                "updated_at": now,
                "active_elapsed_seconds": elapsed,
                "runtime_session_id": self._runtime_id(),
                "last_event_sequence": task.last_event_sequence + 1,
                "last_checkpoint_sequence": task.last_checkpoint_sequence + 1,
                "progress": self._progress_with_elapsed(task.progress, elapsed, now),
            }
        )
        checkpoint = self._checkpoint(
            revised,
            reason=reason,
            pending_steps=pending_steps,
            wait_condition=wait_condition,
        )
        event = self._event(
            revised,
            TaskEventType.CHECKPOINTED,
            message,
            from_state=task.state,
            to_state=task.state,
        )
        stored = self.repository.update(
            revised,
            expected_revision=task.revision,
            event=event,
            checkpoint=checkpoint,
        )
        self._begin_segment_if_active(stored)
        return stored

    @_serialized
    def request_pause(self, task_id: str) -> Task:
        task = self.repository.get(task_id)
        if task.state in TERMINAL_TASK_STATES:
            raise TaskTransitionError("terminal tasks cannot be paused")
        if task.state is TaskState.PAUSED:
            return task
        if task.state not in ACTIVE_TASK_STATES:
            return self._transition_existing(
                task,
                TaskState.PAUSED,
                message="Task paused at an already-safe boundary.",
                checkpoint_reason=CheckpointReason.SAFE_BOUNDARY,
            )
        return self._set_control_request(task, TaskControlRequest.PAUSE)

    @_serialized
    def request_cancel(self, task_id: str) -> Task:
        task = self.repository.get(task_id)
        if task.state in TERMINAL_TASK_STATES:
            return task
        if task.state not in ACTIVE_TASK_STATES:
            return self._transition_existing(
                task,
                TaskState.CANCELED,
                message="Task canceled at a safe boundary.",
                checkpoint_reason=CheckpointReason.SAFE_BOUNDARY,
            )
        return self._set_control_request(task, TaskControlRequest.CANCEL)

    @_serialized
    def hard_stop(self, task_id: str, *, message: str) -> Task:
        """Stop immediately when safe, or require reconciliation if state is uncertain."""
        task = self.repository.get(task_id)
        if task.state in TERMINAL_TASK_STATES:
            return task
        technical = task.progress.technical_operation if task.progress else None
        uncertain = (
            technical is not None
            and technical.interruption_mode is InterruptionMode.SAFE_BOUNDARY_ONLY
        )
        if uncertain:
            return self._transition_existing(
                task,
                TaskState.RECOVERY_REQUIRED,
                message=message,
                checkpoint_reason=CheckpointReason.RECOVERY,
                event_type=TaskEventType.RECOVERY_REQUIRED,
            )
        return self._transition_existing(
            task,
            TaskState.CANCELED,
            message=message,
            checkpoint_reason=CheckpointReason.SAFE_BOUNDARY,
        )

    @_serialized
    def reach_safe_boundary(
        self, task_id: str, *, pending_steps: list[str] | None = None
    ) -> Task:
        task = self.repository.get(task_id)
        if task.control_request is TaskControlRequest.PAUSE:
            return self._transition_existing(
                task,
                TaskState.PAUSED,
                message="Pause request applied at a safe boundary.",
                checkpoint_reason=CheckpointReason.SAFE_BOUNDARY,
                pending_steps=pending_steps,
            )
        if task.control_request is TaskControlRequest.CANCEL:
            return self._transition_existing(
                task,
                TaskState.CANCELED,
                message="Cancellation request applied at a safe boundary.",
                checkpoint_reason=CheckpointReason.SAFE_BOUNDARY,
                pending_steps=pending_steps,
            )
        return self.checkpoint(
            task_id,
            reason=CheckpointReason.SAFE_BOUNDARY,
            pending_steps=pending_steps,
        )

    @_serialized
    def resume(self, task_id: str) -> Task:
        task = self.repository.get(task_id)
        if task.state is TaskState.RECOVERY_REQUIRED:
            raise TaskTransitionError(
                "recovery-required tasks must be reconciled before they can resume"
            )
        if task.state is not TaskState.PAUSED:
            raise TaskTransitionError("only paused tasks can resume")
        target = task.resume_state or TaskState.CREATED
        return self._transition_existing(task, target, message="Task resumed.")

    @_serialized
    def reconcile_recovery(
        self, task_id: str, *, safe_to_resume: bool, message: str
    ) -> Task:
        task = self.repository.get(task_id)
        if task.state is not TaskState.RECOVERY_REQUIRED:
            raise TaskTransitionError("task does not require recovery")
        explanation = message.strip()
        if not explanation:
            raise TaskTransitionError("recovery reconciliation requires an explanation")
        if safe_to_resume and not task.synthetic:
            raise TaskTransitionError(
                "only synthetic fixture work can be marked safe to resume; "
                "real work needs a verified runner before resumption"
            )
        # Reconciliation never starts a worker. A verified synthetic fixture can
        # be left paused; an interrupted real attempt is closed for a fresh run.
        target = TaskState.PAUSED if safe_to_resume else TaskState.FAILED
        return self._transition_existing(task, target, message=explanation)

    @_serialized
    def clean_shutdown(self, reason: RuntimeStopReason) -> list[Task]:
        session_id = self._runtime_id()
        checkpointed: list[Task] = []
        for task in self.repository.list_for_runtime(
            session_id, states=set(ACTIVE_TASK_STATES) | {TaskState.PAUSED}
        ):
            if task.state is TaskState.PAUSED:
                checkpointed.append(self.checkpoint(
                    task.id, reason=CheckpointReason.INTENTIONAL_SHUTDOWN,
                ))
                continue
            checkpointed.append(
                self._transition_existing(
                    task,
                    TaskState.PAUSED,
                    message="Task checkpointed for an intentional Core shutdown.",
                    checkpoint_reason=CheckpointReason.INTENTIONAL_SHUTDOWN,
                )
            )
        self.runtime_sessions.clean_stop(
            session_id, stopped_at=self.clock.now(), reason=reason
        )
        self.runtime_session = None
        self._active_segments.clear()
        return checkpointed

    def _transition_existing(
        self,
        task: Task,
        new_state: TaskState,
        *,
        message: str,
        progress: ProgressUpdate | None = None,
        checkpoint_reason: CheckpointReason | None = None,
        pending_steps: list[str] | None = None,
        event_type: TaskEventType = TaskEventType.STATE_CHANGED,
        final_summary: str | None = None,
    ) -> Task:
        self._validate_transition(task.state, new_state)
        now = self.clock.now()
        elapsed = self._capture_elapsed(task)
        started_at = task.started_at
        if started_at is None and new_state is not TaskState.CREATED:
            started_at = now
        resume_state = task.resume_state
        if new_state in {
            TaskState.PAUSED,
            TaskState.WAITING_CONDITION,
            TaskState.WAITING_USER,
            TaskState.RECOVERY_REQUIRED,
        }:
            if task.state not in {
                TaskState.PAUSED,
                TaskState.WAITING_CONDITION,
                TaskState.WAITING_USER,
                TaskState.RECOVERY_REQUIRED,
            }:
                resume_state = task.state
        else:
            resume_state = None
        completed_at = now if new_state in TERMINAL_TASK_STATES else None
        if new_state in TERMINAL_TASK_STATES:
            final_summary = final_summary or message
        elif final_summary is not None:
            raise TaskTransitionError("only terminal tasks can receive a final summary")
        current_progress = (
            self._build_progress(task, progress, now=now, elapsed=elapsed)
            if progress is not None
            else self._progress_with_elapsed(task.progress, elapsed, now)
        )
        revised = task.model_copy(
            update={
                "revision": task.revision + 1,
                "state": new_state,
                "resume_state": resume_state,
                "control_request": None,
                "updated_at": now,
                "started_at": started_at,
                "completed_at": completed_at,
                "active_elapsed_seconds": elapsed,
                "progress": current_progress,
                "runtime_session_id": self._runtime_id(),
                "last_event_sequence": task.last_event_sequence + 1,
                "last_checkpoint_sequence": (
                    task.last_checkpoint_sequence + 1
                    if checkpoint_reason is not None
                    else task.last_checkpoint_sequence
                ),
                "final_summary": final_summary,
            }
        )
        event = self._event(
            revised,
            event_type,
            message,
            from_state=task.state,
            to_state=new_state,
        )
        checkpoint = (
            self._checkpoint(
                revised, reason=checkpoint_reason, pending_steps=pending_steps
            )
            if checkpoint_reason is not None
            else None
        )
        stored = self.repository.update(
            revised,
            expected_revision=task.revision,
            event=event,
            checkpoint=checkpoint,
        )
        self._begin_segment_if_active(stored)
        return stored

    def _set_control_request(self, task: Task, request: TaskControlRequest) -> Task:
        now = self.clock.now()
        elapsed = self._capture_elapsed(task)
        revised = task.model_copy(
            update={
                "revision": task.revision + 1,
                "control_request": request,
                "updated_at": now,
                "active_elapsed_seconds": elapsed,
                "progress": self._progress_with_elapsed(task.progress, elapsed, now),
                "runtime_session_id": self._runtime_id(),
                "last_event_sequence": task.last_event_sequence + 1,
            }
        )
        event = self._event(
            revised,
            TaskEventType.CONTROL_REQUESTED,
            f"{request.value.capitalize()} requested; waiting for a safe boundary.",
            from_state=task.state,
            to_state=task.state,
        )
        stored = self.repository.update(revised, expected_revision=task.revision, event=event)
        self._begin_segment_if_active(stored)
        return stored

    def _capture_elapsed(self, task: Task) -> float:
        started = self._active_segments.pop(task.id, None)
        if started is None:
            return task.active_elapsed_seconds
        return task.active_elapsed_seconds + max(self.clock.monotonic() - started, 0)

    @_serialized
    def current_elapsed(self, task_id: str) -> float:
        """Read a running task's monotonic elapsed time without changing its checkpoint."""
        task = self.repository.get(task_id)
        started = self._active_segments.get(task_id)
        if started is None:
            return task.active_elapsed_seconds
        return task.active_elapsed_seconds + max(self.clock.monotonic() - started, 0)

    def _begin_segment_if_active(self, task: Task) -> None:
        if task.state in ACTIVE_TASK_STATES:
            self._active_segments[task.id] = self.clock.monotonic()

    @staticmethod
    def _progress_with_elapsed(
        progress: TaskProgress | None, elapsed: float, now: datetime
    ) -> TaskProgress | None:
        if progress is None:
            return None
        return progress.model_copy(
            update={"active_elapsed_seconds": elapsed, "recorded_at": now}
        )

    @staticmethod
    def _build_progress(
        task: Task, update: ProgressUpdate, *, now: datetime, elapsed: float
    ) -> TaskProgress:
        return TaskProgress(
            operation_started_elapsed_seconds=(
                task.progress.operation_started_elapsed_seconds
                if task.progress is not None
                and task.progress.current_phase == update.current_phase
                and task.progress.technical_operation == update.technical_operation
                and task.progress.operation_started_elapsed_seconds is not None
                else elapsed
            ),
            started_at=task.started_at or task.created_at,
            current_phase=update.current_phase,
            completed_major_steps=update.completed_major_steps,
            current_operation=update.current_operation,
            waiting_reason=update.waiting_reason,
            throttled=update.throttled,
            active_elapsed_seconds=elapsed,
            eta_status=update.eta_status,
            eta_min_seconds=update.eta_min_seconds,
            eta_max_seconds=update.eta_max_seconds,
            eta_basis=update.eta_basis,
            technical_operation=update.technical_operation,
            recorded_at=now,
        )

    @staticmethod
    def _validate_transition(current: TaskState, target: TaskState) -> None:
        if current in TERMINAL_TASK_STATES:
            raise TaskTransitionError("terminal tasks cannot transition")
        if target is TaskState.CREATED and current is not TaskState.PAUSED:
            raise TaskTransitionError("tasks cannot transition back to created")
        if current is target:
            raise TaskTransitionError("state transition must change state")

    @staticmethod
    def _checkpoint(
        task: Task,
        *,
        reason: CheckpointReason,
        pending_steps: list[str] | None = None,
        wait_condition: str | None = None,
    ) -> TaskCheckpoint:
        completed = task.progress.completed_major_steps if task.progress else []
        return TaskCheckpoint(
            task_id=task.id,
            sequence=task.last_checkpoint_sequence,
            reason=reason,
            state=task.state,
            created_at=task.updated_at,
            completed_steps=completed,
            pending_steps=pending_steps or [],
            wait_condition=wait_condition,
            active_report_id=task.active_report_id,
            generated_test_data=task.synthetic,
        )

    @staticmethod
    def _event(
        task: Task,
        event_type: TaskEventType,
        message: str,
        *,
        from_state: TaskState,
        to_state: TaskState,
    ) -> TaskEvent:
        return TaskEvent(
            task_id=task.id,
            sequence=task.last_event_sequence,
            event_type=event_type,
            occurred_at=task.updated_at,
            message=message,
            from_state=from_state,
            to_state=to_state,
            progress=task.progress,
            runtime_session_id=task.runtime_session_id,
            generated_test_data=task.synthetic,
        )

    def _runtime_id(self) -> str:
        if self.runtime_session is None:
            raise RuntimeError("Core runtime session has not been started")
        return self.runtime_session.id
