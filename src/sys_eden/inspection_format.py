"""Human CLI presentation for structured inspection data."""

import sys
import unicodedata
from datetime import date, datetime

from sys_eden.inspection import InspectionResult
from sys_eden.inspection_models import (
    BootInspection,
    CpuInspection,
    CrashesInspection,
    DriversInspection,
    EventsInspection,
    GpuInspection,
    MemoryInspection,
    NetworkInspection,
    ProcessesInspection,
    ServicesInspection,
    SoftwareInspection,
    StartupInspection,
    StorageInspection,
    SystemInspection,
)

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


def format_link_speed(value: int | None) -> str:
    if value is None:
        return UNAVAILABLE
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f} Gbps"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.0f} Mbps"
    if value >= 1_000:
        return f"{value / 1_000:.0f} Kbps"
    return f"{value} bps"


def format_throughput(value: int | None) -> str:
    return UNAVAILABLE if value is None else f"{format_bytes(value)}/s"


def format_percent(value: float | None) -> str:
    return UNAVAILABLE if value is None else f"{value:.1f}%"


def format_timestamp(value: datetime | None) -> str:
    return UNAVAILABLE if value is None else value.astimezone().isoformat(timespec="seconds")


def format_date(value: date | None) -> str:
    return UNAVAILABLE if value is None else value.isoformat()


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
    text = "".join(
        " " if character.isspace() else character
        for character in str(value)
        if unicodedata.category(character) not in {"Cc", "Cf", "Cs"}
        or character.isspace()
    )
    return " ".join(text.split()) or UNAVAILABLE


def _section(title: str, rows: list[tuple[str, str]]) -> list[str]:
    return [title, *(f"  {label}: {value}" for label, value in rows)]


def _footer(
    data: (
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
    ),
) -> list[str]:
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
                ("Firmware release date", format_date(item.firmware_release_date)),
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


def _gpu(data: GpuInspection) -> list[str]:
    lines = ["GPU"]
    if not data.adapters:
        lines += _section("Identity", [("Adapters", "none detected")])
    for index, adapter in enumerate(data.adapters, start=1):
        lines += _section(
            f"Adapter {index} - Identity",
            [
                ("GPU", _text(adapter.identity.name)),
                ("Vendor", _text(adapter.identity.vendor)),
                ("Type", _text(adapter.identity.adapter_type)),
            ],
        )
        lines += _section(
            f"Adapter {index} - Configuration",
            [
                ("Dedicated VRAM", format_bytes(adapter.configuration.dedicated_vram_bytes)),
                ("Driver version", _text(adapter.configuration.driver_version)),
                ("Driver date", format_date(adapter.configuration.driver_date)),
            ],
        )
        lines += _section(
            f"Adapter {index} - Current state",
            [
                ("Utilization", format_percent(adapter.current_state.utilization_percent)),
                (
                    "Temperature",
                    UNAVAILABLE
                    if adapter.current_state.temperature_celsius is None
                    else f"{adapter.current_state.temperature_celsius:.1f} °C",
                ),
                ("Active display", _text(adapter.current_state.active_display)),
                ("Primary", _text(adapter.current_state.primary)),
            ],
        )
        lines += _section(
            f"Adapter {index} - Health/status",
            [("Device status", _text(adapter.health_status))],
        )
        if adapter.details:
            item = adapter.details
            lines += _section(
                f"Adapter {index} - Details",
                [
                    ("PNP device ID", _text(item.pnp_device_id)),
                    ("Device ID", _text(item.device_id)),
                    ("Adapter status", _text(item.adapter_status)),
                    ("Device error code", _text(item.device_error_code)),
                    ("Driver provider", _text(item.driver_provider)),
                    ("Driver INF", _text(item.driver_inf)),
                    ("Driver signed", _text(item.driver_signed)),
                    ("Video processor", _text(item.video_processor)),
                    ("Current clock", format_frequency(item.current_clock_mhz)),
                    ("VRAM used", format_bytes(item.vram_used_bytes)),
                    (
                        "Power",
                        UNAVAILABLE if item.power_watts is None else f"{item.power_watts:.1f} W",
                    ),
                    ("Display resolution", _text(item.display_resolution)),
                    ("Display refresh", _text(item.display_refresh_hz)),
                ],
            )
    return lines + _footer(data)


