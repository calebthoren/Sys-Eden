"""Typed, platform-neutral inspection results used by the CLI and future Core logic."""

from datetime import date as Date
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue


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
    firmware_release_date: Date | None = None
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
    driver_date: Date | None = None


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


class NetworkIdentity(InspectionModel):
    name: str | None = None
    description: str | None = None
    classification: Literal["Ethernet", "Wi-Fi", "virtual", "other"] | None = None


class NetworkConfiguration(InspectionModel):
    enabled: bool | None = None


class NetworkState(InspectionModel):
    connected: bool | None = None
    link_speed_bps: int | None = None
    ipv4_addresses: list[str] = Field(default_factory=list)
    ipv6_addresses: list[str] = Field(default_factory=list)
    default_gateways: list[str] = Field(default_factory=list)
    dns_servers: list[str] = Field(default_factory=list)
    receive_bytes_per_second: int | None = None
    send_bytes_per_second: int | None = None
    wifi_ssid: str | None = None
    wifi_signal_percent: float | None = None
    wifi_receive_link_speed_bps: int | None = None
    wifi_transmit_link_speed_bps: int | None = None


class NetworkRoute(InspectionModel):
    destination: str | None = None
    mask: str | None = None
    next_hop: str | None = None
    metric: int | None = None


class NetworkDetails(InspectionModel):
    mac_address: str | None = None
    dhcp_enabled: bool | None = None
    dhcp_server: str | None = None
    dhcp_lease_obtained: datetime | None = None
    dhcp_lease_expires: datetime | None = None
    subnets: list[str] = Field(default_factory=list)
    dns_domain: str | None = None
    dns_suffixes: list[str] = Field(default_factory=list)
    mtu_bytes: int | None = None
    driver_provider: str | None = None
    driver_version: str | None = None
    pnp_device_id: str | None = None
    interface_index: int | None = None
    interface_guid: str | None = None
    routes: list[NetworkRoute] = Field(default_factory=list)
    receive_errors: int | None = None
    send_errors: int | None = None
    receive_discards: int | None = None
    send_discards: int | None = None


class NetworkAdapter(InspectionModel):
    identity: NetworkIdentity
    configuration: NetworkConfiguration
    current_state: NetworkState
    health_status: str | None = None
    details: NetworkDetails | None = None


class NetworkInspection(InspectionModel):
    kind: Literal["network"] = "network"
    adapters: list[NetworkAdapter] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)
    warnings: list[SourceWarning] = Field(default_factory=list)


class ProcessIdentity(InspectionModel):
    pid: int
    name: str | None = None


class ProcessConfiguration(InspectionModel):
    executable_name: str | None = None


class ProcessState(InspectionModel):
    cpu_percent: float | None = None
    memory_bytes: int | None = None
    user: str | None = None
    status: str | None = None


class ProcessDetails(InspectionModel):
    executable_path: str | None = None
    command_line: str | None = None
    parent_pid: int | None = None
    start_time: datetime | None = None
    thread_count: int | None = None
    handle_count: int | None = None
    io_read_bytes_per_second: int | None = None
    io_write_bytes_per_second: int | None = None
    architecture: str | None = None
    publisher: str | None = None
    digitally_signed: bool | None = None


class ProcessEntry(InspectionModel):
    identity: ProcessIdentity
    configuration: ProcessConfiguration
    current_state: ProcessState
    health_status: str | None = None
    details: ProcessDetails | None = None


class ProcessesInspection(InspectionModel):
    kind: Literal["processes"] = "processes"
    total_detected: int
    returned_count: int
    processes: list[ProcessEntry] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)
    warnings: list[SourceWarning] = Field(default_factory=list)


class ServiceIdentity(InspectionModel):
    name: str
    display_name: str | None = None


class ServiceConfiguration(InspectionModel):
    startup_type: str | None = None


class ServiceState(InspectionModel):
    state: str | None = None
    started: bool | None = None


class ServiceDetails(InspectionModel):
    binary_path: str | None = None
    service_account: str | None = None
    description: str | None = None
    pid: int | None = None
    dependencies: list[str] = Field(default_factory=list)
    dependent_services: list[str] = Field(default_factory=list)
    delayed_auto_start: bool | None = None
    service_type: str | None = None
    exit_code: int | None = None
    service_specific_exit_code: int | None = None


class ServiceEntry(InspectionModel):
    identity: ServiceIdentity
    configuration: ServiceConfiguration
    current_state: ServiceState
    health_status: str | None = None
    details: ServiceDetails | None = None


class ServicesInspection(InspectionModel):
    kind: Literal["services"] = "services"
    services: list[ServiceEntry] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)
    warnings: list[SourceWarning] = Field(default_factory=list)


class StartupIdentity(InspectionModel):
    name: str | None = None
    application: str | None = None
    publisher: str | None = None


class StartupConfiguration(InspectionModel):
    enabled: bool | None = None
    source_type: str | None = None
    scope: str | None = None


class StartupDetails(InspectionModel):
    command: str | None = None
    source_location: str | None = None
    arguments: str | None = None
    digitally_signed: bool | None = None
    associated_package: str | None = None
    user: str | None = None
    user_sid: str | None = None
    startup_impact: str | None = None


