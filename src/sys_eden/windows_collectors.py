"""Curated Windows collectors built on the allowlisted generic CIM reader."""

import re
from datetime import UTC, datetime

from pydantic import JsonValue

from sys_eden.inspection import CimQuery, CimReader, InspectionError
from sys_eden.inspection_models import (
    CpuConfiguration,
    CpuDetails,
    CpuIdentity,
    CpuInspection,
    CpuState,
    MemoryConfiguration,
    MemoryDetails,
    MemoryIdentity,
    MemoryInspection,
    MemoryModule,
    MemoryState,
    Observation,
    SourceWarning,
    SystemDetails,
    SystemDrive,
    SystemIdentity,
    SystemInspection,
    SystemState,
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
