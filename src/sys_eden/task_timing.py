"""Conservative estimates from completed, comparable real task operations."""

from __future__ import annotations

from dataclasses import dataclass

from sys_eden.task_models import TaskState, TechnicalOperation
from sys_eden.task_repository import TaskRepository


@dataclass(frozen=True)
class OperationEstimate:
    minimum_seconds: float
    maximum_seconds: float
    basis: str


class TaskTimingEstimator:
    """Use durable events, excluding fixtures, failed work and incompatible workloads."""

    def __init__(self, repository: TaskRepository) -> None:
        self.repository = repository

    def estimate(self, operation: TechnicalOperation) -> OperationEstimate | None:
        samples: list[float] = []
        for task in self.repository.list(limit=100):
            if task.synthetic or task.state is not TaskState.COMPLETED:
                continue
            events = self.repository.events(task.id)
            started = None
            for event in events:
                progress = event.progress
                if progress is None:
                    continue
                if started is not None and (
                    progress.technical_operation != started.technical_operation
                    or event.to_state is TaskState.COMPLETED
                ):
                    previous = started.technical_operation
                    duration = progress.active_elapsed_seconds - started.active_elapsed_seconds
                    if previous is not None and self._comparable(previous, operation) and duration > 0:
                        samples.append(duration)
                        break  # One independent sample per completed task.
                    started = None
                if started is None and progress.technical_operation is not None:
                    started = progress
            if len(samples) >= 10:
                break
        if len(samples) < 3 or max(samples) > min(samples) * 4:
            return None
        return OperationEstimate(
            minimum_seconds=max(0.1, min(samples) * 0.75),
            maximum_seconds=max(samples) * 1.5,
            basis=(
                f"Current operation only: {len(samples)} completed comparable local operations. "
                "The range includes timing variation; later steps are not estimated."
            ),
        )

    @staticmethod
    def _comparable(previous: TechnicalOperation, current: TechnicalOperation) -> bool:
        if previous.generated_test_data or current.generated_test_data:
            return False
        if (previous.kind, previous.provider, previous.tool, previous.model_id, previous.model_loaded,
                previous.workload_key) != (
            current.kind, current.provider, current.tool, current.model_id, current.model_loaded,
            current.workload_key
        ):
            return False
        left, right = previous.context_characters, current.context_characters
        if left is None or right is None:
            return left is right
        return max(left, right) <= max(1, min(left, right)) * 1.5
