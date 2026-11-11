"""Explicitly labeled generated tasks for safe task-engine acceptance testing."""

from __future__ import annotations

from sys_eden.task_engine import ProgressUpdate, TaskEngine
from sys_eden.task_models import EtaStatus, Task, TaskOrigin, TaskState, TechnicalOperation


class SyntheticTaskService:
    """Never runs automatically and never represents real machine activity."""

    def __init__(self, engine: TaskEngine):
        self.engine = engine

    def create_checkpoint_demo(self) -> Task:
        task = self.engine.create_task(
            title="SYNTHETIC TEST — durable checkpoint demonstration",
            objective=(
                "Exercise generated task progress, controls, checkpoints, and recovery. "
                "No real machine evidence or system action is involved."
            ),
            origin=TaskOrigin.SYNTHETIC_TEST,
        )
        return self.engine.transition(
            task.id,
            TaskState.OBSERVING,
            message="SYNTHETIC TEST: started generated fixture observation.",
            progress=ProgressUpdate(
                current_phase="SYNTHETIC TEST — fixture observation",
                completed_major_steps=[],
                current_operation="Read generated fixture record 1 of 2.",
                eta_status=EtaStatus.RANGE,
                eta_min_seconds=2,
                eta_max_seconds=5,
                eta_basis="Fixed generated fixture with two known steps.",
                technical_operation=TechnicalOperation(
                    kind="synthetic_fixture_read",
                    provider="generated_test_fixture",
                    tool="none",
                    summary="Reads generated in-memory test data; no system query is performed.",
                    generated_test_data=True,
                ),
            ),
        )

    def advance(self, task_id: str) -> Task:
        task = self.engine.repository.get(task_id)
        if not task.synthetic:
            raise ValueError("SyntheticTaskService refuses to operate on a real task")
        if task.control_request is not None:
            return self.engine.reach_safe_boundary(
                task_id, pending_steps=["Generated fixture completion"]
            )
        if task.state is TaskState.OBSERVING:
            return self.engine.transition(
                task_id,
                TaskState.DIAGNOSING,
                message="SYNTHETIC TEST: generated observation step completed.",
                progress=ProgressUpdate(
                    current_phase="SYNTHETIC TEST — fixture interpretation",
                    completed_major_steps=["Generated fixture observation"],
                    current_operation="Interpret generated fixture result.",
                    eta_status=EtaStatus.RANGE,
                    eta_min_seconds=1,
                    eta_max_seconds=3,
                    eta_basis="One generated fixture step remains.",
                    technical_operation=TechnicalOperation(
                        kind="synthetic_fixture_interpretation",
                        provider="generated_test_fixture",
                        summary="Interprets invented test data only.",
                        generated_test_data=True,
                    ),
                ),
            )
        if task.state is TaskState.DIAGNOSING:
            return self.engine.transition(
                task_id,
                TaskState.COMPLETED,
                message="SYNTHETIC TEST: all generated fixture steps completed.",
                progress=ProgressUpdate(
                    current_phase="SYNTHETIC TEST — complete",
                    completed_major_steps=[
                        "Generated fixture observation",
                        "Generated fixture interpretation",
                    ],
                    current_operation=None,
                    eta_status=EtaStatus.UNAVAILABLE,
                    eta_basis="The generated test task is complete.",
                ),
            )
        return task
