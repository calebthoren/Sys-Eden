"""Validated bootstrap settings; loading configuration has no write side effects."""

from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator
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


class ModelSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Literal["ollama", "fake"] = "ollama"
    endpoint: str = "http://127.0.0.1:11434"
    default_model: str = Field(default="qwen3.5:9b", min_length=1, max_length=500)
    routing_preference: Literal["fast", "balanced", "strong"] = "balanced"
    health_timeout_seconds: float = Field(default=3, gt=0, le=30)
    request_timeout_seconds: float = Field(default=180, gt=0, le=900)
    context_max_characters: int = Field(default=60_000, ge=1_000, le=200_000)
    max_output_tokens: int = Field(default=2048, ge=128, le=32_768)

    @field_validator("endpoint")
    @classmethod
    def require_loopback_endpoint(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError("model endpoint must be an uncredentialed loopback HTTP endpoint")
        return value.rstrip("/")


class CliSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    home_preview_limit: int = Field(default=5, ge=3, le=5)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EDEN_", env_nested_delimiter="__", extra="forbid")

    data_directory: Path = Path("data")
    model_directory: Path = Path("C:/AI/models")
    model: ModelSettings = Field(default_factory=ModelSettings)
    cli: CliSettings = Field(default_factory=CliSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)


def load_settings() -> Settings:
    """Load defaults with explicit EDEN_ environment overrides; never read .env secrets."""
    return Settings()
