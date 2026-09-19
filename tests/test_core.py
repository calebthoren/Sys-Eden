import asyncio
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from sys_eden.cli import app
from sys_eden.config import Settings
from sys_eden.core import Core
from sys_eden.events import Event, EventBus
from sys_eden.models import ProviderHealth


def test_health_cli_bootstraps_fresh_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("EDEN_DATA_DIRECTORY", str(tmp_path / "data"))
    result = CliRunner().invoke(app, ["health"])
    assert result.exit_code == 0, result.output
    health = json.loads(result.stdout)
    assert health["core"] == "ok"
    assert health["database"] == "ok"
    assert health["configuration"] == "ok"
    assert health["model_provider"]["simulated"]
    assert (tmp_path / "data" / "eden.db").exists()


def test_invalid_config_is_safe_and_nonzero(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("EDEN_STORAGE__MODELS_BUDGET_GB", "private-invalid-value")
    result = CliRunner().invoke(app, ["health"])
    assert result.exit_code == 1
    assert json.loads(result.stdout)["configuration"] == "error"
    assert "private-invalid-value" not in result.output


def test_storage_failure_is_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / "file"
    path.write_text("fixture")
    monkeypatch.setenv("EDEN_DATA_DIRECTORY", str(path))
    result = CliRunner().invoke(app, ["health"])
    assert result.exit_code == 1
    assert json.loads(result.stdout)["database"] == "error"


@pytest.mark.asyncio
async def test_provider_failure_degrades_health(tmp_path: Path):
    class UnavailableProvider:
        async def health(self) -> ProviderHealth:
            raise OSError("private adapter details")

    summary = await Core(Settings(data_directory=tmp_path), UnavailableProvider()).health()
    assert summary.core == "degraded"
    assert not summary.model_provider.available
    assert "private" not in summary.model_dump_json()


@pytest.mark.asyncio
async def test_event_delivery_unsubscribe_and_failure():
    bus = EventBus(timeout_seconds=0.01)
    received: list[Event] = []

    async def listener(event: Event):
        received.append(event)

    unsubscribe = bus.subscribe(listener)
    event = Event(event_type="test")
    await bus.publish(event)
    unsubscribe()
    unsubscribe()
    await bus.publish(event)
    assert received == [event]

    async def stalled(event: Event):
        await asyncio.Event().wait()

    bus.subscribe(stalled)
    with pytest.raises(TimeoutError):
        await bus.publish(event)