def _storage(data: StorageInspection) -> list[str]:
    lines = ["Storage"]
    if not data.physical_disks:
        lines += _section("Physical disks", [("Disks", "none detected")])
    for index, disk in enumerate(data.physical_disks, start=1):
        lines += _section(
            f"Physical disk {index} - Identity",
            [
                ("Disk number", _text(disk.identity.number)),
                ("Model", _text(disk.identity.model)),
            ],
        )
        lines += _section(
            f"Physical disk {index} - Configuration",
            [
                ("Media type", _text(disk.configuration.media_type)),
                ("Bus type", _text(disk.configuration.bus_type)),
                ("Capacity", format_bytes(disk.configuration.capacity_bytes)),
            ],
        )
        lines += _section(
            f"Physical disk {index} - Health/status",
            [
                ("Health", _text(disk.health_status)),
                ("Operational status", ", ".join(disk.operational_status) or UNAVAILABLE),
            ],
        )
        if disk.details:
            item = disk.details
            lines += _section(
                f"Physical disk {index} - Details",
                [
                    ("Serial number", _text(item.serial_number)),
                    ("Firmware version", _text(item.firmware_version)),
                    ("Partition style", _text(item.partition_style)),
                    ("Device ID", _text(item.device_id)),
                    ("TRIM enabled", _text(item.trim_enabled)),
                    (
                        "Temperature",
                        UNAVAILABLE
                        if item.temperature_celsius is None
                        else f"{item.temperature_celsius:.1f} °C",
                    ),
                    ("Read errors", _text(item.read_errors)),
                    ("Write errors", _text(item.write_errors)),
                ],
            )
    if not data.volumes:
        lines += _section("Mounted volumes", [("Volumes", "none detected")])
    for index, volume in enumerate(data.volumes, start=1):
        lines += _section(
            f"Volume {index} - Identity",
            [
                ("Drive", _text(volume.identity.drive_letter)),
                ("Name", _text(volume.identity.name)),
            ],
        )
        lines += _section(
            f"Volume {index} - Configuration",
            [
                ("Filesystem", _text(volume.configuration.filesystem)),
                ("Capacity", format_bytes(volume.configuration.total_bytes)),
            ],
        )
        lines += _section(
            f"Volume {index} - Current state",
            [
                ("Used", format_bytes(volume.current_state.used_bytes)),
                ("Free", format_bytes(volume.current_state.free_bytes)),
                ("Free percentage", format_percent(volume.current_state.free_percent)),
            ],
        )
        lines += _section(
            f"Volume {index} - Health/status",
            [
                ("Health", _text(volume.health_status)),
                ("Operational status", ", ".join(volume.operational_status) or UNAVAILABLE),
            ],
        )
        if volume.details:
            lines += _section(
                f"Volume {index} - Details",
                [
                    ("Path", _text(volume.details.path)),
                    ("Encryption", _text(volume.details.encryption_status)),
                ],
            )
    return lines + _footer(data)


