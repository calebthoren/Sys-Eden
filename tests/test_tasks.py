from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from sys_eden.storage import Database
from sys_eden.task_engine import ProgressUpdate, TaskEngine, TaskTransitionError
from sys_eden.task_models import (
    CheckpointReason,
    EtaStatus,
    InterruptionMode,
    RuntimeSessionStatus,
    RuntimeStopReason,
    TaskControlRequest,
    TaskConversationLink,
    TaskOrigin,
    TaskState,
    TechnicalOperation,
)
from sys_eden.task_repository import RuntimeSessionRepository, TaskRepository


class FakeClock:
    def __init__(self) -> None:
        self.wall = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)
        self.elapsed = 100.0

    def now(self) -> datetime:
        return self.wall

    def monotonic(self) -> float:
        return self.elapsed

    def advance(self, seconds: float) -> None:
        self.wall += timedelta(seconds=seconds)
        self.elapsed += seconds


@pytest.fixture
def task_store(tmp_path: Path):
    database = Database(tmp_path / "eden.db")
    database.initialize()
    repository = TaskRepository(database)
    runtimes = RuntimeSessionRepository(database)
    try:
        yield database, repository, runtimes
    finally:
        database.close()


def test_synthetic_task_is_visibly_marked_in_domain_history_and_checkpoint(task_store):
    _, repository, runtimes = task_store
    clock = FakeClock()
    engine = TaskEngine(repository, runtimes, clock=clock)
    engine.start_runtime()

    task = engine.create_task(
        title="SYNTHETIC TEST — generated checkpoint exercise",
        objective="Exercise generated test steps; no real machine evidence is used.",
        origin=TaskOrigin.SYNTHETIC_TEST,
    )
    assert task.id.startswith("TST-")
    assert task.synthetic
    assert repository.events(task.id)[0].generated_test_data
    assert "generated synthetic test" in repository.events(task.id)[0].message

    task = engine.transition(
        task.id,
        TaskState.OBSERVING,
        message="Started a generated observation step.",
        progress=ProgressUpdate(
            current_phase="Synthetic observation",
            completed_major_steps=[],
            current_operation="Waiting on a generated fixture.",
            eta_status=EtaStatus.RANGE,
            eta_min_seconds=2,
            eta_max_seconds=4,
            eta_basis="Fixed timing from the generated fixture.",
            technical_operation=TechnicalOperation(
                kind="synthetic_wait",
                provider="test_fixture",
                summary="Generated delay; no real command is executed.",
                generated_test_data=True,
            ),
        ),
    )
    clock.advance(3)
    task = engine.checkpoint(
        task.id,
        reason=CheckpointReason.SAFE_BOUNDARY,
        pending_steps=["Generated completion step"],
    )

    assert task.active_elapsed_seconds == pytest.approx(3)
    checkpoint = repository.checkpoints(task.id)[0]
    assert checkpoint.generated_test_data
    assert checkpoint.pending_steps == ["Generated completion step"]


def test_pause_and_cancel_wait_for_safe_boundary_during_active_work(task_store):
    _, repository, runtimes = task_store
    engine = TaskEngine(repository, runtimes, clock=FakeClock())
    engine.start_runtime()
    task = engine.create_task(title="Read-only work", objective="Collect safe evidence.")
    task = engine.transition(task.id, TaskState.OBSERVING, message="Collection started.")

    requested = engine.request_pause(task.id)
    assert requested.state is TaskState.OBSERVING
    assert requested.control_request is TaskControlRequest.PAUSE

    paused = engine.reach_safe_boundary(task.id, pending_steps=["Continue collection"])
    assert paused.state is TaskState.PAUSED
    assert paused.resume_state is TaskState.OBSERVING
    assert paused.control_request is None
    assert repository.checkpoints(task.id)[0].state is TaskState.PAUSED

    resumed = engine.resume(task.id)
    assert resumed.state is TaskState.OBSERVING
    requested = engine.request_cancel(task.id)
    assert requested.state is TaskState.OBSERVING
    canceled = engine.reach_safe_boundary(task.id)
    assert canceled.state is TaskState.CANCELED
    assert canceled.completed_at is not None
    assert canceled.final_summary == "Cancellation request applied at a safe boundary."
    with pytest.raises(TaskTransitionError, match="terminal"):
        engine.transition(task.id, TaskState.OBSERVING, message="Must not restart.")


def test_unfinished_active_task_requires_recovery_after_core_interruption(task_store):
    _, repository, runtimes = task_store
    clock = FakeClock()
    first = TaskEngine(repository, runtimes, clock=clock)
    first_session, _, _ = first.start_runtime()
    task = first.create_task(
        title="Interrupted fixture", objective="Test recovery detection.",
        origin=TaskOrigin.SYNTHETIC_TEST,
    )
    task = first.transition(task.id, TaskState.DIAGNOSING, message="Diagnosis started.")

    clock.advance(10)
    restarted = TaskEngine(repository, runtimes, clock=clock)
    _, interrupted, recovered = restarted.start_runtime()

    assert interrupted is not None
    assert interrupted.id == first_session.id
    assert interrupted.status is RuntimeSessionStatus.INTERRUPTED
    assert [item.id for item in recovered] == [task.id]
    recovered_task = repository.get(task.id)
    assert recovered_task.state is TaskState.RECOVERY_REQUIRED
    assert recovered_task.resume_state is TaskState.DIAGNOSING
    assert repository.checkpoints(task.id)[0].reason is CheckpointReason.RECOVERY
    with pytest.raises(TaskTransitionError, match="reconciled"):
        restarted.resume(task.id)

    reconciled = restarted.reconcile_recovery(
        task.id,
        safe_to_resume=True,
        message="Generated fixture state was reconciled; resumption is safe.",
    )
    assert reconciled.state is TaskState.PAUSED


