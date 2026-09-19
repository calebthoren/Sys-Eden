"""Human CLI presentation for structured inspection data."""

from datetime import datetime

from sys_eden.inspection import InspectionResult
from sys_eden.inspection_models import CpuInspection, MemoryInspection, SystemInspection

UNAVAILABLE = "unavailable"


def format_bytes(value: int | None) -> str:
    if value is None:
        return UNAVAILABLE
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    amount = float(value)
    for unit in units[:-1]:
        if abs(amount) < 1024:
            return f"{amount:.0f} {unit}" if unit == "B" else f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{amount:.1f} {units[-1]}"


def format_frequency(value: float | None) -> str:
    if value is None:
        return UNAVAILABLE
    if value >= 1000:
        return f"{value / 1000:.2f} GHz"
    return f"{value:,.0f} MHz"


def format_memory_speed(value: int | None) -> str:
    return UNAVAILABLE if value is None else f"{value:,} MHz"


def format_percent(value: float | None) -> str:
    return UNAVAILABLE if value is None else f"{value:.1f}%"


def format_timestamp(value: datetime | None) -> str:
    return UNAVAILABLE if value is None else value.astimezone().isoformat(timespec="seconds")


def format_duration(value: float | None) -> str:
    if value is None:
        return UNAVAILABLE
    seconds = max(0, int(value))
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, _ = divmod(seconds, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours or days:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return " ".join(parts)


def _text(value: object | None) -> str:
    if value is None or value == "":
        return UNAVAILABLE
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def _section(title: str, rows: list[tuple[str, str]]) -> list[str]:
    return [title, *(f"  {label}: {value}" for label, value in rows)]


def _footer(data: SystemInspection | CpuInspection | MemoryInspection) -> list[str]:
    lines: list[str] = []
    if data.observations:
        lines.append("Observations")
        lines.extend(f"  [{item.severity}] {item.message}" for item in data.observations)
    if data.warnings:
        lines.append("Unavailable sources")
        lines.extend(f"  {item.source}: {item.code}" for item in data.warnings)
    return lines


def _system(data: SystemInspection) -> list[str]:
    state = data.current_state
    drive = state.system_drive
    lines = ["System"]
    lines += _section(
        "Identity",
        [
            ("Device name", _text(data.identity.device_name)),
            ("Manufacturer", _text(data.identity.manufacturer)),
            ("Model", _text(data.identity.model)),
        ],
    )
    lines += _section(
        "Configuration",
        [
            ("Windows edition", _text(data.configuration.edition)),
            ("Windows version", _text(data.configuration.version)),
            ("Windows build", _text(data.configuration.build)),
            ("Architecture", _text(data.configuration.architecture)),
        ],
    )
    lines += _section(
        "Current state",
        [
            ("Uptime", format_duration(state.uptime_seconds)),
            ("Last boot", format_timestamp(state.last_boot_time)),
            ("CPU", _text(state.cpu_model)),
            ("Installed RAM", format_bytes(state.installed_ram_bytes)),
            ("Primary GPU", _text(state.primary_gpu)),
            ("System drive", _text(drive.name if drive else None)),
            ("Drive free space", format_bytes(drive.free_bytes if drive else None)),
            ("Drive free percentage", format_percent(drive.free_percent if drive else None)),
        ],
    )
    lines += _section("Health/status", [("Windows status", _text(data.health_status))])
    if data.details:
        item = data.details
        lines += _section(
            "Details",
            [
                ("Motherboard manufacturer", _text(item.motherboard_manufacturer)),
                ("Motherboard model", _text(item.motherboard_model)),
                ("Firmware vendor", _text(item.firmware_vendor)),
                ("Firmware version", _text(item.firmware_version)),
                ("Firmware release date", format_timestamp(item.firmware_release_date)),
                ("Firmware mode", _text(item.firmware_mode)),
                ("Secure Boot", _text(item.secure_boot_enabled)),
                ("TPM present", _text(item.tpm_present)),
                ("TPM version", _text(item.tpm_version)),
                ("Windows installed", format_timestamp(item.windows_install_date)),
                ("Windows product type", _text(item.windows_product_type)),
                ("Windows edition ID", _text(item.windows_edition_id)),
                ("Hypervisor present", _text(item.hypervisor_present)),
            ],
        )
    return lines + _footer(data)


def _cpu(data: CpuInspection) -> list[str]:
    lines = ["CPU"]
    lines += _section(
        "Identity",
        [
            ("Processor", _text(data.identity.model)),
            ("Manufacturer", _text(data.identity.manufacturer)),
            ("Architecture", _text(data.identity.architecture)),
        ],
    )
    lines += _section(
        "Configuration",
        [
            ("Physical cores", _text(data.configuration.physical_cores)),
            ("Logical processors", _text(data.configuration.logical_processors)),
            ("Base clock", format_frequency(data.configuration.base_clock_mhz)),
            ("Maximum clock", format_frequency(data.configuration.max_clock_mhz)),
        ],
    )
    lines += _section(
        "Current state",
        [
            ("Total utilization", format_percent(data.current_state.total_utilization_percent)),
            ("Current clock", format_frequency(data.current_state.current_clock_mhz)),
        ],
    )
    lines += _section("Health/status", [("Device status", _text(data.health_status))])
    if data.details:
        item = data.details
        temperature = (
            UNAVAILABLE
            if item.temperature_celsius is None
            else f"{item.temperature_celsius:.1f} °C"
        )
        lines += _section(
            "Details",
            [
                ("Socket", _text(item.socket)),
                ("Processor ID", _text(item.processor_id)),
                ("Family", _text(item.family)),
                ("Revision", _text(item.revision)),
                ("Stepping", _text(item.stepping)),
                ("Level", _text(item.level)),
                ("L2 cache", format_bytes(item.l2_cache_bytes)),
                ("L3 cache", format_bytes(item.l3_cache_bytes)),
                ("Firmware virtualization", _text(item.virtualization_firmware_enabled)),
                (
                    "Second-level address translation",
                    _text(item.second_level_address_translation),
                ),
                ("Sockets detected", _text(item.socket_count)),
                ("NUMA nodes", _text(item.numa_node_count)),
                ("Device ID", _text(item.device_id)),
                ("Temperature", temperature),
            ],
        )
        if item.per_core_utilization_percent:
            lines += _section(
                "Per-core utilization",
                [
                    (core, format_percent(value))
                    for core, value in sorted(
                        item.per_core_utilization_percent.items(),
                        key=lambda pair: (
                            (0, int(pair[0])) if pair[0].isdigit() else (1, pair[0])
                        ),
                    )
                ],
            )
    return lines + _footer(data)


def _ram(data: MemoryInspection) -> list[str]:
    configured = ", ".join(
        format_memory_speed(value) for value in data.configuration.configured_speeds_mhz
    )
    rated = ", ".join(
        format_memory_speed(value) for value in data.configuration.rated_speeds_mhz
    )
    lines = ["RAM"]
    lines += _section(
        "Identity",
        [
            ("Installed memory", format_bytes(data.identity.total_installed_bytes)),
            ("Modules detected", _text(data.identity.module_count)),
        ],
    )
    lines += _section(
        "Configuration",
        [
            ("Configured speed", configured or UNAVAILABLE),
            ("Reported module speed", rated or UNAVAILABLE),
        ],
    )
    lines += _section(
        "Current state",
        [
            ("Used memory", format_bytes(data.current_state.used_bytes)),
            ("Available memory", format_bytes(data.current_state.available_bytes)),
            ("Usage", format_percent(data.current_state.usage_percent)),
        ],
    )
    lines += _section("Health/status", [("Memory status", _text(data.health_status))])
    if data.details:
        for index, item in enumerate(data.details.modules, start=1):
            voltage = (
                UNAVAILABLE
                if item.configured_voltage_volts is None
                else f"{item.configured_voltage_volts:.3f} V"
            )
            lines += _section(
                f"Module {index}",
                [
                    ("Slot", _text(item.slot)),
                    ("Bank", _text(item.bank)),
                    ("Capacity", format_bytes(item.capacity_bytes)),
                    ("Manufacturer", _text(item.manufacturer)),
                    ("Model", _text(item.model)),
                    ("Part number", _text(item.part_number)),
                    ("Rated speed", format_memory_speed(item.rated_speed_mhz)),
                    ("Configured speed", format_memory_speed(item.configured_speed_mhz)),
                    ("Form factor", _text(item.form_factor)),
                    ("Memory type", _text(item.memory_type)),
                    ("Configured voltage", voltage),
                    ("Serial number", _text(item.serial_number)),
                ],
            )
    return lines + _footer(data)


def render_human(result: InspectionResult) -> str:
    if not result.success or result.data is None:
        return f"{result.capability.title()}\nError: {result.error or 'unknown'}"
    if isinstance(result.data, SystemInspection):
        lines = _system(result.data)
    elif isinstance(result.data, CpuInspection):
        lines = _cpu(result.data)
    else:
        lines = _ram(result.data)
    return "\n".join(lines)
