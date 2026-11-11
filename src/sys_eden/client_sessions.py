"""In-memory ownership leases for CLI clients and their temporary chats."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from threading import RLock
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from sys_eden.conversation_service import ConversationService
from sys_eden.task_models import Clock, SystemClock


def new_client_id() -> str:
    return f"CLI-{uuid4().hex[:12].upper()}"


class ClientSession(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=new_client_id, min_length=1, max_length=100)
    connected_at: datetime
    last_heartbeat_at: datetime
    disconnected_at: datetime | None = None


class ClientCloseAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_id: str
    active_temporary_ids: list[str] = Field(default_factory=list)
    meaningful_temporary_ids: list[str] = Field(default_factory=list)

    @property
    def requires_warning(self) -> bool:
        return bool(self.active_temporary_ids or self.meaningful_temporary_ids)


class ClientSessionRegistry:
    """Core-owned leases; losing one client never stops Core or another client."""

    def __init__(
        self,
        conversations: ConversationService,
        *,
        clock: Clock | None = None,
        lease_timeout: timedelta = timedelta(seconds=15),
        disconnect_grace: timedelta = timedelta(seconds=10),
        stop_temporary_work: Callable[[str], None] | None = None,
    ) -> None:
        self.conversations = conversations
        self.clock = clock or SystemClock()
        self.lease_timeout = lease_timeout
        self.disconnect_grace = disconnect_grace
        self.stop_temporary_work = stop_temporary_work
        self._sessions: dict[str, ClientSession] = {}
        self._lock = RLock()

    def connect(self) -> ClientSession:
        now = self.clock.now()
        session = ClientSession(connected_at=now, last_heartbeat_at=now)
        with self._lock:
            self._sessions[session.id] = session
        return session

    def heartbeat(self, client_id: str) -> ClientSession:
        with self._lock:
            session = self._session(client_id)
            if session.disconnected_at is not None:
                raise KeyError(f"CLI client session is closed: {client_id}")
            updated = session.model_copy(
                update={"last_heartbeat_at": self.clock.now()}
            )
            self._sessions[client_id] = updated
        return updated

    def assess_close(self, client_id: str) -> ClientCloseAssessment:
        with self._lock:
            self._session(client_id)
        temporary = self.conversations.temporary_for_client(client_id)
        active = {
            aggregate.conversation.id
            for aggregate in self.conversations.active_temporary_for_client(client_id)
        }
        meaningful = [
            aggregate.conversation.id
            for aggregate in temporary
            if aggregate.messages and aggregate.conversation.id not in active
        ]
        return ClientCloseAssessment(
            client_id=client_id,
            active_temporary_ids=sorted(active),
            meaningful_temporary_ids=sorted(meaningful),
        )

    def disconnect(self, client_id: str) -> ClientSession:
        with self._lock:
            session = self._session(client_id)
            updated = session.model_copy(update={"disconnected_at": self.clock.now()})
            self._sessions[client_id] = updated
        self.conversations.forget_deleted_for_client(client_id)
        return updated

    def require_connected(self, client_id: str) -> None:
        with self._lock:
            session = self._session(client_id)
            if session.disconnected_at is not None:
                raise KeyError(f"CLI client session is closed: {client_id}")

    def expire_disconnected(self) -> dict[str, list[str]]:
        """Discard vanished-client temporary chats after a short Core-owned grace."""
        now = self.clock.now()
        expired: dict[str, list[str]] = {}
        with self._lock:
            for client_id, session in list(self._sessions.items()):
                disconnected_at = session.disconnected_at
                stale_at = session.last_heartbeat_at + self.lease_timeout
                cleanup_at = (
                    disconnected_at + self.disconnect_grace
                    if disconnected_at is not None
                    else stale_at + self.disconnect_grace
                )
                if now < cleanup_at:
                    continue
                if self.stop_temporary_work is not None:
                    for aggregate in self.conversations.active_temporary_for_client(
                        client_id
                    ):
                        self.stop_temporary_work(aggregate.conversation.id)
                expired[client_id] = self.conversations.discard_client_temporary(
                    client_id, include_working=True
                )
                self.conversations.forget_deleted_for_client(client_id)
                del self._sessions[client_id]
        return expired

    def _session(self, client_id: str) -> ClientSession:
        try:
            return self._sessions[client_id]
        except KeyError as error:
            raise KeyError(f"CLI client session not found: {client_id}") from error
