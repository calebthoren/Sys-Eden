"""Inspection orchestration and narrow generic read interfaces."""

from datetime import UTC, datetime
from typing import Annotated, Literal, Protocol
from uuid import uuid4

from pydantic import BaseModel, Field, JsonValue

from sys_eden.inspection_models import (
    CpuInspection,
    DriversInspection,
    GpuInspection,
    InspectionData,
    MemoryInspection,
    NetworkInspection,
    ProcessesInspection,
    ServicesInspection,
    SoftwareInspection,
    StartupInspection,
    StorageInspection,
    SystemInspection,
)

Identifier = Annotated[str, Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")]
CimClass = Literal[
    "Win32_BaseBoard",
    "Win32_BIOS",
    "Win32_ComputerSystem",
    "Win32_LogicalDisk",
    "Win32_IP4RouteTable",
    "Win32_NetworkAdapter",
    "Win32_NetworkAdapterConfiguration",
    "Win32_OperatingSystem",
    "Win32_PerfFormattedData_PerfOS_Processor",
    "Win32_PhysicalMemory",
    "Win32_PnPSignedDriver",
    "Win32_Process",
    "Win32_PerfFormattedData_PerfProc_Process",
    "Win32_Processor",
    "Win32_Tpm",
    "Win32_VideoController",
    "Win32_Service",
    "Win32_StartupCommand",
    "Win32_PnPEntity",
    "MSFT_Disk",
    "MSFT_PhysicalDisk",
    "MSFT_Volume",
]
CimNamespace = Literal[
    "root/cimv2",
    "root/cimv2/Security/MicrosoftTpm",
    "root/Microsoft/Windows/Storage",
]


class CimQuery(BaseModel):
    # The allowlist excludes providers such as Win32_Product that can trigger repairs.
    class_name: CimClass
    properties: list[Identifier] = Field(min_length=1, max_length=32)
    namespace: CimNamespace = "root/cimv2"
    limit: int = Field(default=100, ge=1, le=1000)


class InspectionError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class CimReader(Protocol):
    async def query(self, request: CimQuery) -> list[dict[str, JsonValue]]: ...


class SoftwareInventoryReader(Protocol):
    async def installed_software(self) -> list[dict[str, JsonValue]]: ...


class InspectionProvider(Protocol):
    async def system(self, *, details: bool) -> SystemInspection: ...

    async def cpu(self, *, details: bool) -> CpuInspection: ...

    async def ram(self, *, details: bool) -> MemoryInspection: ...

    async def gpu(self, *, details: bool) -> GpuInspection: ...

    async def storage(self, *, details: bool) -> StorageInspection: ...

    async def network(self, *, details: bool) -> NetworkInspection: ...

    async def processes(self, *, details: bool) -> ProcessesInspection: ...

    async def services(self, *, details: bool) -> ServicesInspection: ...

    async def startup(self, *, details: bool) -> StartupInspection: ...

    async def drivers(self, *, details: bool) -> DriversInspection: ...

    async def software(self, *, details: bool) -> SoftwareInspection: ...


class InspectionResult(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid4()))
    capability: str
    started_at: datetime
    finished_at: datetime
    success: bool
    data: InspectionData | None = None
    error: str | None = None


async def collect(name: str, provider: InspectionProvider, *, details: bool) -> InspectionResult:
    started = datetime.now(UTC)
    try:
        if name == "system":
            data: InspectionData = await provider.system(details=details)
        elif name == "cpu":
            data = await provider.cpu(details=details)
        elif name == "ram":
            data = await provider.ram(details=details)
        elif name == "gpu":
            data = await provider.gpu(details=details)
        elif name == "storage":
            data = await provider.storage(details=details)
        elif name == "network":
            data = await provider.network(details=details)
        elif name == "processes":
            data = await provider.processes(details=details)
        elif name == "services":
            data = await provider.services(details=details)
        elif name == "startup":
            data = await provider.startup(details=details)
        elif name == "drivers":
            data = await provider.drivers(details=details)
        elif name == "software":
            data = await provider.software(details=details)
        else:
            raise InspectionError("CapabilityUnavailable")
    except InspectionError as error:
        return InspectionResult(
            capability=name,
            started_at=started,
            finished_at=datetime.now(UTC),
            success=False,
            error=error.code,
        )
    return InspectionResult(
        capability=name,
        started_at=started,
        finished_at=datetime.now(UTC),
        success=True,
        data=data,
    )
