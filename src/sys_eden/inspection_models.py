"""Typed, platform-neutral inspection results used by the CLI and future Core logic."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class InspectionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Observation(InspectionModel):
    code: str
    message: str
    severity: Literal["information", "warning"] = "information"


class SourceWarning(InspectionModel):
    source: str
    code: str


class SystemDrive(InspectionModel):
    name: str
    filesystem: str | None = None
    total_bytes: int | None = None
    used_bytes: int | None = None
    free_bytes: int | None = None
    free_percent: float | None = None


class SystemIdentity(InspectionModel):
    device_name: str | None = None
    manufacturer: str | None = None
    model: str | None = None


class WindowsConfiguration(InspectionModel):
    edition: str | None = None
    version: str | None = None
    build: str | None = None
    architecture: str | None = None


class SystemState(InspectionModel):
    uptime_seconds: float | None = None
    last_boot_time: datetime | None = None
    cpu_model: str | None = None
    installed_ram_bytes: int | None = None
    primary_gpu: str | None = None
    system_drive: SystemDrive | None = None


class SystemDetails(InspectionModel):
    motherboard_manufacturer: str | None = None
    motherboard_model: str | None = None
    firmware_vendor: str | None = None
    firmware_version: str | None = None
    firmware_release_date: datetime | None = None
    firmware_mode: Literal["UEFI", "legacy"] | None = None
    secure_boot_enabled: bool | None = None
    tpm_present: bool | None = None
    tpm_version: str | None = None
    windows_install_date: datetime | None = None
    windows_product_type: int | None = None
    windows_edition_id: int | None = None
    hypervisor_present: bool | None = None


class SystemInspection(InspectionModel):
    kind: Literal["system"] = "system"
    identity: SystemIdentity
    configuration: WindowsConfiguration
    current_state: SystemState
    health_status: str | None = None
    details: SystemDetails | None = None
    observations: list[Observation] = Field(default_factory=list)
    warnings: list[SourceWarning] = Field(default_factory=list)


class CpuIdentity(InspectionModel):
    model: str | None = None
    manufacturer: str | None = None
    architecture: str | None = None


class CpuConfiguration(InspectionModel):
    physical_cores: int | None = None
    logical_processors: int | None = None
    base_clock_mhz: float | None = None
    max_clock_mhz: float | None = None


class CpuState(InspectionModel):
    total_utilization_percent: float | None = None
    current_clock_mhz: float | None = None


class CpuDetails(InspectionModel):
    socket: str | None = None
    processor_id: str | None = None
    family: int | None = None
    revision: int | None = None
    stepping: str | None = None
    level: int | None = None
    l2_cache_bytes: int | None = None
    l3_cache_bytes: int | None = None
    virtualization_firmware_enabled: bool | None = None
    second_level_address_translation: bool | None = None
    numa_node_count: int | None = None
    socket_count: int | None = None
    device_id: str | None = None
    per_core_utilization_percent: dict[str, float] | None = None
    temperature_celsius: float | None = None


class CpuInspection(InspectionModel):
    kind: Literal["cpu"] = "cpu"
    identity: CpuIdentity
    configuration: CpuConfiguration
    current_state: CpuState
    health_status: str | None = None
    details: CpuDetails | None = None
    observations: list[Observation] = Field(default_factory=list)
    warnings: list[SourceWarning] = Field(default_factory=list)


class MemoryIdentity(InspectionModel):
    total_installed_bytes: int | None = None
    module_count: int | None = None


class MemoryConfiguration(InspectionModel):
    configured_speeds_mhz: list[int] = Field(default_factory=list)
    rated_speeds_mhz: list[int] = Field(default_factory=list)


class MemoryState(InspectionModel):
    used_bytes: int | None = None
    available_bytes: int | None = None
    usage_percent: float | None = None


class MemoryModule(InspectionModel):
    slot: str | None = None
    bank: str | None = None
    capacity_bytes: int | None = None
    manufacturer: str | None = None
    model: str | None = None
    part_number: str | None = None
    rated_speed_mhz: int | None = None
    configured_speed_mhz: int | None = None
    form_factor: str | None = None
    memory_type: str | None = None
    configured_voltage_volts: float | None = None
    serial_number: str | None = None


class MemoryDetails(InspectionModel):
    modules: list[MemoryModule] = Field(default_factory=list)


class MemoryInspection(InspectionModel):
    kind: Literal["ram"] = "ram"
    identity: MemoryIdentity
    configuration: MemoryConfiguration
    current_state: MemoryState
    health_status: str | None = None
    details: MemoryDetails | None = None
    observations: list[Observation] = Field(default_factory=list)
    warnings: list[SourceWarning] = Field(default_factory=list)


class GpuIdentity(InspectionModel):
    name: str | None = None
    vendor: str | None = None
    adapter_type: Literal["hardware", "virtual"] | None = None


class GpuConfiguration(InspectionModel):
    dedicated_vram_bytes: int | None = None
    driver_version: str | None = None
    driver_date: datetime | None = None


class GpuState(InspectionModel):
    utilization_percent: float | None = None
    temperature_celsius: float | None = None
    active_display: bool | None = None
    primary: bool | None = None


class GpuDetails(InspectionModel):
    pnp_device_id: str | None = None
    device_id: str | None = None
    adapter_status: str | None = None
    device_error_code: int | None = None
    driver_provider: str | None = None
    driver_inf: str | None = None
    driver_signed: bool | None = None
    video_processor: str | None = None
    current_clock_mhz: float | None = None
    vram_used_bytes: int | None = None
    power_watts: float | None = None
    display_resolution: str | None = None
    display_refresh_hz: int | None = None


class GpuAdapter(InspectionModel):
    identity: GpuIdentity
    configuration: GpuConfiguration
    current_state: GpuState
    health_status: str | None = None
    details: GpuDetails | None = None


class GpuInspection(InspectionModel):
    kind: Literal["gpu"] = "gpu"
    adapters: list[GpuAdapter] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)
    warnings: list[SourceWarning] = Field(default_factory=list)


class DiskIdentity(InspectionModel):
    number: int | None = None
    model: str | None = None


class DiskConfiguration(InspectionModel):
    media_type: str | None = None
    bus_type: str | None = None
    capacity_bytes: int | None = None


class DiskDetails(InspectionModel):
    serial_number: str | None = None
    firmware_version: str | None = None
    partition_style: str | None = None
    device_id: str | None = None
    trim_enabled: bool | None = None
    temperature_celsius: float | None = None
    read_errors: int | None = None
    write_errors: int | None = None


class PhysicalDisk(InspectionModel):
    identity: DiskIdentity
    configuration: DiskConfiguration
    health_status: str | None = None
    operational_status: list[str] = Field(default_factory=list)
    details: DiskDetails | None = None


class VolumeIdentity(InspectionModel):
    drive_letter: str | None = None
    name: str | None = None


class VolumeConfiguration(InspectionModel):
    filesystem: str | None = None
    total_bytes: int | None = None


class VolumeState(InspectionModel):
    used_bytes: int | None = None
    free_bytes: int | None = None
    free_percent: float | None = None


class VolumeDetails(InspectionModel):
    path: str | None = None
    encryption_status: str | None = None


class StorageVolume(InspectionModel):
    identity: VolumeIdentity
    configuration: VolumeConfiguration
    current_state: VolumeState
    health_status: str | None = None
    operational_status: list[str] = Field(default_factory=list)
    details: VolumeDetails | None = None


class StorageInspection(InspectionModel):
    kind: Literal["storage"] = "storage"
    physical_disks: list[PhysicalDisk] = Field(default_factory=list)
    volumes: list[StorageVolume] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)
    warnings: list[SourceWarning] = Field(default_factory=list)


InspectionData = (
    SystemInspection | CpuInspection | MemoryInspection | GpuInspection | StorageInspection
)
