"""Transactional persistence for durable tasks and Core runtime sessions."""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast

from sqlalchemy import text
from sqlalchemy.engine import CursorResult, RowMapping
from sqlalchemy.exc import IntegrityError

from sys_eden.storage import Database
from sys_eden.task_models import (
    RuntimeSession,
    RuntimeSessionStatus,
    RuntimeStopReason,
    Task,
    TaskCheckpoint,
    TaskControlRequest,
    TaskConversationLink,
    TaskConversationRole,
    TaskEvent,
    TaskEventType,
    TaskOrigin,
    TaskProgress,
    TaskState,
)


class TaskRepositoryError(Exception):
    """Base error for durable task persistence."""


class TaskNotFound(TaskRepositoryError):
    pass


class TaskConflict(TaskRepositoryError):
    pass


class RuntimeSessionError(TaskRepositoryError):
    pass


def _timestamp(value: datetime) -> str:
    return value.isoformat()


def _datetime(value: str | datetime) -> datetime:
    return value if isinstance(value, datetime) else datetime.fromisoformat(value)


def _progress_json(progress: TaskProgress | None) -> str | None:
    return progress.model_dump_json() if progress is not None else None


class TaskRepository:
    def __init__(self, database: Database):
        self.database = database

    def create(self, task: Task, event: TaskEvent) -> Task:
        if event.task_id != task.id or event.sequence != 1:
            raise ValueError("initial event must be sequence one for the new task")
        try:
            with self.database.session() as session:
                session.execute(
                    text(
                        """
                        INSERT INTO tasks (
                            id, schema_version, revision, title, objective, origin, state,
                            resume_state, control_request, created_at, updated_at, started_at,
                            completed_at, active_elapsed_seconds, progress_json, active_report_id,
                            runtime_session_id, last_event_sequence, last_checkpoint_sequence,
                            final_summary
                        ) VALUES (
                            :id, :schema_version, :revision, :title, :objective, :origin, :state,
                            :resume_state, :control_request, :created_at, :updated_at, :started_at,
                            :completed_at, :active_elapsed_seconds, :progress_json,
                            :active_report_id, :runtime_session_id, :last_event_sequence,
                            :last_checkpoint_sequence, :final_summary
                        )
                        """
                    ),
                    self._task_parameters(task),
                )
                self._insert_event(session, event)
        except IntegrityError as error:
            raise TaskConflict(f"Task could not be created: {task.id}") from error
        return task

    def update(
        self,
        task: Task,
        *,
        expected_revision: int,
        event: TaskEvent,
        checkpoint: TaskCheckpoint | None = None,
    ) -> Task:
        if event.task_id != task.id or event.sequence != task.last_event_sequence:
            raise ValueError("event sequence must match the updated task")
        if checkpoint is not None and (
            checkpoint.task_id != task.id
            or checkpoint.sequence != task.last_checkpoint_sequence
        ):
            raise ValueError("checkpoint sequence must match the updated task")
        try:
            with self.database.session() as session:
                result = cast(
                    CursorResult[Any],
                    session.execute(
                        text(
                            """
                            UPDATE tasks SET
                                schema_version = :schema_version,
                                revision = :revision,
                                title = :title,
                                objective = :objective,
                                origin = :origin,
                                state = :state,
                                resume_state = :resume_state,
                                control_request = :control_request,
                                updated_at = :updated_at,
                                started_at = :started_at,
                                completed_at = :completed_at,
                                active_elapsed_seconds = :active_elapsed_seconds,
                                progress_json = :progress_json,
                                active_report_id = :active_report_id,
                                runtime_session_id = :runtime_session_id,
                                last_event_sequence = :last_event_sequence,
                                last_checkpoint_sequence = :last_checkpoint_sequence,
                                final_summary = :final_summary
                            WHERE id = :id AND revision = :expected_revision
                            """
                        ),
                        {**self._task_parameters(task), "expected_revision": expected_revision},
                    ),
                )
                if result.rowcount != 1:
                    raise TaskConflict(
                        f"Task revision changed or task is missing: {task.id}"
                    )
                self._insert_event(session, event)
                if checkpoint is not None:
                    self._insert_checkpoint(session, checkpoint)
        except IntegrityError as error:
            raise TaskConflict(f"Task update violated persistence constraints: {task.id}") from error
        return task

    def get(self, task_id: str) -> Task:
        with self.database.session() as session:
            row = (
                session.execute(text("SELECT * FROM tasks WHERE id = :id"), {"id": task_id})
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise TaskNotFound(f"Task not found: {task_id}")
        return self._task_from_row(row)

    def list(self, *, states: set[TaskState] | None = None, limit: int = 100) -> list[Task]:
        if limit < 1 or limit > 1000:
            raise ValueError("task list limit must be between 1 and 1000")
        parameters: dict[str, object] = {"limit": limit}
        where = ""
        if states:
            ordered = sorted(state.value for state in states)
            parameters.update({f"state_{index}": value for index, value in enumerate(ordered)})
            placeholders = ", ".join(f":state_{index}" for index in range(len(ordered)))
            where = f"WHERE state IN ({placeholders})"
        with self.database.session() as session:
            rows = session.execute(
                text(
                    f"SELECT * FROM tasks {where} "
                    "ORDER BY updated_at DESC, id LIMIT :limit"
                ),
                parameters,
            ).mappings()
            return [self._task_from_row(row) for row in rows]

    def list_for_runtime(
        self, runtime_session_id: str, *, states: set[TaskState]
    ) -> list[Task]:
        if not states:
            return []
        ordered = sorted(state.value for state in states)
        parameters: dict[str, object] = {"runtime_session_id": runtime_session_id}
        parameters.update({f"state_{index}": value for index, value in enumerate(ordered)})
        placeholders = ", ".join(f":state_{index}" for index in range(len(ordered)))
        with self.database.session() as session:
            rows = session.execute(
                text(
                    "SELECT * FROM tasks WHERE runtime_session_id = :runtime_session_id "
                    f"AND state IN ({placeholders}) ORDER BY updated_at, id"
                ),
                parameters,
            ).mappings()
            return [self._task_from_row(row) for row in rows]

    def events(self, task_id: str, *, after_sequence: int = 0) -> list[TaskEvent]:
        with self.database.session() as session:
            rows = session.execute(
                text(
                    "SELECT * FROM task_events WHERE task_id = :task_id "
                    "AND sequence > :after_sequence ORDER BY sequence"
                ),
                {"task_id": task_id, "after_sequence": after_sequence},
            ).mappings()
            return [self._event_from_row(row) for row in rows]

    def checkpoints(self, task_id: str) -> list[TaskCheckpoint]:
        with self.database.session() as session:
            rows = session.execute(
                text(
                    "SELECT data_json FROM task_checkpoints WHERE task_id = :task_id "
                    "ORDER BY sequence"
                ),
                {"task_id": task_id},
            ).scalars()
            return [TaskCheckpoint.model_validate_json(value) for value in rows]

    def link_conversation(self, link: TaskConversationLink) -> TaskConversationLink:
        """Link a task to either a durable CHT identity or a live TMP identity."""
        self.get(link.task_id)
        try:
            with self.database.session() as session:
                if link.role is TaskConversationRole.PRIMARY:
                    session.execute(
                        text(
                            "DELETE FROM task_conversation_links "
                            "WHERE task_id = :task_id AND relationship_role = 'primary'"
                        ),
                        {"task_id": link.task_id},
                    )
                session.execute(
                    text(
                        "INSERT INTO task_conversation_links "
                        "(task_id, conversation_id, relationship_role, linked_at) "
                        "VALUES (:task_id, :conversation_id, :relationship_role, :linked_at) "
                        "ON CONFLICT(task_id, conversation_id) DO UPDATE SET "
                        "relationship_role = excluded.relationship_role, "
                        "linked_at = excluded.linked_at"
                    ),
                    {
                        "task_id": link.task_id,
                        "conversation_id": link.conversation_id,
                        "relationship_role": link.role.value,
                        "linked_at": _timestamp(link.linked_at),
                    },
                )
        except IntegrityError as error:
            raise TaskConflict("Task/conversation link could not be stored") from error
        return link

    def conversations_for_task(self, task_id: str) -> list[TaskConversationLink]:
        with self.database.session() as session:
            rows = session.execute(
                text(
                    "SELECT * FROM task_conversation_links WHERE task_id = :task_id "
                    "ORDER BY CASE relationship_role WHEN 'primary' THEN 0 ELSE 1 END, "
                    "linked_at, conversation_id"
                ),
                {"task_id": task_id},
            ).mappings()
            return [self._conversation_link_from_row(row) for row in rows]

    def tasks_for_conversation(self, conversation_id: str) -> list[Task]:
        with self.database.session() as session:
            rows = session.execute(
                text(
                    "SELECT tasks.* FROM tasks JOIN task_conversation_links AS links "
                    "ON links.task_id = tasks.id WHERE links.conversation_id = :conversation_id "
                    "ORDER BY tasks.updated_at DESC, tasks.id"
                ),
                {"conversation_id": conversation_id},
            ).mappings()
            return [self._task_from_row(row) for row in rows]

    def relink_conversation_identity(self, old_id: str, new_id: str) -> None:
        """Replace a TMP identity after the user explicitly saves that conversation."""
        with self.database.session() as session:
            session.execute(
                text(
                    "UPDATE task_conversation_links SET conversation_id = :new_id "
                    "WHERE conversation_id = :old_id"
                ),
                {"old_id": old_id, "new_id": new_id},
            )

    @staticmethod
    def _task_parameters(task: Task) -> dict[str, object]:
        return {
            "id": task.id,
            "schema_version": task.schema_version,
            "revision": task.revision,
            "title": task.title,
            "objective": task.objective,
            "origin": task.origin.value,
            "state": task.state.value,
            "resume_state": task.resume_state.value if task.resume_state else None,
            "control_request": task.control_request.value if task.control_request else None,
            "created_at": _timestamp(task.created_at),
            "updated_at": _timestamp(task.updated_at),
            "started_at": _timestamp(task.started_at) if task.started_at else None,
            "completed_at": _timestamp(task.completed_at) if task.completed_at else None,
            "active_elapsed_seconds": task.active_elapsed_seconds,
            "progress_json": _progress_json(task.progress),
            "active_report_id": task.active_report_id,
            "runtime_session_id": task.runtime_session_id,
            "last_event_sequence": task.last_event_sequence,
            "last_checkpoint_sequence": task.last_checkpoint_sequence,
            "final_summary": task.final_summary,
        }

    @staticmethod
    def _insert_event(session: Any, event: TaskEvent) -> None:
        session.execute(
            text(
                """
                INSERT INTO task_events (
                    id, task_id, sequence, event_type, occurred_at, message, from_state,
                    to_state, progress_json, runtime_session_id, generated_test_data
                ) VALUES (
                    :id, :task_id, :sequence, :event_type, :occurred_at, :message,
                    :from_state, :to_state, :progress_json, :runtime_session_id,
                    :generated_test_data
                )
                """
            ),
            {
                "id": event.id,
                "task_id": event.task_id,
                "sequence": event.sequence,
                "event_type": event.event_type.value,
                "occurred_at": _timestamp(event.occurred_at),
                "message": event.message,
                "from_state": event.from_state.value if event.from_state else None,
                "to_state": event.to_state.value if event.to_state else None,
                "progress_json": _progress_json(event.progress),
                "runtime_session_id": event.runtime_session_id,
                "generated_test_data": event.generated_test_data,
            },
        )

    @staticmethod
    def _insert_checkpoint(session: Any, checkpoint: TaskCheckpoint) -> None:
        session.execute(
            text(
                """
                INSERT INTO task_checkpoints (
                    id, task_id, sequence, reason, state, created_at, data_json,
                    generated_test_data
                ) VALUES (
                    :id, :task_id, :sequence, :reason, :state, :created_at, :data_json,
                    :generated_test_data
                )
                """
            ),
            {
                "id": checkpoint.id,
                "task_id": checkpoint.task_id,
                "sequence": checkpoint.sequence,
                "reason": checkpoint.reason.value,
                "state": checkpoint.state.value,
                "created_at": _timestamp(checkpoint.created_at),
                "data_json": checkpoint.model_dump_json(),
                "generated_test_data": checkpoint.generated_test_data,
            },
        )

    @staticmethod
    def _task_from_row(row: RowMapping) -> Task:
        return Task(
            id=row["id"],
            schema_version=row["schema_version"],
            revision=row["revision"],
            title=row["title"],
            objective=row["objective"],
            origin=TaskOrigin(row["origin"]),
            state=TaskState(row["state"]),
            resume_state=TaskState(row["resume_state"]) if row["resume_state"] else None,
            control_request=(
                TaskControlRequest(row["control_request"]) if row["control_request"] else None
            ),
            created_at=_datetime(row["created_at"]),
            updated_at=_datetime(row["updated_at"]),
            started_at=_datetime(row["started_at"]) if row["started_at"] else None,
            completed_at=_datetime(row["completed_at"]) if row["completed_at"] else None,
            active_elapsed_seconds=row["active_elapsed_seconds"],
            progress=(
                TaskProgress.model_validate_json(row["progress_json"])
                if row["progress_json"]
                else None
            ),
            active_report_id=row["active_report_id"],
            runtime_session_id=row["runtime_session_id"],
            last_event_sequence=row["last_event_sequence"],
            last_checkpoint_sequence=row["last_checkpoint_sequence"],
            final_summary=row["final_summary"],
        )

    @staticmethod
    def _event_from_row(row: RowMapping) -> TaskEvent:
        return TaskEvent(
            id=row["id"],
            task_id=row["task_id"],
            sequence=row["sequence"],
            event_type=TaskEventType(row["event_type"]),
            occurred_at=_datetime(row["occurred_at"]),
            message=row["message"],
            from_state=TaskState(row["from_state"]) if row["from_state"] else None,
            to_state=TaskState(row["to_state"]) if row["to_state"] else None,
            progress=(
                TaskProgress.model_validate_json(row["progress_json"])
                if row["progress_json"]
                else None
            ),
            runtime_session_id=row["runtime_session_id"],
            generated_test_data=bool(row["generated_test_data"]),
        )

    @staticmethod
    def _conversation_link_from_row(row: RowMapping) -> TaskConversationLink:
        return TaskConversationLink(
            task_id=row["task_id"],
            conversation_id=row["conversation_id"],
            role=TaskConversationRole(row["relationship_role"]),
            linked_at=_datetime(row["linked_at"]),
        )


class RuntimeSessionRepository:
    def __init__(self, database: Database):
        self.database = database

    def begin(self, session: RuntimeSession) -> tuple[RuntimeSession, RuntimeSession | None]:
        if session.status is not RuntimeSessionStatus.RUNNING:
            raise ValueError("new runtime session must be running")
        interrupted: RuntimeSession | None = None
        try:
            with self.database.session() as database_session:
                previous_row = (
                    database_session.execute(
                        text(
                            "SELECT * FROM core_runtime_sessions "
                            "ORDER BY started_at DESC, id DESC LIMIT 1"
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if previous_row is not None and previous_row["status"] == "running":
                    interrupted = self._from_row(previous_row).model_copy(
                        update={
                            "status": RuntimeSessionStatus.INTERRUPTED,
                            "interrupted_at": session.started_at,
                        }
                    )
                    database_session.execute(
                        text(
                            "UPDATE core_runtime_sessions SET status = 'interrupted', "
                            "interrupted_at = :interrupted_at WHERE id = :id AND status = 'running'"
                        ),
                        {
                            "id": interrupted.id,
                            "interrupted_at": _timestamp(session.started_at),
                        },
                    )
                database_session.execute(
                    text(
                        "INSERT INTO core_runtime_sessions "
                        "(id, status, started_at, stopped_at, stop_reason, interrupted_at) "
                        "VALUES (:id, :status, :started_at, NULL, NULL, NULL)"
                    ),
                    {
                        "id": session.id,
                        "status": session.status.value,
                        "started_at": _timestamp(session.started_at),
                    },
                )
        except IntegrityError as error:
            raise RuntimeSessionError("Core runtime session could not be started") from error
        return session, interrupted

    def clean_stop(
        self, session_id: str, *, stopped_at: datetime, reason: RuntimeStopReason
    ) -> RuntimeSession:
        with self.database.session() as session:
            result = cast(
                CursorResult[Any],
                session.execute(
                    text(
                        "UPDATE core_runtime_sessions SET status = 'clean_stopped', "
                        "stopped_at = :stopped_at, stop_reason = :stop_reason "
                        "WHERE id = :id AND status = 'running'"
                    ),
                    {
                        "id": session_id,
                        "stopped_at": _timestamp(stopped_at),
                        "stop_reason": reason.value,
                    },
                ),
            )
            if result.rowcount != 1:
                raise RuntimeSessionError("Runtime session is missing or already stopped")
        return self.get(session_id)

    def get(self, session_id: str) -> RuntimeSession:
        with self.database.session() as session:
            row = (
                session.execute(
                    text("SELECT * FROM core_runtime_sessions WHERE id = :id"),
                    {"id": session_id},
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise RuntimeSessionError(f"Runtime session not found: {session_id}")
        return self._from_row(row)

    @staticmethod
    def _from_row(row: RowMapping) -> RuntimeSession:
        return RuntimeSession(
            id=row["id"],
            status=RuntimeSessionStatus(row["status"]),
            started_at=_datetime(row["started_at"]),
            stopped_at=_datetime(row["stopped_at"]) if row["stopped_at"] else None,
            stop_reason=RuntimeStopReason(row["stop_reason"]) if row["stop_reason"] else None,
            interrupted_at=(
                _datetime(row["interrupted_at"]) if row["interrupted_at"] else None
            ),
        )
