"""UI-independent client contract for the local Eden Core."""

from __future__ import annotations

import asyncio
from typing import Protocol

from sys_eden.conversation_models import ConversationAggregate, ConversationRole
from sys_eden.core_application import CoreApplication, CoreRuntimeStatus
from sys_eden.storage_status import StorageRecommendation, StorageStatus
from sys_eden.task_models import Task, TaskEvent


class CoreUnavailable(ConnectionError):
    pass


class CoreClient(Protocol):
    async def status(self) -> CoreRuntimeStatus: ...

    async def start_core(self) -> CoreRuntimeStatus: ...

    async def stop_core(self) -> CoreRuntimeStatus: ...

    async def list_tasks(self) -> list[Task]: ...

    async def get_task(self, task_id: str) -> Task: ...

    async def task_events(self, task_id: str, *, after_sequence: int = 0) -> list[TaskEvent]: ...

    async def pause_task(self, task_id: str) -> Task: ...

    async def resume_task(self, task_id: str) -> Task: ...

    async def cancel_task(self, task_id: str) -> Task: ...

    async def storage_status(self) -> StorageStatus: ...

    async def storage_recommendations(self) -> list[StorageRecommendation]: ...


class InProcessCoreClient:
    """Permanent test/development adapter; production transport is selected separately."""

    def __init__(self, application: CoreApplication):
        self.application = application

    async def status(self) -> CoreRuntimeStatus:
        return self.application.status

    async def start_core(self) -> CoreRuntimeStatus:
        return await asyncio.to_thread(self.application.start)

    async def stop_core(self) -> CoreRuntimeStatus:
        self._require_running()
        return await asyncio.to_thread(self.application.stop)

    async def list_tasks(self) -> list[Task]:
        self._require_running()
        return await asyncio.to_thread(self.application.tasks.list)

    async def get_task(self, task_id: str) -> Task:
        self._require_running()
        return await asyncio.to_thread(self.application.tasks.get, task_id)

    async def task_events(
        self, task_id: str, *, after_sequence: int = 0
    ) -> list[TaskEvent]:
        self._require_running()
        return await asyncio.to_thread(
            self.application.tasks.events,
            task_id,
            after_sequence=after_sequence,
        )

    async def pause_task(self, task_id: str) -> Task:
        self._require_running()
        return await asyncio.to_thread(self.application.task_engine.request_pause, task_id)

    async def resume_task(self, task_id: str) -> Task:
        self._require_running()
        return await asyncio.to_thread(self.application.task_engine.resume, task_id)

    async def cancel_task(self, task_id: str) -> Task:
        self._require_running()
        return await asyncio.to_thread(self.application.task_engine.request_cancel, task_id)

    async def create_saved_conversation(self, title: str) -> ConversationAggregate:
        self._require_running()
        return await asyncio.to_thread(
            self.application.conversation_service.create_saved, title=title
        )

    async def append_conversation(
        self, conversation_id: str, *, role: ConversationRole, content: str
    ) -> ConversationAggregate:
        self._require_running()
        return await asyncio.to_thread(
            self.application.conversation_service.append,
            conversation_id,
            role=role,
            content=content,
        )

    async def storage_status(self) -> StorageStatus:
        self._require_running()
        return await asyncio.to_thread(self.application.storage_status.status)

    async def storage_recommendations(self) -> list[StorageRecommendation]:
        self._require_running()
        return await asyncio.to_thread(self.application.storage_status.recommendations)

    def _require_running(self) -> None:
        if self.application.status.state.value != "running":
            raise CoreUnavailable(
                "Eden Core is stopped. Starting the client does not start Core automatically."
            )
