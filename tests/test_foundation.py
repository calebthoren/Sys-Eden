import io
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from sys_eden.config import Settings, StorageSettings, load_settings
from sys_eden.logging import configure_logging


def test_environment_overrides_preserve_independent_budgets(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("EDEN_STORAGE__MODELS_BUDGET_GB", "7.5")
    monkeypatch.setenv("EDEN_DATA_DIRECTORY", "fixture-data")
    settings = load_settings()
    assert settings.storage.models_budget_gb == 7.5
    assert settings.storage.telemetry_budget_gb == 5
    assert settings.storage.free_space_reserve_gb == 5
    assert not settings.storage.auto_rebalance
    assert settings.data_directory == Path("fixture-data")


@pytest.mark.parametrize("value", [0, -1, float("inf"), float("nan")])
def test_invalid_budget_rejected(value: float):
    with pytest.raises(ValidationError):
        StorageSettings(models_budget_gb=value)


def test_config_does_not_create_directory(tmp_path: Path):
    path = tmp_path / "not-created"
    Settings(data_directory=path)
    assert not path.exists()


def test_structured_logging_does_not_duplicate_or_emit_arbitrary_extras():
    stream = io.StringIO()
    configure_logging(stream)
    logger = configure_logging(stream)
    logger.info("Core initialized", extra={"event_type": "core.ready", "secret": "private"})
    lines = stream.getvalue().splitlines()
    assert len(lines) == 1
    event = json.loads(lines[0])
    assert event["event_type"] == "core.ready"
    assert event["task_id"] is None
    assert event["timestamp"].endswith("+00:00")
    assert "private" not in lines[0]
