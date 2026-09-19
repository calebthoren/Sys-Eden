"""Validated bootstrap settings; loading configuration has no write side effects."""

from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

Budget = Annotated[float, Field(gt=0, allow_inf_nan=False)]


class StorageSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    application_target_gb: Budget = 4
    models_budget_gb: Budget = 12
    reports_memory_db_budget_gb: Budget = 2
    logs_cache_budget_gb: Budget = 2
    telemetry_budget_gb: Budget = 5
    free_space_reserve_gb: Budget = 5
    auto_rebalance: bool = False


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="EDEN_", env_nested_delimiter="__", extra="forbid"
    )

    data_directory: Path = Path("data")
    model_directory: Path = Path("C:/AI/models")
    storage: StorageSettings = Field(default_factory=StorageSettings)


def load_settings() -> Settings:
    """Load defaults with explicit EDEN_ environment overrides; never read .env secrets."""
    return Settings()
