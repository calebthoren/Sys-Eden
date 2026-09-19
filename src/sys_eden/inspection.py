"""Structured, local-only inspection boundaries and initial collectors."""

from datetime import UTC, datetime
from typing import Annotated, Literal, Protocol
from uuid import uuid4

from pydantic import BaseModel, Field, JsonValue

Identifier = Annotated[str, Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")]


class CimQuery(BaseModel):
    # Expand after reviewing provider behavior; Win32_Product can trigger repairs.
    class_name: Literal["Win32_OperatingSystem", "Win32_Processor", "Win32_PhysicalMemory"]
    properties: list[Identifier] = Field(min_length=1, max_length=32)
    limit: int = Field(default=100, ge=1, le=1000)


class InspectionError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class CimReader(Protocol):
    async def query(self, request: CimQuery) -> list[dict[str, JsonValue]]: ...


class InspectionResult(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid4()))
    capability: str
    started_at: datetime
    finished_at: datetime
    success: bool
    data: list[dict[str, JsonValue]] = Field(default_factory=list)
    error: str | None = None


QUERIES = {
    "os": CimQuery(
        class_name="Win32_OperatingSystem",
        properties=["Caption", "Version", "BuildNumber", "LastBootUpTime", "LocalDateTime"],
    ),
    "cpu": CimQuery(
        class_name="Win32_Processor",
        properties=["Name", "NumberOfCores", "NumberOfLogicalProcessors", "MaxClockSpeed"],
    ),
    "ram": CimQuery(
        class_name="Win32_PhysicalMemory",
        properties=["Capacity", "Speed", "ConfiguredClockSpeed"],
    ),
}


async def collect(name: str, reader: CimReader) -> InspectionResult:
    query = QUERIES[name]
    started = datetime.now(UTC)
    try:
        data = await reader.query(query)
    except InspectionError as error:
        return InspectionResult(
            capability=name, started_at=started, finished_at=datetime.now(UTC),
            success=False, error=error.code,
        )
    return InspectionResult(
        capability=name, started_at=started, finished_at=datetime.now(UTC),
        success=True, data=data,
    )
