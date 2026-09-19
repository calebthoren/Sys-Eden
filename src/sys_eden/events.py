"""In-process event delivery; durable task events belong to the task milestone."""

import asyncio
from collections.abc import Awaitable, Callable

from pydantic import BaseModel


class Event(BaseModel):
    event_type: str


type Handler = Callable[[Event], Awaitable[None]]


class EventBus:
    def __init__(self, timeout_seconds: float = 5):
        self._handlers: list[Handler] = []
        self._timeout = timeout_seconds

    def subscribe(self, handler: Handler) -> Callable[[], None]:
        self._handlers.append(handler)

        def unsubscribe() -> None:
            if handler in self._handlers:
                self._handlers.remove(handler)

        return unsubscribe

    async def publish(self, event: Event) -> None:
        """Deliver in registration order; surface failures and propagate cancellation."""
        for handler in tuple(self._handlers):
            async with asyncio.timeout(self._timeout):
                await handler(event)
