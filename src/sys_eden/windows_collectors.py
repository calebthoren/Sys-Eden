"""Curated Windows collectors built on the allowlisted generic CIM reader."""

import re
from datetime import UTC, datetime
from ipaddress import ip_address
from typing import Literal

from pydantic import JsonValue

from sys_eden.inspection import CimQuery, CimReader, InspectionError
from sys_eden.inspection_models import (
    CpuConfiguration,
    CpuDetails,
    CpuIdentity,
    CpuInspection,
    CpuState,
    DiskConfiguration,
    DiskDetails,
    DiskIdentity,
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
    SourceWarning,
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

    def __init__(self, reader: CimReader):
        self._reader = reader

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
            firmware_release_date=_datetime(bios.get("ReleaseDate")),
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
                driver_date=_datetime(row.get("DriverDate")),
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