def _network(data: NetworkInspection) -> list[str]:
    lines = ["Network"]
    if not data.adapters:
        lines += _section("Adapters", [("Relevant adapters", "none detected")])
    for index, adapter in enumerate(data.adapters, start=1):
        lines += _section(
            f"Adapter {index} - Identity",
            [
                ("Name", _text(adapter.identity.name)),
                ("Hardware/model", _text(adapter.identity.description)),
                ("Type", _text(adapter.identity.classification)),
            ],
        )
        lines += _section(
            f"Adapter {index} - Configuration",
            [("Enabled", _text(adapter.configuration.enabled))],
        )
        state = adapter.current_state
        state_rows = [
                ("Connected", _text(state.connected)),
                ("Link speed", format_link_speed(state.link_speed_bps)),
                ("IPv4", ", ".join(state.ipv4_addresses) or UNAVAILABLE),
                ("IPv6", ", ".join(state.ipv6_addresses) or UNAVAILABLE),
                ("Default gateway", ", ".join(state.default_gateways) or UNAVAILABLE),
                ("DNS servers", ", ".join(state.dns_servers) or UNAVAILABLE),
                ("Receive throughput", format_throughput(state.receive_bytes_per_second)),
                ("Send throughput", format_throughput(state.send_bytes_per_second)),
        ]
        if adapter.identity.classification == "Wi-Fi":
            state_rows += [
                ("Wi-Fi SSID", _text(state.wifi_ssid)),
                ("Wi-Fi signal", format_percent(state.wifi_signal_percent)),
                ("Wi-Fi receive speed", format_link_speed(state.wifi_receive_link_speed_bps)),
                ("Wi-Fi transmit speed", format_link_speed(state.wifi_transmit_link_speed_bps)),
            ]
        lines += _section(f"Adapter {index} - Current state", state_rows)
        lines += _section(
            f"Adapter {index} - Health/status",
            [("Adapter status", _text(adapter.health_status))],
        )
        if adapter.details:
            item = adapter.details
            lines += _section(
                f"Adapter {index} - Details",
                [
                    ("MAC address", _text(item.mac_address)),
                    ("DHCP enabled", _text(item.dhcp_enabled)),
                    ("DHCP server", _text(item.dhcp_server)),
                    ("DHCP lease obtained", format_timestamp(item.dhcp_lease_obtained)),
                    ("DHCP lease expires", format_timestamp(item.dhcp_lease_expires)),
                    ("Subnets/prefixes", ", ".join(item.subnets) or UNAVAILABLE),
                    ("DNS domain", _text(item.dns_domain)),
                    ("DNS suffixes", ", ".join(item.dns_suffixes) or UNAVAILABLE),
                    ("MTU", _text(item.mtu_bytes)),
                    ("Driver provider", _text(item.driver_provider)),
                    ("Driver version", _text(item.driver_version)),
                    ("PNP device ID", _text(item.pnp_device_id)),
                    ("Interface index", _text(item.interface_index)),
                    ("Interface GUID", _text(item.interface_guid)),
                    ("Receive errors", _text(item.receive_errors)),
                    ("Send errors", _text(item.send_errors)),
                    ("Receive discards", _text(item.receive_discards)),
                    ("Send discards", _text(item.send_discards)),
                ],
            )
            for route_index, route in enumerate(item.routes, start=1):
                lines += _section(
                    f"Adapter {index} - IPv4 route {route_index}",
                    [
                        ("Destination", _text(route.destination)),
                        ("Mask", _text(route.mask)),
                        ("Next hop", _text(route.next_hop)),
                        ("Metric", _text(route.metric)),
                    ],
                )
    return lines + _footer(data)


def _processes(data: ProcessesInspection) -> list[str]:
    lines = [
        "Processes",
        "Summary",
        f"  Detected: {data.total_detected}",
        f"  Shown: {data.returned_count}",
        "Current state",
    ]
    for process in data.processes:
        state = process.current_state
        lines.append(
            "  "
            f"PID {process.identity.pid} | {_text(process.identity.name)} | "
            f"CPU {format_percent(state.cpu_percent)} | "
            f"RAM {format_bytes(state.memory_bytes)} | "
            f"user {_text(state.user)} | {_text(state.status)}"
        )
        if process.details:
            item = process.details
            lines += _section(
                f"PID {process.identity.pid} - Details",
                [
                    ("Executable path", _text(item.executable_path)),
                    ("Command line", _text(item.command_line)),
                    ("Parent PID", _text(item.parent_pid)),
                    ("Start time", format_timestamp(item.start_time)),
                    ("Threads", _text(item.thread_count)),
                    ("Handles", _text(item.handle_count)),
                    ("I/O read", format_throughput(item.io_read_bytes_per_second)),
                    ("I/O write", format_throughput(item.io_write_bytes_per_second)),
                    ("Architecture", _text(item.architecture)),
                    ("Publisher", _text(item.publisher)),
                    ("Digitally signed", _text(item.digitally_signed)),
                ],
            )
    return lines + _footer(data)


def _services(data: ServicesInspection) -> list[str]:
    lines = ["Services", "Current state"]
    for service in data.services:
        identity = service.identity
        state = service.current_state
        lines.append(
            "  "
            f"{_text(identity.display_name)} ({identity.name}) | "
            f"{_text(state.state)} | startup {_text(service.configuration.startup_type)} | "
            f"status {_text(service.health_status)}"
        )
        if service.details:
            item = service.details
            lines += _section(
                f"{identity.name} - Details",
                [
                    ("Binary path", _text(item.binary_path)),
                    ("Service account", _text(item.service_account)),
                    ("Description", _text(item.description)),
                    ("PID", _text(item.pid)),
                    ("Dependencies", ", ".join(item.dependencies) or UNAVAILABLE),
                    (
                        "Dependent services",
                        ", ".join(item.dependent_services) or UNAVAILABLE,
                    ),
                    ("Delayed auto start", _text(item.delayed_auto_start)),
                    ("Service type", _text(item.service_type)),
                    ("Exit code", _text(item.exit_code)),
                    ("Service-specific exit code", _text(item.service_specific_exit_code)),
                ],
            )
    return lines + _footer(data)


