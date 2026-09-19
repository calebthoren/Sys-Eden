"""Curated Windows collectors built on the allowlisted generic CIM reader."""

import re
from datetime import UTC, date, datetime
from ipaddress import ip_address
from typing import Literal

from pydantic import JsonValue

from sys_eden.inspection import (
    CimQuery,
    CimReader,
    EventLogReader,
    EventProviderName,
    EventQuery,
    InspectionError,
    SoftwareInventoryReader,
)
from sys_eden.inspection_models import (
    BootEvidence,
    BootInspection,
    CpuConfiguration,
    CpuDetails,
    CpuIdentity,
    CpuInspection,
    CpuState,
    CrashDetails,
    CrashesInspection,
    CrashRecord,
    DiskConfiguration,
    DiskDetails,
    DiskIdentity,
    DriverConfiguration,
    DriverDetails,
    DriverEntry,
    DriverIdentity,
    DriversInspection,
    EventDetails,
    EventRecord,
    EventsInspection,
    GpuAdapter,
    GpuConfiguration,
    GpuDetails,
    GpuIdentity,
    GpuInspection,
    GpuState,
    MemoryConfiguration,
    MemoryDetails,
    MemoryIdentity,
    MemoryInspection,
    MemoryModule,
    MemoryState,
    NetworkAdapter,
    NetworkConfiguration,
    NetworkDetails,
    NetworkIdentity,
    NetworkInspection,
    NetworkRoute,
    NetworkState,
    Observation,
    PhysicalDisk,
    ProcessConfiguration,
    ProcessDetails,
    ProcessEntry,
    ProcessesInspection,
    ProcessIdentity,
    ProcessState,
    ServiceConfiguration,
    ServiceDetails,
    ServiceEntry,
    ServiceIdentity,
    ServicesInspection,
    ServiceState,
    SoftwareConfiguration,
    SoftwareDetails,
    SoftwareEntry,
    SoftwareIdentity,
    SoftwareInspection,
    SourceWarning,
    StartupConfiguration,
    StartupDetails,
    StartupIdentity,
    StartupInspection,
    StartupItem,
    StorageInspection,
    StorageVolume,
    SystemDetails,
    SystemDrive,
    SystemIdentity,
    SystemInspection,
    SystemState,
    VolumeConfiguration,
    VolumeDetails,
    VolumeIdentity,
    VolumeState,
    WindowsConfiguration,
)

_POWERSHELL_DATE = re.compile(r"^/Date\((?P<milliseconds>-?\d+)(?:[+-]\d+)?\)/$")
_CPU_ARCHITECTURES = {0: "x86", 5: "ARM", 6: "Itanium", 9: "x64", 12: "ARM64"}
_MEMORY_FORM_FACTORS = {
    0: "Unknown",
    8: "DIMM",
    12: "SODIMM",
    13: "SRIMM",
    15: "FB-DIMM",
}
_SMBIOS_MEMORY_TYPES = {
    0: "Unknown",
    20: "DDR",
    21: "DDR2",
    24: "DDR3",
    26: "DDR4",
    27: "LPDDR",
    28: "LPDDR2",
    29: "LPDDR3",
    30: "LPDDR4",
    34: "DDR5",
    35: "LPDDR5",
}
_MEDIA_TYPES = {0: "Unspecified", 3: "HDD", 4: "SSD", 5: "Storage-class memory"}
_BUS_TYPES = {
    0: "Unknown",
    1: "SCSI",
    2: "ATAPI",
    3: "ATA",
    4: "IEEE 1394",
    6: "Fibre Channel",
    7: "USB",
    8: "RAID",
    9: "iSCSI",
    10: "SAS",
    11: "SATA",
    12: "SD",
    13: "MMC",
    14: "Virtual",
    15: "File-backed virtual",
    16: "Storage Spaces",
    17: "NVMe",
    18: "Storage-class memory",
    19: "UFS",
}
_HEALTH_STATUSES = {0: "Healthy", 1: "Warning", 2: "Unhealthy", 5: "Unknown"}
_OPERATIONAL_STATUSES = {
    0: "Unknown",
    1: "Other",
    2: "OK",
    3: "Degraded",
    4: "Stressed",
    5: "Predictive failure",
    6: "Error",
    7: "Non-recoverable error",
    8: "Starting",
    9: "Stopping",
    10: "Stopped",
    11: "In service",
    12: "No contact",
    13: "Lost communication",
    14: "Aborted",
    15: "Dormant",
    16: "Supporting entity in error",
    17: "Completed",
    18: "Power mode",
    19: "Relocating",
}
_PARTITION_STYLES = {0: "RAW", 1: "MBR", 2: "GPT"}
_EVENT_LEVELS = {1: "Critical", 2: "Error", 3: "Warning", 4: "Information", 5: "Verbose"}
_WER_CRASH_MARKERS = (
    "appcrash",
    "apphang",
    "bex",
    "bluescreen",
    "clr20",
    "crash",
    "hang",
    "livekernel",
    "radar",
    "stoppedworking",
)
_CRASH_METADATA_FIELDS = (
    "EventName",
    "HashedBucket",
    "Bucket",
    "BucketType",
    "ReportStatus",
    "Response",
    "PackageFullName",
    "PackageRelativeAppId",
    "HangType",
    "ProcessId",
    "FaultingProcessId",
    "ExeFileName",
    "AppPath",
    "IntegratorReportId",
)


def _clean(value: JsonValue | None) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _integer(value: JsonValue | None) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _number(value: JsonValue | None) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _boolean(value: JsonValue | None) -> bool | None:
    if isinstance(value, bool):
        return value
    if value in (0, "0", "False", "false"):
        return False
    if value in (1, "1", "True", "true"):
        return True
    return None


def _datetime(value: JsonValue | None) -> datetime | None:
    text = _clean(value)
    if text is None:
        return None
    match = _POWERSHELL_DATE.match(text)
    if match:
        milliseconds = int(match.group("milliseconds"))
        return datetime.fromtimestamp(milliseconds / 1000, UTC)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _first(rows: list[dict[str, JsonValue]]) -> dict[str, JsonValue]:
    return rows[0] if rows else {}


def _unique_integers(rows: list[dict[str, JsonValue]], field: str) -> list[int]:
    values = {_integer(row.get(field)) for row in rows}
    return sorted(value for value in values if value is not None and value > 0)