def test_real_recovered_work_cannot_claim_a_running_worker(task_store):
    _, repository, runtimes = task_store
    engine = TaskEngine(repository, runtimes)
    engine.start_runtime()
    task = engine.create_task(title="Real work", objective="Read-only diagnostic")
    engine.transition(task.id, TaskState.OBSERVING, message="Started.")
    restarted = TaskEngine(repository, runtimes)
    restarted.start_runtime()
    with pytest.raises(TaskTransitionError, match="only synthetic"):
        restarted.reconcile_recovery(task.id, safe_to_resume=True, message="Checked.")
    failed = restarted.reconcile_recovery(
        task.id, safe_to_resume=False, message="Interrupted attempt reviewed; rerun if needed."
    )
    assert failed.state is TaskState.FAILED
    assert failed.final_summary is not None
    assert "rerun" in failed.final_summary


def test_clean_shutdown_is_not_classified_as_a_crash(task_store):
    _, repository, runtimes = task_store
    clock = FakeClock()
    first = TaskEngine(repository, runtimes, clock=clock)
    session, _, _ = first.start_runtime()
    task = first.create_task(title="Clean stop", objective="Test intentional shutdown.")
    task = first.transition(task.id, TaskState.RESEARCHING, message="Research started.")

    checkpointed = first.clean_shutdown(RuntimeStopReason.USER_REQUESTED)
    assert [item.state for item in checkpointed] == [TaskState.PAUSED]
    assert runtimes.get(session.id).status is RuntimeSessionStatus.CLEAN_STOPPED
    assert repository.checkpoints(task.id)[0].reason is CheckpointReason.INTENTIONAL_SHUTDOWN

    second = TaskEngine(repository, runtimes, clock=clock)
    _, interrupted, recovered = second.start_runtime()
    assert interrupted is None
    assert recovered == []
    assert repository.get(task.id).state is TaskState.PAUSED


def test_non_stoppable_segment_is_announced_before_operation_progress(task_store):
    _, repository, runtimes = task_store
    clock = FakeClock()
    engine = TaskEngine(repository, runtimes, clock=clock)
    engine.start_runtime()
    task = engine.create_task(title="Bounded work", objective="Test stop boundaries.")
    task = engine.transition(task.id, TaskState.OBSERVING, message="Ready.")

    operation = TechnicalOperation(
        kind="provider_read",
        summary="Wait for one provider response.",
        interruption_mode=InterruptionMode.SAFE_BOUNDARY_ONLY,
        non_stoppable_reason="The provider call cannot be interrupted safely once sent.",
    )
    update = ProgressUpdate(
            current_phase="Reading provider data",
            completed_major_steps=[],
            technical_operation=operation,
    )
    with pytest.raises(TaskTransitionError, match="announce"):
        engine.record_progress(
            task.id, update, message="Entering a non-stoppable provider segment."
        )
    engine.announce_non_stoppable_segment(task.id, operation)
    announced = repository.events(task.id)[-1]
    assert announced.event_type.value == "non_stoppable_segment_announced"
    assert "next safe boundary" in announced.message
    engine.record_progress(
        task.id, update,
        message="Entering a non-stoppable provider segment.",
    )

    event = repository.events(task.id)[-1]
    assert event.event_type.value == "non_stoppable_segment_entered"
    assert event.progress is not None
    assert event.progress.technical_operation is not None
    assert "cannot be interrupted" in event.progress.technical_operation.non_stoppable_reason

    stopped = engine.hard_stop(
        task.id, message="Hard stop during a safe-boundary-only provider call."
    )
    assert stopped.state is TaskState.RECOVERY_REQUIRED
    assert repository.checkpoints(task.id)[0].reason is CheckpointReason.RECOVERY


def test_task_can_link_to_temporary_identity_and_relink_when_chat_is_saved(task_store):
    _, repository, runtimes = task_store
    clock = FakeClock()
    engine = TaskEngine(repository, runtimes, clock=clock)
    engine.start_runtime()
    task = engine.create_task(title="Linked work", objective="Remain visible in chat.")
    repository.link_conversation(
        TaskConversationLink(
            task_id=task.id,
            conversation_id="TMP-TEST",
            linked_at=clock.now(),
        )
    )

    assert repository.tasks_for_conversation("TMP-TEST") == [task]
    repository.relink_conversation_identity("TMP-TEST", "CHT-SAVED")
    assert repository.tasks_for_conversation("TMP-TEST") == []
    assert repository.conversations_for_task(task.id)[0].conversation_id == "CHT-SAVED"
