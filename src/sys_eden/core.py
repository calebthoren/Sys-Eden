"""User-context Core bootstrap and health; no platform mutation authority."""

import asyncio
import sqlite3
from pathlib import Path

from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from sys_eden.config import Settings
from sys_eden.events import Event, EventBus
from sys_eden.models import FakeModelProvider, ModelProvider, ProviderHealth
from sys_eden.storage import Database, StorageError


class HealthSummary(BaseModel):
    core: str
    configuration: str = "ok"
    database: str
    model_provider: ProviderHealth
    data_directory: Path


class Core:
    def __init__(self, settings: Settings, provider: ModelProvider | None = None):
        self.settings = settings
        self.provider = provider if provider is not None else FakeModelProvider()
        self.events = EventBus()

    def _database_health(self) -> str:
        database = Database(self.settings.data_directory / "eden.db")
        try:
            database.initialize()
            return "ok" if database.healthy() else "error"
        except (OSError, SQLAlchemyError, sqlite3.Error, StorageError):
            return "error"
        finally:
            database.close()

    async def health(self) -> HealthSummary:
        database = await asyncio.to_thread(self._database_health)
        try:
            async with asyncio.timeout(5):
                provider = await self.provider.health()
        except (OSError, TimeoutError):
            provider = ProviderHealth(provider="unavailable", available=False)
        summary = HealthSummary(
            core="ok" if database == "ok" and provider.available else "degraded",
            database=database,
            model_provider=provider,
            data_directory=self.settings.data_directory.resolve(),
        )
        await self.events.publish(Event(event_type="core.health_checked"))
        return summary
