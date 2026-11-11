"""Stable JSON envelope shared by direct commands, the CLI, and future UIs."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class JsonAssociations(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_id: str | None = None
    task_id: str | None = None
    report_id: str | None = None


class JsonProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    synthetic: bool = False
    contains_synthetic: bool = False
    source: str | None = Field(default=None, max_length=200)


class JsonError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(pattern=r"^[a-z][a-z0-9_.-]*$", max_length=100)
    message: str = Field(min_length=1, max_length=4000)
    retryable: bool = False


class EdenJsonEnvelope[JsonData](BaseModel):
    """Version the stable envelope separately from each operation payload."""

    model_config = ConfigDict(extra="allow")

    eden_json: Literal[1] = 1
    type: str = Field(pattern=r"^[a-z][a-z0-9_.-]*$", max_length=100)
    data_version: int = Field(default=1, ge=1)
    status: Literal["success", "partial", "error"]
    request_id: str = Field(min_length=1, max_length=100)
    generated_at: datetime
    associations: JsonAssociations = Field(default_factory=JsonAssociations)
    provenance: JsonProvenance = Field(default_factory=JsonProvenance)
    data: JsonData | None = None
    warnings: list[str] = Field(default_factory=list, max_length=100)
    error: JsonError | None = None

    @field_validator("generated_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("generated_at must include a UTC offset")
        return value

    @field_validator("warnings")
    @classmethod
    def bound_warnings(cls, value: list[str]) -> list[str]:
        if any(not warning or len(warning) > 2000 for warning in value):
            raise ValueError("warnings must contain 1 to 2000 characters")
        return value

    def model_post_init(self, __context: object, /) -> None:
        if self.status == "error" and self.error is None:
            raise ValueError("error status requires an error object")
        if self.status != "error" and self.error is not None:
            raise ValueError("only error status may include an error object")