class StartupItem(InspectionModel):
    identity: StartupIdentity
    configuration: StartupConfiguration
    current_state: str | None = None
    health_status: str | None = None
    details: StartupDetails | None = None


class StartupInspection(InspectionModel):
    kind: Literal["startup"] = "startup"
    items: list[StartupItem] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)
    warnings: list[SourceWarning] = Field(default_factory=list)


class DriverIdentity(InspectionModel):
    device_name: str | None = None
    device_class: str | None = None


class DriverConfiguration(InspectionModel):
    provider: str | None = None
    version: str | None = None
    date: Date | None = None
    signed: bool | None = None


class DriverDetails(InspectionModel):
    inf_name: str | None = None
    hardware_ids: list[str] = Field(default_factory=list)
    compatible_ids: list[str] = Field(default_factory=list)
    device_instance_id: str | None = None
    service_name: str | None = None
    driver_files: list[str] = Field(default_factory=list)
    signer: str | None = None
    manufacturer: str | None = None
    problem_code: int | None = None
    location: str | None = None


class DriverEntry(InspectionModel):
    identity: DriverIdentity
    configuration: DriverConfiguration
    current_state: str | None = None
    health_status: str | None = None
    details: DriverDetails | None = None


class DriversInspection(InspectionModel):
    kind: Literal["drivers"] = "drivers"
    drivers: list[DriverEntry] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)
    warnings: list[SourceWarning] = Field(default_factory=list)


class SoftwareIdentity(InspectionModel):
    name: str
    publisher: str | None = None


class SoftwareConfiguration(InspectionModel):
    version: str | None = None
    installation_scope: Literal["user", "machine"] | None = None
    install_date: Date | None = None


class SoftwareDetails(InspectionModel):
    install_location: str | None = None
    registry_source: str | None = None
    uninstall_identifier: str | None = None
    product_identifier: str | None = None
    architecture: Literal["x86", "x64"] | None = None
    install_source: str | None = None
    install_channel: str | None = None


class SoftwareEntry(InspectionModel):
    identity: SoftwareIdentity
    configuration: SoftwareConfiguration
    current_state: str | None = None
    health_status: str | None = None
    details: SoftwareDetails | None = None


class SoftwareInspection(InspectionModel):
    kind: Literal["software"] = "software"
    applications: list[SoftwareEntry] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)
    warnings: list[SourceWarning] = Field(default_factory=list)


class EventDetails(InspectionModel):
    full_message: str | None = None
    record_id: int | None = None
    task: str | None = None
    opcode: str | None = None
    process_id: int | None = None
    thread_id: int | None = None
    activity_id: str | None = None
    event_data: dict[str, JsonValue] = Field(default_factory=dict)


class EventRecord(InspectionModel):
    timestamp: datetime | None = None
    level: str | None = None
    provider: str | None = None
    event_id: int | None = None
    channel: str | None = None
    summary: str | None = None
    details: EventDetails | None = None


class EventsInspection(InspectionModel):
    kind: Literal["events"] = "events"
    filter_description: str
    events: list[EventRecord] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)
    warnings: list[SourceWarning] = Field(default_factory=list)


class CrashDetails(InspectionModel):
    faulting_module_version: str | None = None
    faulting_module_path: str | None = None
    exception_offset: str | None = None
    report_id: str | None = None
    bucket_id: str | None = None
    event_id: int | None = None
    record_id: int | None = None
    application_version: str | None = None
    event_data: dict[str, JsonValue] = Field(default_factory=dict)


class CrashRecord(InspectionModel):
    timestamp: datetime | None = None
    affected_application: str | None = None
    crash_type: str | None = None
    faulting_module: str | None = None
    exception_code: str | None = None
    recurrence_count: int = 1
    details: CrashDetails | None = None


class CrashesInspection(InspectionModel):
    kind: Literal["crashes"] = "crashes"
    crashes: list[CrashRecord] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)
    warnings: list[SourceWarning] = Field(default_factory=list)


class BootEvidence(InspectionModel):
    timestamp: datetime | None = None
    event_id: int | None = None
    channel: str | None = None
    record_id: int | None = None
    summary: str | None = None


class BootInspection(InspectionModel):
    kind: Literal["boot"] = "boot"
    recent_boot_times: list[datetime] = Field(default_factory=list)
    current_uptime_seconds: float | None = None
    previous_shutdown: Literal["normal", "unexpected"] | None = None
    latest_boot_duration_ms: int | None = None
    startup_warnings: list[EventRecord] = Field(default_factory=list)
    evidence: list[BootEvidence] | None = None
    observations: list[Observation] = Field(default_factory=list)
    warnings: list[SourceWarning] = Field(default_factory=list)


InspectionData = (
    SystemInspection
    | CpuInspection
    | MemoryInspection
    | GpuInspection
    | StorageInspection
    | NetworkInspection
    | ProcessesInspection
    | ServicesInspection
    | StartupInspection
    | DriversInspection
    | SoftwareInspection
    | EventsInspection
    | CrashesInspection
    | BootInspection
)