class WindowsInspectionProvider:
    """Translate Windows-specific data into stable domain models."""

    def __init__(
        self,
        reader: CimReader,
        software_reader: SoftwareInventoryReader | None = None,
        event_reader: EventLogReader | None = None,
    ):
        self._reader = reader
        self._software_reader = software_reader
        self._event_reader = event_reader

    async def _query(
        self,
        class_name: str,
        properties: list[str],
        warnings: list[SourceWarning],
        *,
        namespace: str = "root/cimv2",
        limit: int = 100,
    ) -> tuple[list[dict[str, JsonValue]], bool]:
        try:
            query = CimQuery.model_validate(
                {
                    "class_name": class_name,
                    "properties": properties,
                    "namespace": namespace,
                    "limit": limit,
                }
            )
            return await self._reader.query(query), True
        except InspectionError as error:
            warnings.append(SourceWarning(source=class_name, code=error.code))
            return [], False

    async def system(self, *, details: bool) -> SystemInspection:
        warnings: list[SourceWarning] = []
        computers, computer_ok = await self._query(
            "Win32_ComputerSystem",
            ["Name", "Manufacturer", "Model", "TotalPhysicalMemory", "HypervisorPresent"],
            warnings,
            limit=1,
        )
        operating_systems, os_ok = await self._query(
            "Win32_OperatingSystem",
            [
                "Caption",
                "Version",
                "BuildNumber",
                "OSArchitecture",
                "LastBootUpTime",
                "SystemDrive",
                "Status",
                "InstallDate",
                "OperatingSystemSKU",
                "ProductType",
            ],
            warnings,
            limit=1,
        )
        processors, _ = await self._query("Win32_Processor", ["Name"], warnings)
        memory_modules, _ = await self._query(
            "Win32_PhysicalMemory", ["Capacity"], warnings
        )
        graphics, _ = await self._query(
            "Win32_VideoController",
            ["Name", "CurrentHorizontalResolution", "CurrentVerticalResolution"],
            warnings,
        )
        volumes, _ = await self._query(
            "Win32_LogicalDisk",
            ["DeviceID", "FileSystem", "Size", "FreeSpace", "DriveType"],
            warnings,
        )
        if not computer_ok and not os_ok:
            raise InspectionError("InspectionUnavailable")

        computer = _first(computers)
        operating_system = _first(operating_systems)
        boot_time = _datetime(operating_system.get("LastBootUpTime"))
        uptime = None
        if boot_time is not None:
            uptime = max(0.0, (datetime.now(UTC) - boot_time).total_seconds())
        active_graphics = [
            row
            for row in graphics
            if _integer(row.get("CurrentHorizontalResolution"))
            and _integer(row.get("CurrentVerticalResolution"))
        ]
        primary_gpu = None
        observations: list[Observation] = []
        if len(active_graphics) == 1:
            primary_gpu = _clean(active_graphics[0].get("Name"))
        elif len(graphics) == 1:
            primary_gpu = _clean(graphics[0].get("Name"))
        elif graphics:
            observations.append(
                Observation(
                    code="primary_gpu_undetermined",
                    message="Multiple GPUs were found, but Windows did not identify one primary GPU.",
                )
            )

        system_drive_name = _clean(operating_system.get("SystemDrive"))
        drive_row = next(
            (row for row in volumes if _clean(row.get("DeviceID")) == system_drive_name),
            None,
        )
        drive = self._system_drive(drive_row) if drive_row is not None else None
        system_details = await self._system_details(
            details, computer, operating_system, warnings
        )
        return SystemInspection(
            identity=SystemIdentity(
                device_name=_clean(computer.get("Name")),
                manufacturer=_clean(computer.get("Manufacturer")),
                model=_clean(computer.get("Model")),
            ),
            configuration=WindowsConfiguration(
                edition=_clean(operating_system.get("Caption")),
                version=_clean(operating_system.get("Version")),
                build=_clean(operating_system.get("BuildNumber")),
                architecture=_clean(operating_system.get("OSArchitecture")),
            ),
            current_state=SystemState(
                uptime_seconds=uptime,
                last_boot_time=boot_time,
                cpu_model=self._joined_values(processors, "Name"),
                installed_ram_bytes=(
                    sum(_integer(row.get("Capacity")) or 0 for row in memory_modules)
                    or _integer(computer.get("TotalPhysicalMemory"))
                ),
                primary_gpu=primary_gpu,
                system_drive=drive,
            ),
            health_status=_clean(operating_system.get("Status")),
            details=system_details,
            observations=observations,
            warnings=warnings,
        )

    async def _system_details(
        self,
        requested: bool,
        computer: dict[str, JsonValue],
        operating_system: dict[str, JsonValue],
        warnings: list[SourceWarning],
    ) -> SystemDetails | None:
        if not requested:
            return None
        boards, _ = await self._query(
            "Win32_BaseBoard", ["Manufacturer", "Product"], warnings, limit=1
        )
        bios_rows, _ = await self._query(
            "Win32_BIOS", ["Manufacturer", "SMBIOSBIOSVersion", "ReleaseDate"], warnings, limit=1
        )
        tpm_rows, tpm_ok = await self._query(
            "Win32_Tpm",
            ["SpecVersion"],
            warnings,
            namespace="root/cimv2/Security/MicrosoftTpm",
            limit=1,
        )
        board = _first(boards)
        bios = _first(bios_rows)
        tpm = _first(tpm_rows)
        return SystemDetails(
            motherboard_manufacturer=_clean(board.get("Manufacturer")),
            motherboard_model=_clean(board.get("Product")),
            firmware_vendor=_clean(bios.get("Manufacturer")),
            firmware_version=_clean(bios.get("SMBIOSBIOSVersion")),
            firmware_release_date=self._calendar_date(bios.get("ReleaseDate")),
            tpm_present=bool(tpm_rows) if tpm_ok else None,
            tpm_version=_clean(tpm.get("SpecVersion")),
            windows_install_date=_datetime(operating_system.get("InstallDate")),
            windows_product_type=_integer(operating_system.get("ProductType")),
            windows_edition_id=_integer(operating_system.get("OperatingSystemSKU")),
            hypervisor_present=_boolean(computer.get("HypervisorPresent")),
        )

    @staticmethod
    def _system_drive(row: dict[str, JsonValue]) -> SystemDrive:
        total = _integer(row.get("Size"))
        free = _integer(row.get("FreeSpace"))
        used = total - free if total is not None and free is not None else None
        free_percent = free / total * 100 if total and free is not None else None
        return SystemDrive(
            name=_clean(row.get("DeviceID")) or "unavailable",
            filesystem=_clean(row.get("FileSystem")),
            total_bytes=total,
            used_bytes=used,
            free_bytes=free,
            free_percent=free_percent,
        )

    async def cpu(self, *, details: bool) -> CpuInspection:
        warnings: list[SourceWarning] = []
        properties = [
            "Name",
            "Manufacturer",
            "NumberOfCores",
            "NumberOfLogicalProcessors",
            "Architecture",
            "LoadPercentage",
            "MaxClockSpeed",
            "CurrentClockSpeed",
            "Status",
        ]
        if details:
            properties += [
                "SocketDesignation",
                "ProcessorId",
                "Family",
                "Revision",
                "Stepping",
                "Level",
                "L2CacheSize",
                "L3CacheSize",
                "VirtualizationFirmwareEnabled",
                "SecondLevelAddressTranslationExtensions",
                "DeviceID",
            ]
        processors, ok = await self._query("Win32_Processor", properties, warnings)
        if not ok or not processors:
            raise InspectionError("InspectionUnavailable")
        total_cores = sum(_integer(row.get("NumberOfCores")) or 0 for row in processors)
        total_threads = sum(
            _integer(row.get("NumberOfLogicalProcessors")) or 0 for row in processors
        )
        loads = [
            value
            for row in processors
            if (value := _number(row.get("LoadPercentage"))) is not None
        ]
        clocks = [
            value
            for row in processors
            if (value := _number(row.get("CurrentClockSpeed"))) is not None
        ]
        maximum_clocks = [
            value
            for row in processors
            if (value := _number(row.get("MaxClockSpeed"))) is not None
        ]
        first = processors[0]
        cpu_details = await self._cpu_details(details, processors, first, warnings)
        architecture_code = _integer(first.get("Architecture"))
        return CpuInspection(
            identity=CpuIdentity(
                model=self._joined_values(processors, "Name"),
                manufacturer=self._joined_values(processors, "Manufacturer"),
                architecture=(
                    _CPU_ARCHITECTURES.get(architecture_code)
                    if architecture_code is not None
                    else None
                ),
            ),
            configuration=CpuConfiguration(
                physical_cores=total_cores or None,
                logical_processors=total_threads or None,
                # Win32_Processor does not expose a reliable base clock separately.
                base_clock_mhz=None,
                max_clock_mhz=max(maximum_clocks) if maximum_clocks else None,
            ),
            current_state=CpuState(
                total_utilization_percent=sum(loads) / len(loads) if loads else None,
                current_clock_mhz=sum(clocks) / len(clocks) if clocks else None,
            ),
            health_status=self._joined_values(processors, "Status"),
            details=cpu_details,
            warnings=warnings,
        )

    async def _cpu_details(
        self,
        requested: bool,
        processors: list[dict[str, JsonValue]],
        first: dict[str, JsonValue],
        warnings: list[SourceWarning],
    ) -> CpuDetails | None:
        if not requested:
            return None
        counters, _ = await self._query(
            "Win32_PerfFormattedData_PerfOS_Processor",
            ["Name", "PercentProcessorTime"],
            warnings,
        )
        per_core = {
            name: value
            for row in counters
            if (name := _clean(row.get("Name"))) is not None and name != "_Total"
            if (value := _number(row.get("PercentProcessorTime"))) is not None
        }
        return CpuDetails(
            socket=_clean(first.get("SocketDesignation")),
            processor_id=_clean(first.get("ProcessorId")),
            family=_integer(first.get("Family")),
            revision=_integer(first.get("Revision")),
            stepping=_clean(first.get("Stepping")),
            level=_integer(first.get("Level")),
            l2_cache_bytes=self._kilobytes(first.get("L2CacheSize")),
            l3_cache_bytes=self._kilobytes(first.get("L3CacheSize")),
            virtualization_firmware_enabled=_boolean(
                first.get("VirtualizationFirmwareEnabled")
            ),
            second_level_address_translation=_boolean(
                first.get("SecondLevelAddressTranslationExtensions")
            ),
            socket_count=len(processors),
            device_id=_clean(first.get("DeviceID")),
            per_core_utilization_percent=per_core or None,
            # Standard Windows CIM does not reliably expose CPU package temperature.
            temperature_celsius=None,
        )

    async def ram(self, *, details: bool) -> MemoryInspection:
        warnings: list[SourceWarning] = []
        module_properties = [
            "Capacity",
            "Speed",
            "ConfiguredClockSpeed",
            "Manufacturer",
            "PartNumber",
            "SMBIOSMemoryType",
            "Status",
        ]
        if details:
            module_properties += [
                "Model",
                "DeviceLocator",
                "BankLabel",
                "FormFactor",
                "ConfiguredVoltage",
                "SerialNumber",
            ]
        modules, modules_ok = await self._query(
            "Win32_PhysicalMemory", module_properties, warnings
        )
        operating_systems, os_ok = await self._query(
            "Win32_OperatingSystem",
            ["TotalVisibleMemorySize", "FreePhysicalMemory"],
            warnings,
            limit=1,
        )
        computers, computer_ok = await self._query(
            "Win32_ComputerSystem", ["TotalPhysicalMemory"], warnings, limit=1
        )
        if not modules_ok and not os_ok and not computer_ok:
            raise InspectionError("InspectionUnavailable")
        operating_system = _first(operating_systems)
        computer = _first(computers)
        total_visible = self._kilobytes(operating_system.get("TotalVisibleMemorySize"))
        available = self._kilobytes(operating_system.get("FreePhysicalMemory"))
        used = (
            total_visible - available
            if total_visible is not None and available is not None
            else None
        )
        usage = used / total_visible * 100 if total_visible and used is not None else None
        installed = sum(_integer(row.get("Capacity")) or 0 for row in modules) or None
        if installed is None:
            installed = _integer(computer.get("TotalPhysicalMemory"))
        observations = self._memory_observations(modules)
        return MemoryInspection(
            identity=MemoryIdentity(
                total_installed_bytes=installed,
                module_count=len(modules) if modules_ok else None,
            ),
            configuration=MemoryConfiguration(
                configured_speeds_mhz=_unique_integers(modules, "ConfiguredClockSpeed"),
                rated_speeds_mhz=_unique_integers(modules, "Speed"),
            ),
            current_state=MemoryState(
                used_bytes=used,
                available_bytes=available,
                usage_percent=usage,
            ),
            health_status=self._joined_values(modules, "Status"),
            details=(
                MemoryDetails(modules=[self._memory_module(row) for row in modules])
                if details
                else None
            ),
            observations=observations,
            warnings=warnings,
        )

    async def gpu(self, *, details: bool) -> GpuInspection:
        warnings: list[SourceWarning] = []
        properties = [
            "Name",
            "AdapterCompatibility",
            "DriverVersion",
            "DriverDate",
            "CurrentHorizontalResolution",
            "CurrentVerticalResolution",
            "Status",
            "ConfigManagerErrorCode",
            "PNPDeviceID",
            "DeviceID",
        ]
        if details:
            properties += ["VideoProcessor", "CurrentRefreshRate"]
        graphics, ok = await self._query("Win32_VideoController", properties, warnings)
        if not ok:
            raise InspectionError("InspectionUnavailable")
        drivers: list[dict[str, JsonValue]] = []
        if details:
            drivers, _ = await self._query(
                "Win32_PnPSignedDriver",
                [
                    "DeviceID",
                    "DriverProviderName",
                    "DriverVersion",
                    "DriverDate",
                    "InfName",
                    "IsSigned",
                ],
                warnings,
                limit=1000,
            )
        active_rows = [row for row in graphics if self._gpu_active(row)]
        unique_primary = active_rows[0] if len(active_rows) == 1 else None
        if len(graphics) == 1:
            unique_primary = graphics[0]
        observations: list[Observation] = []
        if len(graphics) > 1 and unique_primary is None:
            observations.append(
                Observation(
                    code="primary_gpu_undetermined",
                    message=(
                        "Multiple GPUs were found, but Windows did not identify one primary GPU."
                    ),
                )
            )
        adapters = [
            self._gpu_adapter(row, drivers, details, row is unique_primary)
            for row in graphics
        ]
        return GpuInspection(
            adapters=adapters,
            observations=observations,
            warnings=warnings,
        )

    def _gpu_adapter(
        self,
        row: dict[str, JsonValue],
        drivers: list[dict[str, JsonValue]],
        details: bool,
        primary: bool,
    ) -> GpuAdapter:
        pnp_id = _clean(row.get("PNPDeviceID"))
        driver = next(
            (
                item
                for item in drivers
                if (_clean(item.get("DeviceID")) or "").casefold()
                == (pnp_id or "").casefold()
            ),
            {},
        )
        width = _integer(row.get("CurrentHorizontalResolution"))
        height = _integer(row.get("CurrentVerticalResolution"))
        resolution = f"{width}x{height}" if width and height else None
        active = self._gpu_active(row)
        return GpuAdapter(
            identity=GpuIdentity(
                name=_clean(row.get("Name")),
                vendor=_clean(row.get("AdapterCompatibility")),
                adapter_type=(
                    "virtual"
                    if (pnp_id or "").upper().startswith(("ROOT\\", "SWD\\"))
                    else "hardware"
                    if pnp_id
                    else None
                ),
            ),
            configuration=GpuConfiguration(
                # AdapterRAM is a 32-bit WMI field and is unreliable for modern GPUs.
                dedicated_vram_bytes=None,
                driver_version=_clean(row.get("DriverVersion")),
                driver_date=self._calendar_date(row.get("DriverDate")),
            ),
            current_state=GpuState(
                # Standard CIM does not reliably map utilization/temperature per adapter.
                utilization_percent=None,
                temperature_celsius=None,
                active_display=active,
                primary=primary if primary else (False if active is False else None),
            ),
            health_status=_clean(row.get("Status")),
            details=(
                GpuDetails(
                    pnp_device_id=pnp_id,
                    device_id=_clean(row.get("DeviceID")),
                    adapter_status=_clean(row.get("Status")),
                    device_error_code=_integer(row.get("ConfigManagerErrorCode")),
                    driver_provider=_clean(driver.get("DriverProviderName")),
                    driver_inf=_clean(driver.get("InfName")),
                    driver_signed=_boolean(driver.get("IsSigned")),
                    video_processor=_clean(row.get("VideoProcessor")),
                    display_resolution=resolution,
                    display_refresh_hz=_integer(row.get("CurrentRefreshRate")),
                )
                if details
                else None
            ),
        )

    async def storage(self, *, details: bool) -> StorageInspection:
        warnings: list[SourceWarning] = []
        namespace = "root/Microsoft/Windows/Storage"
        physical_rows, physical_ok = await self._query(
            "MSFT_PhysicalDisk",
            [
                "DeviceId",
                "FriendlyName",
                "MediaType",
                "BusType",
                "Size",
                "HealthStatus",
                "OperationalStatus",
                "SerialNumber",
                "FirmwareVersion",
            ],
            warnings,
            namespace=namespace,
        )
        volume_rows, volume_ok = await self._query(
            "MSFT_Volume",
            [
                "DriveLetter",
                "FileSystemLabel",
                "FileSystem",
                "Size",
                "SizeRemaining",
                "HealthStatus",
                "OperationalStatus",
                "Path",
            ],
            warnings,
            namespace=namespace,
        )
        if not physical_ok and not volume_ok:
            raise InspectionError("InspectionUnavailable")
        disk_rows: list[dict[str, JsonValue]] = []
        if details:
            disk_rows, _ = await self._query(
                "MSFT_Disk",
                ["Number", "FriendlyName", "PartitionStyle", "UniqueId", "SerialNumber"],
                warnings,
                namespace=namespace,
            )
        physical_disks = [
            self._physical_disk(row, disk_rows, details) for row in physical_rows
        ]
        volumes = [self._storage_volume(row, details) for row in volume_rows]
        observations = self._storage_observations(physical_disks, volumes)
        return StorageInspection(
            physical_disks=physical_disks,
            volumes=volumes,
            observations=observations,
            warnings=warnings,
        )

    async def network(self, *, details: bool) -> NetworkInspection:
        warnings: list[SourceWarning] = []
        adapter_properties = [
            "Index",
            "NetConnectionID",
            "Name",
            "Description",
            "NetEnabled",
            "NetConnectionStatus",
            "Speed",
            "AdapterTypeID",
            "PhysicalAdapter",
            "Status",
        ]
        if details:
            adapter_properties += ["InterfaceIndex", "GUID", "MACAddress", "PNPDeviceID"]
        adapter_rows, adapters_ok = await self._query(
            "Win32_NetworkAdapter",
            adapter_properties,
            warnings,
            limit=1000,
        )
        config_properties = [
            "Index",
            "IPEnabled",
            "IPAddress",
            "DefaultIPGateway",
            "DNSServerSearchOrder",
        ]
        if details:
            config_properties += [
                "DHCPEnabled",
                "DHCPServer",
                "DHCPLeaseObtained",
                "DHCPLeaseExpires",
                "IPSubnet",
                "DNSDomain",
                "DNSDomainSuffixSearchOrder",
                "MTU",
            ]
        config_rows, configs_ok = await self._query(
            "Win32_NetworkAdapterConfiguration",
            config_properties,
            warnings,
            limit=1000,
        )
        if not adapters_ok and not configs_ok:
            raise InspectionError("InspectionUnavailable")
        configs = {_integer(row.get("Index")): row for row in config_rows}
        relevant = [
            row
            for row in adapter_rows
            if _clean(row.get("NetConnectionID"))
            or _boolean(configs.get(_integer(row.get("Index")), {}).get("IPEnabled"))
        ]
        drivers: list[dict[str, JsonValue]] = []
        routes: list[dict[str, JsonValue]] = []
        if details:
            drivers, _ = await self._query(
                "Win32_PnPSignedDriver",
                ["DeviceID", "DriverProviderName", "DriverVersion"],
                warnings,
                limit=1000,
            )
            routes, _ = await self._query(
                "Win32_IP4RouteTable",
                ["InterfaceIndex", "Destination", "Mask", "NextHop", "Metric1"],
                warnings,
                limit=1000,
            )
        adapters = [
            self._network_adapter(
                row,
                configs.get(_integer(row.get("Index")), {}),
                drivers,
                routes,
                details,
            )
            for row in relevant
        ]
        return NetworkInspection(adapters=adapters, warnings=warnings)

    async def processes(self, *, details: bool) -> ProcessesInspection:
        warnings: list[SourceWarning] = []
        process_properties = ["ProcessId", "Name", "ExecutionState"]
        if details:
            process_properties += [
                "ExecutablePath",
                "CommandLine",
                "ParentProcessId",
                "CreationDate",
                "ThreadCount",
                "HandleCount",
            ]
        process_rows, process_ok = await self._query(
            "Win32_Process", process_properties, warnings, limit=1000
        )
        performance_rows, performance_ok = await self._query(
            "Win32_PerfFormattedData_PerfProc_Process",
            [
                "IDProcess",
                "Name",
                "PercentProcessorTime",
                "WorkingSetPrivate",
                "IOReadBytesPerSec",
                "IOWriteBytesPerSec",
                "ThreadCount",
                "HandleCount",
            ],
            warnings,
            limit=1000,
        )
        if not process_ok and not performance_ok:
            raise InspectionError("InspectionUnavailable")
        computers, _ = await self._query(
            "Win32_ComputerSystem", ["NumberOfLogicalProcessors"], warnings, limit=1
        )
        logical_processors = _integer(_first(computers).get("NumberOfLogicalProcessors")) or 1
        performance = {
            pid: row
            for row in performance_rows
            if (pid := _integer(row.get("IDProcess"))) is not None
            and _clean(row.get("Name")) != "_Total"
        }
        entries: list[ProcessEntry] = []
        for row in process_rows:
            pid = _integer(row.get("ProcessId"))
            if pid is not None and pid != 0:
                entries.append(
                    self._process_entry(
                        row,
                        performance.get(pid, {}),
                        details,
                        logical_processors,
                    )
                )
        entries.sort(
            key=lambda item: (
                item.current_state.cpu_percent or 0,
                item.current_state.memory_bytes or 0,
            ),
            reverse=True,
        )
        limit = 100 if details else 20
        selected = entries[:limit]
        observations: list[Observation] = []
        if len(entries) > len(selected):
            observations.append(
                Observation(
                    code="process_list_truncated",
                    message=(
                        f"Showing {len(selected)} of {len(entries)} processes, ranked by CPU "
                        "and private memory usage."
                    ),
                )
            )
        return ProcessesInspection(
            total_detected=len(entries),
            returned_count=len(selected),
            processes=selected,
            observations=observations,
            warnings=warnings,
        )

    def _process_entry(
        self,
        row: dict[str, JsonValue],
        performance: dict[str, JsonValue],
        details: bool,
        logical_processors: int,
    ) -> ProcessEntry:
        pid = _integer(row.get("ProcessId"))
        if pid is None:
            raise InspectionError("InvalidToolOutput")
        raw_cpu = _number(performance.get("PercentProcessorTime"))
        normalized_cpu = (
            min(100.0, raw_cpu / logical_processors) if raw_cpu is not None else None
        )
        name = _clean(row.get("Name"))
        return ProcessEntry(
            identity=ProcessIdentity(pid=pid, name=name),
            configuration=ProcessConfiguration(executable_name=name),
            current_state=ProcessState(
                cpu_percent=normalized_cpu,
                memory_bytes=_integer(performance.get("WorkingSetPrivate")),
                # Win32_Process owner requires a separate method call and may be protected.
                user=None,
                status="running",
            ),
            details=(
                ProcessDetails(
                    executable_path=_clean(row.get("ExecutablePath")),
                    command_line=_clean(row.get("CommandLine")),
                    parent_pid=_integer(row.get("ParentProcessId")),
                    start_time=_datetime(row.get("CreationDate")),
                    thread_count=(
                        _integer(row.get("ThreadCount"))
                        or _integer(performance.get("ThreadCount"))
                    ),
                    handle_count=(
                        _integer(row.get("HandleCount"))
                        or _integer(performance.get("HandleCount"))
                    ),
                    io_read_bytes_per_second=_integer(
                        performance.get("IOReadBytesPerSec")
                    ),
                    io_write_bytes_per_second=_integer(
                        performance.get("IOWriteBytesPerSec")
                    ),
                )
                if details
                else None
            ),
        )

    async def services(self, *, details: bool) -> ServicesInspection:
        warnings: list[SourceWarning] = []
        properties = ["Name", "DisplayName", "State", "StartMode", "Status", "Started"]
        if details:
            properties += [
                "PathName",
                "StartName",
                "Description",
                "ProcessId",
                "DelayedAutoStart",
                "ServiceType",
                "ExitCode",
                "ServiceSpecificExitCode",
            ]
        rows, ok = await self._query("Win32_Service", properties, warnings, limit=1000)
        if not ok:
            raise InspectionError("InspectionUnavailable")
        services = [self._service_entry(row, details) for row in rows]
        services.sort(
            key=lambda item: (
                item.current_state.state != "Running",
                (item.identity.display_name or item.identity.name).casefold(),
            )
        )
        return ServicesInspection(services=services, warnings=warnings)

    async def startup(self, *, details: bool) -> StartupInspection:
        warnings: list[SourceWarning] = []
        properties = ["Name", "Caption", "Location", "User"]
        if details:
            properties += ["Command", "Description", "UserSID"]
        rows, ok = await self._query("Win32_StartupCommand", properties, warnings, limit=1000)
        if not ok:
            raise InspectionError("InspectionUnavailable")
        items = [self._startup_item(row, details) for row in rows]
        items.sort(key=lambda item: (item.identity.name or "").casefold())
        return StartupInspection(items=items, warnings=warnings)

    @staticmethod
    def _startup_item(row: dict[str, JsonValue], details: bool) -> StartupItem:
        location = _clean(row.get("Location"))
        user = _clean(row.get("User"))
        user_sid = _clean(row.get("UserSID"))
        source_type = None
        if location:
            lowered = location.casefold()
            if "startup" in lowered:
                source_type = "startup folder"
            elif "registry" in lowered or lowered.startswith(("hk", "machine", "user")):
                source_type = "registry"
        system_sids = ("S-1-5-18", "S-1-5-19", "S-1-5-20")
        scope = (
            "system"
            if (user_sid or "").upper().startswith(system_sids)
            or (user or "").casefold() in {"all users", "public"}
            else "user"
            if user or user_sid
            else None
        )
        name = _clean(row.get("Name"))
        return StartupItem(
            identity=StartupIdentity(
                name=name,
                application=_clean(row.get("Caption")) or name,
            ),
            configuration=StartupConfiguration(
                # This provider enumerates registered entries but not disabled-state stores.
                enabled=None,
                source_type=source_type,
                scope=scope,
            ),
            current_state="registered",
            details=(
                StartupDetails(
                    command=_clean(row.get("Command")),
                    source_location=location,
                    user=user,
                    user_sid=user_sid,
                )
                if details
                else None
            ),
        )

    async def drivers(self, *, details: bool) -> DriversInspection:
        warnings: list[SourceWarning] = []
        signed_properties = [
            "DeviceID",
            "DeviceName",
            "DeviceClass",
            "DriverProviderName",
            "DriverVersion",
            "DriverDate",
            "IsSigned",
            "Started",
        ]
        if details:
            signed_properties += ["InfName", "Signer", "Manufacturer"]
        signed_rows, signed_ok = await self._query(
            "Win32_PnPSignedDriver", signed_properties, warnings, limit=1000
        )
        entity_properties = ["DeviceID", "Name", "PNPClass", "Status", "ConfigManagerErrorCode"]
        if details:
            entity_properties += [
                "HardwareID",
                "CompatibleID",
                "Service",
                "LocationInformation",
            ]
        entity_rows, entity_ok = await self._query(
            "Win32_PnPEntity", entity_properties, warnings, limit=1000
        )
        if not signed_ok and not entity_ok:
            raise InspectionError("InspectionUnavailable")
        entities = {
            key.casefold(): row
            for row in entity_rows
            if (key := _clean(row.get("DeviceID"))) is not None
        }
        entries = [
            self._driver_entry(
                row,
                entities.get((_clean(row.get("DeviceID")) or "").casefold(), {}),
                details,
            )
            for row in signed_rows
            if _clean(row.get("DeviceName")) or _clean(row.get("DeviceID"))
        ]
        entries = [item for item in entries if item.identity.device_name is not None]
        entries.sort(
            key=lambda item: (
                (item.identity.device_class or "").casefold(),
                (item.identity.device_name or "").casefold(),
            )
        )
        observations = [
            Observation(
                code="device_problem_code",
                message=(
                    f"{item.identity.device_name or 'A device'} reports problem code "
                    f"{item.details.problem_code}."
                ),
                severity="warning",
            )
            for item in entries
            if item.details is not None
            and item.details.problem_code not in (None, 0)
        ]
        return DriversInspection(
            drivers=entries,
            observations=observations,
            warnings=warnings,
        )

    @staticmethod
    def _driver_entry(
        row: dict[str, JsonValue],
        entity: dict[str, JsonValue],
        details: bool,
    ) -> DriverEntry:
        problem_code = _integer(entity.get("ConfigManagerErrorCode"))
        status = _clean(entity.get("Status"))
        if status is None and problem_code == 0:
            status = "OK"
        started = _boolean(row.get("Started"))
        return DriverEntry(
            identity=DriverIdentity(
                device_name=_clean(row.get("DeviceName")) or _clean(entity.get("Name")),
                device_class=_clean(row.get("DeviceClass")) or _clean(entity.get("PNPClass")),
            ),
            configuration=DriverConfiguration(
                provider=_clean(row.get("DriverProviderName")),
                version=_clean(row.get("DriverVersion")),
                date=WindowsInspectionProvider._calendar_date(row.get("DriverDate")),
                signed=_boolean(row.get("IsSigned")),
            ),
            current_state=(
                "started" if started is True else "not started" if started is False else None
            ),
            health_status=status,
            details=(
                DriverDetails(
                    inf_name=_clean(row.get("InfName")),
                    hardware_ids=WindowsInspectionProvider._strings(entity.get("HardwareID")),
                    compatible_ids=WindowsInspectionProvider._strings(
                        entity.get("CompatibleID")
                    ),
                    device_instance_id=_clean(row.get("DeviceID")),
                    service_name=_clean(entity.get("Service")),
                    signer=_clean(row.get("Signer")),
                    manufacturer=_clean(row.get("Manufacturer")),
                    problem_code=problem_code,
                    location=_clean(entity.get("LocationInformation")),
                )
                if details
                else None
            ),
        )

    async def software(self, *, details: bool) -> SoftwareInspection:
        if self._software_reader is None:
            raise InspectionError("CapabilityUnavailable")
        rows = await self._software_reader.installed_software()
        applications = [self._software_entry(row, details) for row in rows]
        applications.sort(key=lambda item: item.identity.name.casefold())
        return SoftwareInspection(applications=applications)

    async def events(self, *, details: bool) -> EventsInspection:
        if self._event_reader is None:
            raise InspectionError("CapabilityUnavailable")
        request = EventQuery(
            log_names=["System", "Application"],
            levels=[1, 2, 3],
            since_hours=24,
            limit=100 if details else 50,
            include_event_data=details,
        )
        rows = await self._event_reader.query_events(request)
        observations = []
        if len(rows) == request.limit:
            observations.append(
                Observation(
                    code="event_query_limit_reached",
                    message=(
                        f"The event query reached its {request.limit}-record limit; "
                        "additional matching events may exist."
                    ),
                    severity="information",
                )
            )
        return EventsInspection(
            filter_description=(
                "Critical, error, and warning events from System and Application "
                "during the last 24 hours"
            ),
            events=[self._event_record(row, details) for row in rows],
            observations=observations,
        )

    async def crashes(self, *, details: bool) -> CrashesInspection:
        if self._event_reader is None:
            raise InspectionError("CapabilityUnavailable")
        rows = await self._event_reader.query_events(
            EventQuery(
                log_names=["Application"],
                event_ids=[1000, 1001, 1002],
                since_hours=24 * 30,
                limit=200,
                include_event_data=True,
            )
        )
        grouped: dict[tuple[str | None, str, str | None, str | None], CrashRecord] = {}
        for row in rows:
            data = self._event_data(row)
            event_id = _integer(row.get("EventId"))
            if not self._is_crash_event(event_id, data):
                continue
            crash_type = self._crash_type(event_id, data)
            application = self._crash_application(event_id, data)
            module = self._crash_module(event_id, data)
            exception_code = self._crash_exception_code(event_id, data)
            key = (application, crash_type, module, exception_code)
            existing = grouped.get(key)
            if existing is not None:
                existing.recurrence_count += 1
                continue
            grouped[key] = CrashRecord(
                timestamp=_datetime(row.get("Timestamp")),
                affected_application=application,
                crash_type=crash_type,
                faulting_module=module,
                exception_code=exception_code,
                details=(
                    CrashDetails(
                        faulting_module_version=self._crash_module_version(event_id, data),
                        faulting_module_path=self._event_value(
                            data, "ModulePath", "FaultingModulePath"
                        ),
                        exception_offset=self._crash_exception_offset(event_id, data),
                        report_id=self._event_value(data, "ReportId", "ReportIdentifier"),
                        bucket_id=self._event_value(
                            data, "BucketId", "FaultBucket", "HashedBucket", "Bucket"
                        ),
                        event_id=event_id,
                        record_id=_integer(row.get("RecordId")),
                        application_version=self._crash_application_version(event_id, data),
                        event_data=self._crash_metadata(data),
                    )
                    if details
                    else None
                ),
            )
        crashes = list(grouped.values())
        crashes.sort(key=lambda item: item.timestamp or datetime.min.replace(tzinfo=UTC), reverse=True)
        observations = []
        if len(rows) == 200:
            observations.append(
                Observation(
                    code="crash_query_limit_reached",
                    message=(
                        "The crash query reached its 200-record limit; recurrence counts "
                        "may be lower bounds."
                    ),
                    severity="information",
                )
            )
        return CrashesInspection(crashes=crashes, observations=observations)

    async def boot(self, *, details: bool) -> BootInspection:
        if self._event_reader is None:
            raise InspectionError("CapabilityUnavailable")
        warnings: list[SourceWarning] = []
        operating_systems, _ = await self._query(
            "Win32_OperatingSystem", ["LastBootUpTime"], warnings, limit=1
        )
        last_boot = _datetime(_first(operating_systems).get("LastBootUpTime"))
        uptime = (
            max(0.0, (datetime.now(UTC) - last_boot).total_seconds())
            if last_boot is not None
            else None
        )
        system_rows: list[dict[str, JsonValue]] = []
        boot_sources: tuple[tuple[EventProviderName, list[int]], ...] = (
            ("Microsoft-Windows-Kernel-General", [12, 13]),
            ("Microsoft-Windows-Kernel-Power", [41]),
            ("EventLog", [6005, 6006, 6008]),
        )
        for provider_name, event_ids in boot_sources:
            system_rows.extend(
                await self._safe_events(
                    EventQuery(
                        log_names=["System"],
                        provider_names=[provider_name],
                        event_ids=event_ids,
                        since_hours=24 * 30,
                        limit=100,
                        include_event_data=details,
                    ),
                    warnings,
                    f"{provider_name} boot events",
                )
            )
        system_rows.sort(
            key=lambda row: _datetime(row.get("Timestamp"))
            or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        )
        performance_rows = await self._safe_events(
            EventQuery(
                log_names=["Microsoft-Windows-Diagnostics-Performance/Operational"],
                provider_names=["Microsoft-Windows-Diagnostics-Performance"],
                event_ids=list(range(100, 111)),
                since_hours=24 * 30,
                limit=100,
                include_event_data=True,
            ),
            warnings,
            "Boot performance events",
        )
        recent_boot_times = self._boot_times(system_rows, last_boot)
        previous_shutdown = self._previous_shutdown(system_rows, recent_boot_times)
        boot_record = next(
            (row for row in performance_rows if _integer(row.get("EventId")) == 100),
            None,
        )
        boot_duration = (
            _integer(self._event_data(boot_record).get("BootTime"))
            if boot_record is not None
            else None
        )
        startup_warnings = [
            self._event_record(row, details)
            for row in performance_rows
            if (_integer(row.get("EventId")) or 0) in range(101, 111)
        ]
        observations: list[Observation] = []
        if previous_shutdown == "unexpected":
            observations.append(
                Observation(
                    code="unexpected_previous_shutdown",
                    message="Windows recorded the previous shutdown as unexpected.",
                    severity="warning",
                )
            )
        evidence = None
        if details:
            evidence = [
                BootEvidence(
                    timestamp=_datetime(row.get("Timestamp")),
                    event_id=_integer(row.get("EventId")),
                    channel=_clean(row.get("Channel")),
                    record_id=_integer(row.get("RecordId")),
                    summary=self._summary(_clean(row.get("Message"))),
                )
                for row in [*system_rows, *performance_rows][:50]
            ]
        return BootInspection(
            recent_boot_times=recent_boot_times,
            current_uptime_seconds=uptime,
            previous_shutdown=previous_shutdown,
            latest_boot_duration_ms=boot_duration,
            startup_warnings=startup_warnings,
            evidence=evidence,
            observations=observations,
            warnings=warnings,
        )

    async def _safe_events(
        self,
        request: EventQuery,
        warnings: list[SourceWarning],
        source: str,
    ) -> list[dict[str, JsonValue]]:
        if self._event_reader is None:
            return []
        try:
            return await self._event_reader.query_events(request)
        except InspectionError as error:
            warnings.append(SourceWarning(source=source, code=error.code))
            return []

    @staticmethod
    def _event_record(row: dict[str, JsonValue], details: bool) -> EventRecord:
        message = _clean(row.get("Message"))
        return EventRecord(
            timestamp=_datetime(row.get("Timestamp")),
            level=_clean(row.get("Level"))
            or _EVENT_LEVELS.get(_integer(row.get("LevelCode")) or 0),
            provider=_clean(row.get("Provider")),
            event_id=_integer(row.get("EventId")),
            channel=_clean(row.get("Channel")),
            summary=WindowsInspectionProvider._summary(message),
            details=(
                EventDetails(
                    full_message=message,
                    record_id=_integer(row.get("RecordId")),
                    task=_clean(row.get("Task")),
                    opcode=_clean(row.get("Opcode")),
                    process_id=_integer(row.get("ProcessId")),
                    thread_id=_integer(row.get("ThreadId")),
                    activity_id=_clean(row.get("ActivityId")),
                    event_data=WindowsInspectionProvider._event_data(row),
                )
                if details
                else None
            ),
        )

    @staticmethod
    def _software_entry(row: dict[str, JsonValue], details: bool) -> SoftwareEntry:
        name = _clean(row.get("DisplayName"))
        if name is None:
            raise InspectionError("InvalidToolOutput")
        scope = _clean(row.get("Scope"))
        architecture = _clean(row.get("Architecture"))
        install_date = WindowsInspectionProvider._compact_date(row.get("InstallDate"))
        return SoftwareEntry(
            identity=SoftwareIdentity(
                name=name,
                publisher=_clean(row.get("Publisher")),
            ),
            configuration=SoftwareConfiguration(
                version=_clean(row.get("DisplayVersion")),
                installation_scope=(
                    "user" if scope == "user" else "machine" if scope == "machine" else None
                ),
                install_date=install_date,
            ),
            details=(
                SoftwareDetails(
                    install_location=_clean(row.get("InstallLocation")),
                    registry_source=_clean(row.get("RegistrySource")),
                    uninstall_identifier=_clean(row.get("UninstallIdentifier")),
                    product_identifier=_clean(row.get("ProductIdentifier")),
                    architecture=(
                        "x86" if architecture == "x86" else "x64" if architecture == "x64" else None
                    ),
                    install_source=_clean(row.get("InstallSource")),
                    install_channel=_clean(row.get("InstallChannel")),
                )
                if details
                else None
            ),
        )

    @staticmethod
    def _service_entry(row: dict[str, JsonValue], details: bool) -> ServiceEntry:
        name = _clean(row.get("Name"))
        if name is None:
            raise InspectionError("InvalidToolOutput")
        return ServiceEntry(
            identity=ServiceIdentity(
                name=name,
                display_name=_clean(row.get("DisplayName")),
            ),
            configuration=ServiceConfiguration(
                startup_type=_clean(row.get("StartMode")),
            ),
            current_state=ServiceState(
                state=_clean(row.get("State")),
                started=_boolean(row.get("Started")),
            ),
            health_status=_clean(row.get("Status")),
            details=(
                ServiceDetails(
                    binary_path=_clean(row.get("PathName")),
                    service_account=_clean(row.get("StartName")),
                    description=_clean(row.get("Description")),
                    pid=_integer(row.get("ProcessId")),
                    delayed_auto_start=_boolean(row.get("DelayedAutoStart")),
                    service_type=_clean(row.get("ServiceType")),
                    exit_code=_integer(row.get("ExitCode")),
                    service_specific_exit_code=_integer(
                        row.get("ServiceSpecificExitCode")
                    ),
                )
                if details
                else None
            ),
        )

    def _network_adapter(
        self,
        row: dict[str, JsonValue],
        config: dict[str, JsonValue],
        drivers: list[dict[str, JsonValue]],
        routes: list[dict[str, JsonValue]],
        details: bool,
    ) -> NetworkAdapter:
        addresses = self._strings(config.get("IPAddress"))
        ipv4_addresses = []
        ipv6_addresses = []
        for address in addresses:
            try:
                version = ip_address(address.split("%", maxsplit=1)[0]).version
            except ValueError:
                continue
            (ipv4_addresses if version == 4 else ipv6_addresses).append(address)
        pnp_id = _clean(row.get("PNPDeviceID"))
        driver = next(
            (
                item
                for item in drivers
                if (_clean(item.get("DeviceID")) or "").casefold()
                == (pnp_id or "").casefold()
            ),
            {},
        )
        interface_index = _integer(row.get("InterfaceIndex"))
        matching_routes = [
            NetworkRoute(
                destination=_clean(item.get("Destination")),
                mask=_clean(item.get("Mask")),
                next_hop=_clean(item.get("NextHop")),
                metric=_integer(item.get("Metric1")),
            )
            for item in routes
            if _integer(item.get("InterfaceIndex")) == interface_index
        ]
        connection_status = _integer(row.get("NetConnectionStatus"))
        return NetworkAdapter(
            identity=NetworkIdentity(
                name=_clean(row.get("NetConnectionID")) or _clean(row.get("Name")),
                description=_clean(row.get("Description")),
                classification=self._network_classification(row),
            ),
            configuration=NetworkConfiguration(enabled=_boolean(row.get("NetEnabled"))),
            current_state=NetworkState(
                connected=(connection_status == 2 if connection_status is not None else None),
                link_speed_bps=self._positive_integer(row.get("Speed")),
                ipv4_addresses=ipv4_addresses,
                ipv6_addresses=ipv6_addresses,
                default_gateways=self._strings(config.get("DefaultIPGateway")),
                dns_servers=self._strings(config.get("DNSServerSearchOrder")),
            ),
            health_status=_clean(row.get("Status")),
            details=(
                NetworkDetails(
                    mac_address=_clean(row.get("MACAddress")),
                    dhcp_enabled=_boolean(config.get("DHCPEnabled")),
                    dhcp_server=_clean(config.get("DHCPServer")),
                    dhcp_lease_obtained=_datetime(config.get("DHCPLeaseObtained")),
                    dhcp_lease_expires=_datetime(config.get("DHCPLeaseExpires")),
                    subnets=self._strings(config.get("IPSubnet")),
                    dns_domain=_clean(config.get("DNSDomain")),
                    dns_suffixes=self._strings(config.get("DNSDomainSuffixSearchOrder")),
                    mtu_bytes=_integer(config.get("MTU")),
                    driver_provider=_clean(driver.get("DriverProviderName")),
                    driver_version=_clean(driver.get("DriverVersion")),
                    pnp_device_id=pnp_id,
                    interface_index=interface_index,
                    interface_guid=_clean(row.get("GUID")),
                    routes=matching_routes,
                )
                if details
                else None
            ),
        )

    @staticmethod
    def _network_classification(
        row: dict[str, JsonValue],
    ) -> Literal["Ethernet", "Wi-Fi", "virtual", "other"]:
        if _boolean(row.get("PhysicalAdapter")) is False:
            return "virtual"
        adapter_type = _integer(row.get("AdapterTypeID"))
        combined_name = " ".join(
            filter(
                None,
                [
                    _clean(row.get("NetConnectionID")),
                    _clean(row.get("Name")),
                    _clean(row.get("Description")),
                ],
            )
        ).casefold()
        if "bluetooth" in combined_name:
            return "other"
        if adapter_type == 9 or any(
            token in combined_name for token in ("wi-fi", "wireless", "802.11")
        ):
            return "Wi-Fi"
        if adapter_type == 0:
            return "Ethernet"
        return "other"

    def _physical_disk(
        self,
        row: dict[str, JsonValue],
        disks: list[dict[str, JsonValue]],
        details: bool,
    ) -> PhysicalDisk:
        number = _integer(row.get("DeviceId"))
        disk = next(
            (item for item in disks if _integer(item.get("Number")) == number),
            {},
        )
        media_code = _integer(row.get("MediaType"))
        bus_code = _integer(row.get("BusType"))
        health_code = _integer(row.get("HealthStatus"))
        bus_type = _BUS_TYPES.get(bus_code) if bus_code is not None else None
        media_type = _MEDIA_TYPES.get(media_code) if media_code is not None else None
        if bus_type == "NVMe" and media_type in (None, "Unspecified"):
            media_type = "NVMe SSD"
        partition_code = _integer(disk.get("PartitionStyle"))
        return PhysicalDisk(
            identity=DiskIdentity(number=number, model=_clean(row.get("FriendlyName"))),
            configuration=DiskConfiguration(
                media_type=media_type,
                bus_type=bus_type,
                capacity_bytes=_integer(row.get("Size")),
            ),
            health_status=(
                _HEALTH_STATUSES.get(health_code) if health_code is not None else None
            ),
            operational_status=self._status_list(row.get("OperationalStatus")),
            details=(
                DiskDetails(
                    serial_number=self._useful_serial(row.get("SerialNumber")),
                    firmware_version=_clean(row.get("FirmwareVersion")),
                    partition_style=(
                        _PARTITION_STYLES.get(partition_code)
                        if partition_code is not None
                        else None
                    ),
                    device_id=_clean(row.get("DeviceId")),
                )
                if details
                else None
            ),
        )

    def _storage_volume(
        self, row: dict[str, JsonValue], details: bool
    ) -> StorageVolume:
        total = _integer(row.get("Size"))
        free = _integer(row.get("SizeRemaining"))
        used = total - free if total is not None and free is not None else None
        free_percent = free / total * 100 if total and free is not None else None
        drive_letter = _clean(row.get("DriveLetter"))
        if drive_letter and not drive_letter.endswith(":"):
            drive_letter += ":"
        health_code = _integer(row.get("HealthStatus"))
        return StorageVolume(
            identity=VolumeIdentity(
                drive_letter=drive_letter,
                name=_clean(row.get("FileSystemLabel")),
            ),
            configuration=VolumeConfiguration(
                filesystem=_clean(row.get("FileSystem")),
                total_bytes=total,
            ),
            current_state=VolumeState(
                used_bytes=used,
                free_bytes=free,
                free_percent=free_percent,
            ),
            health_status=(
                _HEALTH_STATUSES.get(health_code) if health_code is not None else None
            ),
            operational_status=self._status_list(row.get("OperationalStatus")),
            details=(VolumeDetails(path=_clean(row.get("Path"))) if details else None),
        )

    @staticmethod
    def _storage_observations(
        disks: list[PhysicalDisk], volumes: list[StorageVolume]
    ) -> list[Observation]:
        observations: list[Observation] = []
        for disk in disks:
            if disk.health_status in {"Warning", "Unhealthy"}:
                observations.append(
                    Observation(
                        code="disk_health_not_healthy",
                        message=(
                            f"Physical disk {disk.identity.number} reports "
                            f"{disk.health_status.lower()} health."
                        ),
                        severity="warning",
                    )
                )
        for volume in volumes:
            percent = volume.current_state.free_percent
            name = volume.identity.drive_letter or volume.identity.name or "unnamed volume"
            if percent is not None and percent < 10:
                observations.append(
                    Observation(
                        code="low_volume_free_space",
                        message=f"Volume {name} has {percent:.1f}% free space.",
                        severity="warning",
                    )
                )
        return observations

    @staticmethod
    def _gpu_active(row: dict[str, JsonValue]) -> bool:
        return bool(
            _integer(row.get("CurrentHorizontalResolution"))
            and _integer(row.get("CurrentVerticalResolution"))
        )

    @staticmethod
    def _status_list(value: JsonValue | None) -> list[str]:
        values = value if isinstance(value, list) else [value]
        result = []
        for item in values:
            code = _integer(item)
            if code is not None:
                result.append(_OPERATIONAL_STATUSES.get(code, f"Code {code}"))
        return result

    @staticmethod
    def _strings(value: JsonValue | None) -> list[str]:
        values = value if isinstance(value, list) else [value]
        return [text for item in values if (text := _clean(item)) is not None]

    @staticmethod
    def _positive_integer(value: JsonValue | None) -> int | None:
        number = _integer(value)
        return number if number is not None and number > 0 else None

    @staticmethod
    def _compact_date(value: JsonValue | None) -> date | None:
        text = _clean(value)
        if text is None or len(text) != 8 or not text.isdigit():
            return None
        try:
            return date(int(text[:4]), int(text[4:6]), int(text[6:8]))
        except ValueError:
            return None

    @staticmethod
    def _calendar_date(value: JsonValue | None) -> date | None:
        timestamp = _datetime(value)
        return timestamp.date() if timestamp is not None else None

    @staticmethod
    def _event_data(row: dict[str, JsonValue] | None) -> dict[str, JsonValue]:
        if row is None:
            return {}
        value = row.get("EventData")
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _event_value(data: dict[str, JsonValue], *names: str) -> str | None:
        normalized = {key.casefold(): value for key, value in data.items()}
        for name in names:
            value = _clean(normalized.get(name.casefold()))
            if value is not None:
                return value
        return None

    @classmethod
    def _is_crash_event(cls, event_id: int | None, data: dict[str, JsonValue]) -> bool:
        if event_id in {1000, 1002}:
            return True
        if event_id != 1001:
            return False
        event_name = cls._event_value(data, "EventName")
        return event_name is not None and any(
            marker in event_name.casefold() for marker in _WER_CRASH_MARKERS
        )

    @classmethod
    def _crash_type(cls, event_id: int | None, data: dict[str, JsonValue]) -> str:
        if event_id == 1000:
            return "application crash"
        if event_id == 1002:
            return "application hang"
        event_name = cls._event_value(data, "EventName")
        return event_name or "Windows Error Reporting crash"

    @classmethod
    def _crash_application(
        cls, event_id: int | None, data: dict[str, JsonValue]
    ) -> str | None:
        application = cls._event_value(
            data, "AppName", "FaultingApplicationName", "ApplicationName"
        )
        if application is not None or event_id != 1001:
            return application
        event_name = (cls._event_value(data, "EventName") or "").casefold()
        if any(marker in event_name for marker in ("app", "bex", "crashpad", "radar")):
            return cls._event_value(data, "P1")
        return None

    @classmethod
    def _crash_module(
        cls, event_id: int | None, data: dict[str, JsonValue]
    ) -> str | None:
        module = cls._event_value(
            data, "ModuleName", "FaultingModuleName", "FaultModuleName"
        )
        if module is not None:
            return module
        event_name = (cls._event_value(data, "EventName") or "").casefold()
        return cls._event_value(data, "P4") if event_id == 1001 and "appcrash" in event_name else None

    @classmethod
    def _crash_exception_code(
        cls, event_id: int | None, data: dict[str, JsonValue]
    ) -> str | None:
        code = cls._event_value(data, "ExceptionCode")
        if code is not None:
            return code
        event_name = (cls._event_value(data, "EventName") or "").casefold()
        return cls._event_value(data, "P7") if event_id == 1001 and "appcrash" in event_name else None

    @classmethod
    def _crash_module_version(
        cls, event_id: int | None, data: dict[str, JsonValue]
    ) -> str | None:
        version = cls._event_value(data, "ModuleVersion", "FaultingModuleVersion")
        if version is not None:
            return version
        event_name = (cls._event_value(data, "EventName") or "").casefold()
        return cls._event_value(data, "P5") if event_id == 1001 and "appcrash" in event_name else None

    @classmethod
    def _crash_exception_offset(
        cls, event_id: int | None, data: dict[str, JsonValue]
    ) -> str | None:
        offset = cls._event_value(data, "ExceptionOffset")
        if offset is not None:
            return offset
        event_name = (cls._event_value(data, "EventName") or "").casefold()
        return cls._event_value(data, "P8") if event_id == 1001 and "appcrash" in event_name else None

    @classmethod
    def _crash_application_version(
        cls, event_id: int | None, data: dict[str, JsonValue]
    ) -> str | None:
        version = cls._event_value(data, "AppVersion", "ApplicationVersion")
        if version is not None:
            return version
        if event_id != 1001:
            return None
        event_name = (cls._event_value(data, "EventName") or "").casefold()
        if "moapphang" in event_name:
            return cls._event_value(data, "P3")
        if any(marker in event_name for marker in ("appcrash", "bex", "crashpad", "radar")):
            return cls._event_value(data, "P2")
        return None

    @staticmethod
    def _crash_metadata(data: dict[str, JsonValue]) -> dict[str, JsonValue]:
        normalized = {key.casefold(): (key, value) for key, value in data.items()}
        result: dict[str, JsonValue] = {}
        for field in _CRASH_METADATA_FIELDS:
            entry = normalized.get(field.casefold())
            if entry is None:
                continue
            original_key, value = entry
            if value is not None and value != "":
                result[original_key] = value
        return result

    @staticmethod
    def _summary(message: str | None) -> str | None:
        if message is None:
            return None
        summary = " ".join(message.split())
        return summary if len(summary) <= 240 else f"{summary[:237]}..."

    @staticmethod
    def _boot_times(
        rows: list[dict[str, JsonValue]], last_boot: datetime | None
    ) -> list[datetime]:
        kernel_starts = sorted(
            (
                timestamp
                for row in rows
                if _integer(row.get("EventId")) == 12
                if (timestamp := _datetime(row.get("Timestamp"))) is not None
            ),
            reverse=True,
        )
        event_log_starts = sorted(
            (
                timestamp
                for row in rows
                if _integer(row.get("EventId")) == 6005
                if (timestamp := _datetime(row.get("Timestamp"))) is not None
            ),
            reverse=True,
        )
        candidates = ([last_boot] if last_boot is not None else []) + kernel_starts + event_log_starts
        result: list[datetime] = []
        for timestamp in candidates:
            if not any(abs((timestamp - existing).total_seconds()) < 300 for existing in result):
                result.append(timestamp)
        result.sort(reverse=True)
        return result[:10]

    @staticmethod
    def _previous_shutdown(
        rows: list[dict[str, JsonValue]], boot_times: list[datetime]
    ) -> Literal["normal", "unexpected"] | None:
        shutdowns = [
            (timestamp, event_id)
            for row in rows
            if (event_id := _integer(row.get("EventId"))) in {13, 41, 6006, 6008}
            if (timestamp := _datetime(row.get("Timestamp"))) is not None
        ]
        if not shutdowns:
            return None
        current_boot = boot_times[0] if boot_times else None
        if current_boot is not None:
            plausible = [
                item
                for item in shutdowns
                if item[0] <= current_boot or (item[0] - current_boot).total_seconds() < 600
            ]
            if plausible:
                shutdowns = plausible
        _, event_id = max(shutdowns, key=lambda item: item[0])
        return "unexpected" if event_id in {41, 6008} else "normal"

    @staticmethod
    def _memory_module(row: dict[str, JsonValue]) -> MemoryModule:
        form_factor = _integer(row.get("FormFactor"))
        memory_type = _integer(row.get("SMBIOSMemoryType"))
        millivolts = _number(row.get("ConfiguredVoltage"))
        return MemoryModule(
            slot=_clean(row.get("DeviceLocator")),
            bank=_clean(row.get("BankLabel")),
            capacity_bytes=_integer(row.get("Capacity")),
            manufacturer=_clean(row.get("Manufacturer")),
            model=_clean(row.get("Model")),
            part_number=_clean(row.get("PartNumber")),
            rated_speed_mhz=_integer(row.get("Speed")),
            configured_speed_mhz=_integer(row.get("ConfiguredClockSpeed")),
            form_factor=(
                _MEMORY_FORM_FACTORS.get(form_factor) if form_factor is not None else None
            ),
            memory_type=(
                _SMBIOS_MEMORY_TYPES.get(memory_type) if memory_type is not None else None
            ),
            configured_voltage_volts=millivolts / 1000 if millivolts else None,
            serial_number=WindowsInspectionProvider._useful_serial(row.get("SerialNumber")),
        )

    @staticmethod
    def _memory_observations(rows: list[dict[str, JsonValue]]) -> list[Observation]:
        if len(rows) < 2:
            return []
        comparisons = {
            "Capacity": ("mixed_module_capacities", "Installed DIMM capacities differ."),
            "ConfiguredClockSpeed": (
                "mixed_configured_speeds",
                "Installed DIMMs report different configured speeds.",
            ),
            "SMBIOSMemoryType": ("mixed_memory_types", "Installed DIMM memory types differ."),
            "PartNumber": ("mixed_part_numbers", "Installed DIMM part numbers differ."),
        }
        observations: list[Observation] = []
        for field, (code, message) in comparisons.items():
            values = {str(row[field]).strip() for row in rows if row.get(field) not in (None, "")}
            if len(values) > 1:
                observations.append(Observation(code=code, message=message))
        return observations

    @staticmethod
    def _joined_values(rows: list[dict[str, JsonValue]], field: str) -> str | None:
        values = []
        for row in rows:
            value = _clean(row.get(field))
            if value is not None and value not in values:
                values.append(value)
        return "; ".join(values) if values else None

    @staticmethod
    def _kilobytes(value: JsonValue | None) -> int | None:
        number = _integer(value)
        return number * 1024 if number is not None else None

    @staticmethod
    def _useful_serial(value: JsonValue | None) -> str | None:
        serial = _clean(value)
        if serial is None:
            return None
        normalized = serial.replace("-", "").replace(" ", "").upper()
        if normalized in {"0", "00000000", "FFFFFFFF", "UNKNOWN", "DEFAULTSTRING"}:
            return None
        return serial