def _startup(data: StartupInspection) -> list[str]:
    lines = ["Startup items", "Configuration"]
    for item in data.items:
        lines.append(
            "  "
            f"{_text(item.identity.name)} | app {_text(item.identity.application)} | "
            f"enabled {_text(item.configuration.enabled)} | "
            f"source {_text(item.configuration.source_type)} | "
            f"scope {_text(item.configuration.scope)} | "
            f"publisher {_text(item.identity.publisher)}"
        )
        if item.details:
            detail = item.details
            lines += _section(
                f"{_text(item.identity.name)} - Details",
                [
                    ("Command/path", _text(detail.command)),
                    ("Source location", _text(detail.source_location)),
                    ("Arguments", _text(detail.arguments)),
                    ("Digitally signed", _text(detail.digitally_signed)),
                    ("Associated package", _text(detail.associated_package)),
                    ("User", _text(detail.user)),
                    ("User SID", _text(detail.user_sid)),
                    ("Startup impact", _text(detail.startup_impact)),
                ],
            )
    return lines + _footer(data)


def _drivers(data: DriversInspection) -> list[str]:
    display_limit = 50
    shown = data.drivers[:display_limit]
    lines = ["Drivers", "Summary", f"  Detected: {len(data.drivers)}", f"  Shown: {len(shown)}"]
    lines.append("Inventory")
    for driver in shown:
        lines.append(
            "  "
            f"{_text(driver.identity.device_name)} | "
            f"class {_text(driver.identity.device_class)} | "
            f"provider {_text(driver.configuration.provider)} | "
            f"version {_text(driver.configuration.version)} | "
            f"date {format_date(driver.configuration.date)} | "
            f"status {_text(driver.health_status)} | "
            f"signed {_text(driver.configuration.signed)}"
        )
        if driver.details:
            item = driver.details
            lines += _section(
                f"{_text(driver.identity.device_name)} - Details",
                [
                    ("INF/package", _text(item.inf_name)),
                    ("Hardware IDs", ", ".join(item.hardware_ids) or UNAVAILABLE),
                    ("Compatible IDs", ", ".join(item.compatible_ids) or UNAVAILABLE),
                    ("Device instance ID", _text(item.device_instance_id)),
                    ("Service", _text(item.service_name)),
                    ("Driver files", ", ".join(item.driver_files) or UNAVAILABLE),
                    ("Signer", _text(item.signer)),
                    ("Manufacturer", _text(item.manufacturer)),
                    ("Problem code", _text(item.problem_code)),
                    ("Location", _text(item.location)),
                ],
            )
    if len(data.drivers) > len(shown):
        lines.append("Display note")
        lines.append("  Human output is limited to 50 drivers; --json includes all records.")
    return lines + _footer(data)


def _software(data: SoftwareInspection) -> list[str]:
    display_limit = 100
    shown = data.applications[:display_limit]
    lines = [
        "Installed software",
        "Summary",
        f"  Detected: {len(data.applications)}",
        f"  Shown: {len(shown)}",
        "Inventory",
    ]
    for application in shown:
        lines.append(
            "  "
            f"{application.identity.name} | "
            f"version {_text(application.configuration.version)} | "
            f"publisher {_text(application.identity.publisher)} | "
            f"scope {_text(application.configuration.installation_scope)} | "
            f"installed {format_date(application.configuration.install_date)}"
        )
        if application.details:
            item = application.details
            lines += _section(
                f"{application.identity.name} - Details",
                [
                    ("Install location", _text(item.install_location)),
                    ("Registry source", _text(item.registry_source)),
                    ("Uninstall identifier", _text(item.uninstall_identifier)),
                    ("Product identifier", _text(item.product_identifier)),
                    ("Architecture", _text(item.architecture)),
                    ("Install source", _text(item.install_source)),
                    ("Install channel", _text(item.install_channel)),
                ],
            )
    if len(data.applications) > len(shown):
        lines.append("Display note")
        lines.append("  Human output is limited to 100 applications; --json includes all records.")
    return lines + _footer(data)


