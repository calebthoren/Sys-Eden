"""Bridge a live conversation request to durable diagnostic work and stop signals."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from threading import RLock

from sys_eden.task_engine import ProgressUpdate, TaskEngine
from sys_eden.task_models import (
    TERMINAL_TASK_STATES,
    EtaStatus,
    TaskControlRequest,
    TaskConversationLink,
    TaskState,
    TechnicalOperation,
)
from sys_eden.task_timing import TaskTimingEstimator


class ConversationStopped(ValueError):
    """The user stopped this request before its next safe step."""


class ConversationWorkSession:
    """Coordinate one RPC request without making ordinary chat a durable task."""

    def __init__(self, engine: TaskEngine, conversation_id: str) -> None:
        self.engine = engine
        self.conversation_id = conversation_id
        self.task_id: str | None = None
        self._lock = RLock()
        self._stop_requested = False
        self._hard_stop = False
        self._shutdown_requested = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._async_task: asyncio.Task[object] | None = None
        self._timing = TaskTimingEstimator(engine.repository)
        self.technical_operation: TechnicalOperation | None = None

    def bind_current_task(self) -> None:
        with self._lock:
            self._loop = asyncio.get_running_loop()
            self._async_task = asyncio.current_task()
            if self._hard_stop and self._async_task is not None:
                self._async_task.cancel()

    def request_stop(self, *, hard: bool) -> None:
        with self._lock:
            self._stop_requested = True
            self._hard_stop = self._hard_stop or hard
            self._stop_task_locked(at_boundary=False)
            loop = self._loop
            async_task = self._async_task
        if hard and loop is not None and async_task is not None and not async_task.done():
            try:
                loop.call_soon_threadsafe(async_task.cancel)
            except RuntimeError:
                # A completed request may close its loop between the check and signal.
                pass

    def request_shutdown(self) -> None:
        with self._lock:
            self._shutdown_requested = True

    @contextmanager
    def promotion_boundary(self) -> Iterator[None]:
        """Serialize transcript promotion with task control and completion."""
        with self._lock:
            yield

    def check_boundary(self) -> None:
        with self._lock:
            if self._shutdown_requested:
                if self.task_id is not None:
                    task = self.engine.repository.get(self.task_id)
                    if task.state not in TERMINAL_TASK_STATES and task.state is not TaskState.PAUSED:
                        self.engine.request_pause(task.id)
                        self.engine.reach_safe_boundary(task.id)
                raise ConversationStopped("Core is stopping; this request was checkpointed.")
            if not self._stop_requested and self.task_id is not None:
                task = self.engine.repository.get(self.task_id)
                if task.control_request is TaskControlRequest.CANCEL:
                    self._stop_requested = True
            if not self._stop_requested:
                return
            self._stop_task_locked(at_boundary=True)
            hard = self._hard_stop
        raise ConversationStopped(
            "Conversation hard-stopped." if hard else "Conversation stopped at a safe boundary."
        )

    async def wait_boundary(self) -> None:
        """Checkpoint a requested pause, retaining the live continuation until resumed."""
        while True:
            self.check_boundary()
            with self._lock:
                if self.task_id is None:
                    return
                task = self.engine.repository.get(self.task_id)
                if task.control_request is TaskControlRequest.PAUSE:
                    task = self.engine.reach_safe_boundary(self.task_id)
                paused = task.state is TaskState.PAUSED
                if task.state is TaskState.CANCELED:
                    self._stop_requested = True
            if not paused:
                self.check_boundary()
                return
            await asyncio.sleep(0.1)

    def begin_diagnosis(
        self, message: str, component: str, *, report_id: str | None = None
    ) -> None:
        self.check_boundary()
        with self._lock:
            if self.task_id is not None:
                raise ValueError("this conversation request already has a task")
            task = self.engine.create_task(
                title=f"Investigate {component}",
                objective=(
                    f"Read-only {component} investigation in a temporary chat."
                    if self.conversation_id.startswith("TMP-")
                    else message[:8000]
                ),
                active_report_id=report_id,
            )
            self.engine.repository.link_conversation(
                TaskConversationLink(
                    task_id=task.id,
                    conversation_id=self.conversation_id,
                    linked_at=datetime.now(UTC),
                )
            )
            self.task_id = task.id
            self.engine.transition(
                task.id,
                TaskState.OBSERVING,
                message=f"Started read-only {component} investigation.",
                progress=ProgressUpdate(
                    current_phase="Preparing investigation",
                    completed_major_steps=[],
                    current_operation=f"Preparing read-only {component} evidence collection.",
                    eta_status=EtaStatus.UNAVAILABLE,
                ),
            )
        self.check_boundary()

    def record_progress(
        self, phase: str, detail: str, operation: TechnicalOperation | None = None
    ) -> None:
        self.check_boundary()
        with self._lock:
            self.technical_operation = operation
            if self.task_id is None:
                return
            task = self.engine.repository.get(self.task_id)
            if task.state in TERMINAL_TASK_STATES:
                return
            completed = list(task.progress.completed_major_steps) if task.progress else []
            if task.progress and task.progress.current_phase != phase:
                completed.append(task.progress.current_phase)
            estimate = self._timing.estimate(operation) if operation is not None else None
            update = ProgressUpdate(
                    current_phase=phase,
                    completed_major_steps=completed,
                    current_operation=detail,
                    eta_status=EtaStatus.RANGE if estimate else EtaStatus.UNAVAILABLE,
                    eta_min_seconds=estimate.minimum_seconds if estimate else None,
                    eta_max_seconds=estimate.maximum_seconds if estimate else None,
                    eta_basis=estimate.basis if estimate else "Not enough comparable completed operations.",
                    technical_operation=operation,
            )
            target = TaskState.DIAGNOSING if phase == "generating_assessment" else None
            if target is not None and task.state is not target:
                self.engine.transition(task.id, target, progress=update, message=detail)
            else:
                self.engine.record_progress(task.id, update, message=detail)

    def complete(self, response: str) -> None:
        self.check_boundary()
        with self._lock:
            if self.task_id is None:
                return
            task = self.engine.repository.get(self.task_id)
            if task.state not in TERMINAL_TASK_STATES:
                self.engine.transition(
                    task.id,
                    TaskState.COMPLETED,
                    message="Read-only investigation completed.",
                    final_summary=(
                        "Read-only investigation completed in a temporary chat; "
                        "the private response was not retained in this task."
                        if self.conversation_id.startswith("TMP-")
                        else response[:1000]
                    ),
                )

    def fail(self, error: BaseException) -> None:
        with self._lock:
            if self._shutdown_requested:
                return
            if self.task_id is None:
                return
            if self._stop_requested:
                self._stop_task_locked(at_boundary=True)
                return
            task = self.engine.repository.get(self.task_id)
            if task.state not in TERMINAL_TASK_STATES:
                self.engine.transition(
                    task.id,
                    TaskState.FAILED,
                    message=f"Read-only investigation failed: {type(error).__name__}.",
                    final_summary="Investigation failed before a conclusion was available.",
                )

    def _stop_task_locked(self, *, at_boundary: bool) -> None:
        if self.task_id is None:
            return
        task = self.engine.repository.get(self.task_id)
        if task.state in TERMINAL_TASK_STATES:
            return
        if self._hard_stop:
            self.engine.hard_stop(
                task.id,
                message="Hard stop requested during this conversation's work.",
            )
        else:
            if task.control_request is not TaskControlRequest.CANCEL:
                self.engine.request_cancel(task.id)
            if at_boundary:
                self.engine.reach_safe_boundary(task.id)