def _events(data: EventsInspection) -> list[str]:
    lines = ["Events", "Filter", f"  {data.filter_description}", "Recent events"]
    if not data.events:
        lines.append("  No matching events found.")
    for event in data.events:
        lines.append(
            "  "
            f"{format_timestamp(event.timestamp)} | {_text(event.level)} | "
            f"{_text(event.provider)} | ID {_text(event.event_id)} | "
            f"{_text(event.channel)} | {_text(event.summary)}"
        )
        if event.details:
            item = event.details
            lines += _section(
                f"Event {_text(event.event_id)} - Details",
                [
                    ("Full message", _text(item.full_message)),
                    ("Record ID", _text(item.record_id)),
                    ("Task", _text(item.task)),
                    ("Opcode", _text(item.opcode)),
                    ("Process ID", _text(item.process_id)),
                    ("Thread ID", _text(item.thread_id)),
                    ("Activity ID", _text(item.activity_id)),
                    ("Event data", _text(item.event_data or None)),
                ],
            )
    return lines + _footer(data)


def _crashes(data: CrashesInspection) -> list[str]:
    lines = ["Crashes", "Recent crash groups"]
    if not data.crashes:
        lines.append("  No matching application crash events found in the last 30 days.")
    for index, crash in enumerate(data.crashes, start=1):
        lines += _section(
            f"Crash group {index}",
            [
                ("Latest timestamp", format_timestamp(crash.timestamp)),
                ("Application/process", _text(crash.affected_application)),
                ("Type", _text(crash.crash_type)),
                ("Faulting module", _text(crash.faulting_module)),
                ("Exception/error code", _text(crash.exception_code)),
                ("Recurrence count", _text(crash.recurrence_count)),
            ],
        )
        if crash.details:
            item = crash.details
            lines += _section(
                f"Crash group {index} - Details",
                [
                    ("Module version", _text(item.faulting_module_version)),
                    ("Module path", _text(item.faulting_module_path)),
                    ("Exception offset", _text(item.exception_offset)),
                    ("Report ID", _text(item.report_id)),
                    ("Bucket ID", _text(item.bucket_id)),
                    ("Event ID", _text(item.event_id)),
                    ("Record ID", _text(item.record_id)),
                    ("Application version", _text(item.application_version)),
                    ("Event data", _text(item.event_data or None)),
                ],
            )
    return lines + _footer(data)


def _boot(data: BootInspection) -> list[str]:
    duration = (
        UNAVAILABLE
        if data.latest_boot_duration_ms is None
        else f"{data.latest_boot_duration_ms / 1000:.2f} s"
    )
    lines = ["Boot"]
    lines += _section(
        "Current state",
        [
            ("Uptime", format_duration(data.current_uptime_seconds)),
            ("Previous shutdown", _text(data.previous_shutdown)),
            ("Latest measured boot duration", duration),
        ],
    )
    lines += _section(
        "Recent boot timestamps",
        [
            (str(index), format_timestamp(timestamp))
            for index, timestamp in enumerate(data.recent_boot_times, start=1)
        ]
        or [("Boots", "unavailable")],
    )
    lines.append("Startup warnings")
    if not data.startup_warnings:
        lines.append("  No matching boot-performance warnings found.")
    for event in data.startup_warnings:
        lines.append(
            "  "
            f"{format_timestamp(event.timestamp)} | ID {_text(event.event_id)} | "
            f"{_text(event.summary)}"
        )
    if data.evidence is not None:
        for index, evidence in enumerate(data.evidence, start=1):
            lines += _section(
                f"Evidence {index}",
                [
                    ("Timestamp", format_timestamp(evidence.timestamp)),
                    ("Event ID", _text(evidence.event_id)),
                    ("Channel", _text(evidence.channel)),
                    ("Record ID", _text(evidence.record_id)),
                    ("Summary", _text(evidence.summary)),
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
    elif isinstance(result.data, MemoryInspection):
        lines = _ram(result.data)
    elif isinstance(result.data, GpuInspection):
        lines = _gpu(result.data)
    elif isinstance(result.data, StorageInspection):
        lines = _storage(result.data)
    elif isinstance(result.data, NetworkInspection):
        lines = _network(result.data)
    elif isinstance(result.data, ProcessesInspection):
        lines = _processes(result.data)
    elif isinstance(result.data, ServicesInspection):
        lines = _services(result.data)
    elif isinstance(result.data, StartupInspection):
        lines = _startup(result.data)
    elif isinstance(result.data, DriversInspection):
        lines = _drivers(result.data)
    elif isinstance(result.data, SoftwareInspection):
        lines = _software(result.data)
    elif isinstance(result.data, EventsInspection):
        lines = _events(result.data)
    elif isinstance(result.data, CrashesInspection):
        lines = _crashes(result.data)
    else:
        lines = _boot(result.data)
    rendered = "\n".join(lines)
    encoding = sys.stdout.encoding or "utf-8"
    return rendered.encode(encoding, errors="replace").decode(encoding, errors="replace")
