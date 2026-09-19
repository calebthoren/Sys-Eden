import asyncio
import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from pydantic import JsonValue, ValidationError
from typer.testing import CliRunner

from sys_eden.cli import app
from sys_eden.inspection import CimQuery, InspectionError, InspectionResult, collect
from sys_eden.inspection_format import (
    UNAVAILABLE,
    format_bytes,
    format_memory_speed,
    render_human,
)
from sys_eden.inspection_models import (
    CpuConfiguration,
    CpuIdentity,
    CpuInspection,
    CpuState,
    SystemIdentity,
    SystemInspection,
    SystemState,
    WindowsConfiguration,
)
from sys_eden.windows import WindowsCimReader
from sys_eden.windows_collectors import WindowsInspectionProvider


class FixtureReader:
    def __init__(self) -> None:
        self.requests: list[CimQuery] = []
        self.rows: dict[str, list[dict[str, JsonValue]]] = {
            "Win32_ComputerSystem": [
                {
                    "Name": "EDEN-PC",
                    "Manufacturer": "Fixture Systems",
                    "Model": "Model One",
                    "TotalPhysicalMemory": 34359738368,
                    "HypervisorPresent": False,
                    "NumberOfLogicalProcessors": 4,
                }
            ],
            "Win32_OperatingSystem": [
                {
                    "Caption": "Microsoft Windows 11 Test",
                    "Version": "10.0.26100",
                    "BuildNumber": "26100",
                    "OSArchitecture": "64-bit",
                    "LastBootUpTime": "/Date(1767225600000)/",
                    "SystemDrive": "C:",
                    "Status": "OK",
                    "InstallDate": "/Date(1735689600000)/",
                    "OperatingSystemSKU": 101,
                    "ProductType": 1,
                    "TotalVisibleMemorySize": 33000000,
                    "FreePhysicalMemory": 12000000,
                }
            ],
            "Win32_Processor": [
                {
                    "Name": "Fixture CPU",
                    "Manufacturer": "Fixture Silicon",
                    "NumberOfCores": 8,
                    "NumberOfLogicalProcessors": 16,
                    "Architecture": 9,
                    "LoadPercentage": 25,
                    "MaxClockSpeed": 5000,
                    "CurrentClockSpeed": 4200,
                    "Status": "OK",
                    "SocketDesignation": "AM5",
                    "ProcessorId": "ABC123",
                    "Family": 107,
                    "Revision": 1,
                    "Stepping": "2",
                    "Level": 25,
                    "L2CacheSize": 8192,
                    "L3CacheSize": 32768,
                    "VirtualizationFirmwareEnabled": True,
                    "SecondLevelAddressTranslationExtensions": True,
                    "DeviceID": "CPU0",
                }
            ],
            "Win32_VideoController": [
                {
                    "Name": "Fixture GPU",
                    "AdapterCompatibility": "Fixture Graphics",
                    "DriverVersion": "1.2.3",
                    "DriverDate": "/Date(1735689600000)/",
                    "CurrentHorizontalResolution": 2560,
                    "CurrentVerticalResolution": 1440,
                    "CurrentRefreshRate": 144,
                    "Status": "OK",
                    "ConfigManagerErrorCode": 0,
                    "PNPDeviceID": "PCI\\VEN_FIXTURE",
                    "DeviceID": "VideoController1",
                    "VideoProcessor": "Fixture Processor",
                }
            ],
            "Win32_PnPSignedDriver": [
                {
                    "DeviceID": "PCI\\VEN_FIXTURE",
                    "DriverProviderName": "Fixture Driver Provider",
                    "DriverVersion": "1.2.3",
                    "DriverDate": "/Date(1735689600000)/",
                    "InfName": "fixture.inf",
                    "IsSigned": True,
                },
                {
                    "DeviceID": "PCI\\VEN_NETWORK",
                    "DriverProviderName": "Fixture Network Provider",
                    "DriverVersion": "4.5.6",
                },
            ],
            "Win32_NetworkAdapter": [
                {
                    "Index": 7,
                    "InterfaceIndex": 12,
                    "GUID": "{fixture-guid}",
                    "NetConnectionID": "Ethernet",
                    "Name": "Fixture Ethernet",
                    "Description": "Fixture 2.5GbE Adapter",
                    "NetEnabled": True,
                    "NetConnectionStatus": 2,
                    "Speed": 2500000000,
                    "AdapterTypeID": 0,
                    "PhysicalAdapter": True,
                    "MACAddress": "00:11:22:33:44:55",
                    "PNPDeviceID": "PCI\\VEN_NETWORK",
                    "Status": "OK",
                }
            ],
            "Win32_NetworkAdapterConfiguration": [
                {
                    "Index": 7,
                    "IPEnabled": True,
                    "IPAddress": ["192.0.2.10", "2001:db8::10"],
                    "DefaultIPGateway": ["192.0.2.1"],
                    "DNSServerSearchOrder": ["192.0.2.53", "2001:db8::53"],
                    "DHCPEnabled": True,
                    "DHCPServer": "192.0.2.1",
                    "DHCPLeaseObtained": "/Date(1767225600000)/",
                    "DHCPLeaseExpires": "/Date(1767312000000)/",
                    "IPSubnet": ["255.255.255.0", "64"],
                    "DNSDomain": "example.test",
                    "DNSDomainSuffixSearchOrder": ["example.test"],
                    "MTU": 1500,
                }
            ],
            "Win32_IP4RouteTable": [
                {
                    "InterfaceIndex": 12,
                    "Destination": "0.0.0.0",
                    "Mask": "0.0.0.0",
                    "NextHop": "192.0.2.1",
                    "Metric1": 25,
                }
            ],
            "Win32_Process": [
                {
                    "ProcessId": 10,
                    "Name": "busy.exe",
                    "ExecutionState": None,
                    "ExecutablePath": "C:\\Apps\\busy.exe",
                    "CommandLine": '"C:\\Apps\\busy.exe" --work',
                    "ParentProcessId": 4,
                    "CreationDate": "/Date(1767225600000)/",
                    "ThreadCount": 8,
                    "HandleCount": 100,
                },
                {
                    "ProcessId": 20,
                    "Name": "memory.exe",
                    "ExecutionState": None,
                    "ExecutablePath": None,
                    "CommandLine": None,
                    "ParentProcessId": 4,
                    "CreationDate": None,
                    "ThreadCount": 4,
                    "HandleCount": 50,
                },
            ],
            "Win32_PerfFormattedData_PerfProc_Process": [
                {
                    "IDProcess": 10,
                    "Name": "busy",
                    "PercentProcessorTime": 200,
                    "WorkingSetPrivate": 1000,
                    "IOReadBytesPerSec": 20,
                    "IOWriteBytesPerSec": 30,
                    "ThreadCount": 8,
                    "HandleCount": 100,
                },
                {
                    "IDProcess": 20,
                    "Name": "memory",
                    "PercentProcessorTime": 40,
                    "WorkingSetPrivate": 2000,
                    "IOReadBytesPerSec": 0,
                    "IOWriteBytesPerSec": 0,
                    "ThreadCount": 4,
                    "HandleCount": 50,
                },
                {
                    "IDProcess": 0,
                    "Name": "_Total",
                    "PercentProcessorTime": 400,
                    "WorkingSetPrivate": 999999,
                    "IOReadBytesPerSec": 0,
                    "IOWriteBytesPerSec": 0,
                    "ThreadCount": 1,
                    "HandleCount": 1,
                },
            ],
            "Win32_Service": [
                {
                    "Name": "FixtureService",
                    "DisplayName": "Fixture Service",
                    "State": "Running",
                    "StartMode": "Auto",
                    "Status": "OK",
                    "Started": True,
                    "PathName": '"C:\\Apps\\service.exe"',
                    "StartName": "LocalSystem",
                    "Description": "Fixture service",
                    "ProcessId": 123,
                    "DelayedAutoStart": False,
                    "ServiceType": "Own Process",
                    "ExitCode": 0,
                    "ServiceSpecificExitCode": 0,
                }
            ],
            "Win32_LogicalDisk": [
                {
                    "DeviceID": "C:",
                    "FileSystem": "NTFS",
                    "Size": 1000,
                    "FreeSpace": 250,
                    "DriveType": 3,
                }
            ],
            "Win32_BaseBoard": [{"Manufacturer": "Board Inc", "Product": "Board X"}],
            "Win32_BIOS": [
                {
                    "Manufacturer": "Firmware Inc",
                    "SMBIOSBIOSVersion": "1.2.3",
                    "ReleaseDate": "/Date(1704067200000)/",
                }
            ],
            "Win32_Tpm": [{"SpecVersion": "2.0"}],
            "Win32_PerfFormattedData_PerfOS_Processor": [
                {"Name": "0", "PercentProcessorTime": 10},
                {"Name": "1", "PercentProcessorTime": 20},
                {"Name": "_Total", "PercentProcessorTime": 15},
            ],
            "Win32_PhysicalMemory": [
                {
                    "Capacity": 17179869184,
                    "Speed": 6000,
                    "ConfiguredClockSpeed": 5600,
                    "Manufacturer": "Memory Inc",
                    "Model": None,
                    "PartNumber": "PART-A",
                    "SMBIOSMemoryType": 34,
                    "Status": "OK",
                    "DeviceLocator": "DIMM_A2",
                    "BankLabel": "Channel A",
                    "FormFactor": 8,
                    "ConfiguredVoltage": 1250,
                    "SerialNumber": "SERIAL-A",
                },
                {
                    "Capacity": 17179869184,
                    "Speed": 6000,
                    "ConfiguredClockSpeed": 5600,
                    "Manufacturer": "Memory Inc",
                    "Model": None,
                    "PartNumber": "PART-B",
                    "SMBIOSMemoryType": 34,
                    "Status": "OK",
                    "DeviceLocator": "DIMM_B2",
                    "BankLabel": "Channel B",
                    "FormFactor": 8,
                    "ConfiguredVoltage": 1250,
                    "SerialNumber": "SERIAL-B",
                },
            ],
            "MSFT_PhysicalDisk": [
                {
                    "DeviceId": "0",
                    "FriendlyName": "Fixture NVMe",
                    "MediaType": 4,
                    "BusType": 17,
                    "Size": 1000,
                    "HealthStatus": 0,
                    "OperationalStatus": [2],
                    "SerialNumber": "DISK-SERIAL",
                    "FirmwareVersion": "FW1",
                }
            ],
            "MSFT_Disk": [
                {
                    "Number": 0,
                    "FriendlyName": "Fixture NVMe",
                    "PartitionStyle": 2,
                    "UniqueId": "fixture-id",
                    "SerialNumber": "DISK-SERIAL",
                }
            ],
            "MSFT_Volume": [
                {
                    "DriveLetter": "C",
                    "FileSystemLabel": "System",
                    "FileSystem": "NTFS",
                    "Size": 1000,
                    "SizeRemaining": 50,
                    "HealthStatus": 0,
                    "OperationalStatus": [2],
                    "Path": "\\\\?\\Volume{fixture}\\",
                }
            ],
        }

    async def query(self, request: CimQuery) -> list[dict[str, JsonValue]]:
        self.requests.append(request)
        rows = self.rows.get(request.class_name, [])
        return [{key: row.get(key) for key in request.properties} for row in rows]


def test_generic_query_rejects_mutating_provider_and_script_properties():
    with pytest.raises(ValidationError):
        CimQuery.model_validate({"class_name": "Win32_Product", "properties": ["Name"]})
    with pytest.raises(ValidationError):
        CimQuery(class_name="Win32_Processor", properties=["Name; exit"])


@pytest.mark.asyncio
async def test_system_default_and_details_are_typed_and_curated():
    reader = FixtureReader()
    provider = WindowsInspectionProvider(reader)
    basic = await provider.system(details=False)
    assert basic.identity.device_name == "EDEN-PC"
    assert basic.configuration.build == "26100"
    assert basic.current_state.primary_gpu == "Fixture GPU"
    assert basic.current_state.installed_ram_bytes == 34359738368
    assert basic.current_state.system_drive is not None
    assert basic.current_state.system_drive.free_percent == 25
    assert basic.details is None
    assert not any(request.class_name == "Win32_BIOS" for request in reader.requests)

    detailed = await provider.system(details=True)
    assert detailed.details is not None
    assert detailed.details.motherboard_model == "Board X"
    assert detailed.details.firmware_version == "1.2.3"
    assert detailed.details.tpm_present
    assert detailed.details.tpm_version == "2.0"
    assert detailed.details.firmware_mode is None
    assert detailed.details.secure_boot_enabled is None


@pytest.mark.asyncio
async def test_cpu_reports_reliable_values_and_marks_unsupported_values_missing():
    result = await WindowsInspectionProvider(FixtureReader()).cpu(details=True)
    assert result.identity.architecture == "x64"
    assert result.configuration.physical_cores == 8
    assert result.configuration.base_clock_mhz is None
    assert result.current_state.total_utilization_percent == 25
    assert result.details is not None
    assert result.details.l3_cache_bytes == 32768 * 1024
    assert result.details.per_core_utilization_percent == {"0": 10, "1": 20}
    assert result.details.temperature_celsius is None


@pytest.mark.asyncio
async def test_ram_default_omits_serial_and_details_decode_inventory():
    reader = FixtureReader()
    provider = WindowsInspectionProvider(reader)
    basic = await provider.ram(details=False)
    module_request = next(
        request for request in reader.requests if request.class_name == "Win32_PhysicalMemory"
    )
    assert "SerialNumber" not in module_request.properties
    assert basic.identity.total_installed_bytes == 34359738368
    assert basic.identity.module_count == 2
    assert basic.current_state.used_bytes == (33000000 - 12000000) * 1024
    assert basic.details is None
    assert [item.code for item in basic.observations] == ["mixed_part_numbers"]

    detailed = await provider.ram(details=True)
    assert detailed.details is not None
    assert detailed.details.modules[0].memory_type == "DDR5"
    assert detailed.details.modules[0].form_factor == "DIMM"
    assert detailed.details.modules[0].configured_voltage_volts == 1.25
    assert detailed.details.modules[0].serial_number == "SERIAL-A"


@pytest.mark.asyncio
async def test_gpu_keeps_unreliable_telemetry_unavailable_and_adds_driver_details():
    provider = WindowsInspectionProvider(FixtureReader())
    basic = await provider.gpu(details=False)
    assert len(basic.adapters) == 1
    adapter = basic.adapters[0]
    assert adapter.identity.name == "Fixture GPU"
    assert adapter.identity.adapter_type == "hardware"
    assert adapter.configuration.dedicated_vram_bytes is None
    assert adapter.current_state.utilization_percent is None
    assert adapter.current_state.primary
    assert adapter.details is None

    detailed = await provider.gpu(details=True)
    assert detailed.adapters[0].details is not None
    assert detailed.adapters[0].details.driver_provider == "Fixture Driver Provider"
    assert detailed.adapters[0].details.driver_inf == "fixture.inf"
    assert detailed.adapters[0].details.display_resolution == "2560x1440"


@pytest.mark.asyncio
async def test_storage_reports_disks_volumes_details_and_low_space_observation():
    provider = WindowsInspectionProvider(FixtureReader())
    basic = await provider.storage(details=False)
    assert basic.physical_disks[0].configuration.media_type == "SSD"
    assert basic.physical_disks[0].configuration.bus_type == "NVMe"
    assert basic.physical_disks[0].details is None
    assert basic.volumes[0].identity.drive_letter == "C:"
    assert basic.volumes[0].current_state.used_bytes == 950
    assert basic.observations[0].code == "low_volume_free_space"

    detailed = await provider.storage(details=True)
    assert detailed.physical_disks[0].details is not None
    assert detailed.physical_disks[0].details.partition_style == "GPT"
    assert detailed.physical_disks[0].details.serial_number == "DISK-SERIAL"
    assert detailed.volumes[0].details is not None
    assert detailed.volumes[0].details.encryption_status is None


@pytest.mark.asyncio
async def test_network_default_and_details_are_scoped_and_structured():
    reader = FixtureReader()
    provider = WindowsInspectionProvider(reader)
    basic = await provider.network(details=False)
    assert len(basic.adapters) == 1
    adapter = basic.adapters[0]
    assert adapter.identity.classification == "Ethernet"
    assert adapter.current_state.connected
    assert adapter.current_state.link_speed_bps == 2500000000
    assert adapter.current_state.ipv4_addresses == ["192.0.2.10"]
    assert adapter.current_state.ipv6_addresses == ["2001:db8::10"]
    assert adapter.details is None
    adapter_request = next(
        request for request in reader.requests if request.class_name == "Win32_NetworkAdapter"
    )
    assert "MACAddress" not in adapter_request.properties

    detailed = await provider.network(details=True)
    item = detailed.adapters[0].details
    assert item is not None
    assert item.mac_address == "00:11:22:33:44:55"
    assert item.driver_provider == "Fixture Network Provider"
    assert item.mtu_bytes == 1500
    assert item.routes[0].next_hop == "192.0.2.1"
    assert detailed.adapters[0].current_state.wifi_ssid is None


@pytest.mark.asyncio
async def test_network_classifies_bluetooth_and_omits_zero_link_speed():
    reader = FixtureReader()
    reader.rows["Win32_NetworkAdapter"][0].update(
        {
            "Name": "Bluetooth Device (Personal Area Network)",
            "Description": "Bluetooth Device",
            "NetConnectionID": "Bluetooth Network Connection",
            "Speed": 0,
        }
    )
    result = await WindowsInspectionProvider(reader).network(details=False)
    assert result.adapters[0].identity.classification == "other"
    assert result.adapters[0].current_state.link_speed_bps is None


@pytest.mark.asyncio
async def test_processes_are_ranked_and_details_tolerate_protected_fields():
    reader = FixtureReader()
    provider = WindowsInspectionProvider(reader)
    basic = await provider.processes(details=False)
    assert basic.total_detected == 2
    assert basic.processes[0].identity.pid == 10
    assert basic.processes[0].current_state.cpu_percent == 50
    assert basic.processes[0].current_state.user is None
    assert basic.processes[0].details is None
    process_request = next(
        request for request in reader.requests if request.class_name == "Win32_Process"
    )
    assert "CommandLine" not in process_request.properties

    detailed = await provider.processes(details=True)
    assert detailed.processes[0].details is not None
    assert detailed.processes[0].details.executable_path == "C:\\Apps\\busy.exe"
    protected = next(item for item in detailed.processes if item.identity.pid == 20)
    assert protected.details is not None
    assert protected.details.executable_path is None


@pytest.mark.asyncio
async def test_services_default_and_details_are_curated():
    reader = FixtureReader()
    provider = WindowsInspectionProvider(reader)
    basic = await provider.services(details=False)
    assert basic.services[0].identity.name == "FixtureService"
    assert basic.services[0].configuration.startup_type == "Auto"
    assert basic.services[0].current_state.state == "Running"
    assert basic.services[0].details is None

    detailed = await provider.services(details=True)
    assert detailed.services[0].details is not None
    assert detailed.services[0].details.service_account == "LocalSystem"
    assert detailed.services[0].details.pid == 123


@pytest.mark.asyncio
async def test_partial_source_failure_is_reported_without_losing_other_evidence():
    class PartialReader(FixtureReader):
        async def query(self, request: CimQuery) -> list[dict[str, JsonValue]]:
            if request.class_name == "Win32_PhysicalMemory":
                raise InspectionError("PermissionDenied")
            return await super().query(request)

    result = await WindowsInspectionProvider(PartialReader()).ram(details=False)
    assert result.identity.total_installed_bytes == 34359738368
    assert result.identity.module_count is None
    assert result.warnings[0].code == "PermissionDenied"


@pytest.mark.asyncio
async def test_collect_wraps_provider_failure():
    class Provider:
        async def system(self, *, details: bool):
            raise InspectionError("PermissionDenied")

        async def cpu(self, *, details: bool):
            raise InspectionError("PermissionDenied")

        async def ram(self, *, details: bool):
            raise InspectionError("PermissionDenied")

        async def gpu(self, *, details: bool):
            raise InspectionError("PermissionDenied")

        async def storage(self, *, details: bool):
            raise InspectionError("PermissionDenied")

        async def network(self, *, details: bool):
            raise InspectionError("PermissionDenied")

        async def processes(self, *, details: bool):
            raise InspectionError("PermissionDenied")

        async def services(self, *, details: bool):
            raise InspectionError("PermissionDenied")

    result = await collect("cpu", Provider(), details=False)
    assert not result.success
    assert result.error == "PermissionDenied"
    assert result.data is None


def test_human_formatter_uses_consistent_units_and_unavailable_values():
    result = CpuInspection(
        identity=CpuIdentity(model="Fixture", architecture="x64"),
        configuration=CpuConfiguration(physical_cores=4, logical_processors=8),
        current_state=CpuState(total_utilization_percent=12.345),
    )
    now = datetime.now(UTC)
    envelope = InspectionResult(
        capability="cpu",
        started_at=now,
        finished_at=now,
        success=True,
        data=result,
    )
    rendered = render_human(envelope)
    assert "Total utilization: 12.3%" in rendered
    assert f"Base clock: {UNAVAILABLE}" in rendered
    assert format_bytes(1536) == "1.5 KiB"
    assert format_memory_speed(4800) == "4,800 MHz"


def test_placeholder_memory_serial_is_not_presented_as_identity():
    row: dict[str, JsonValue] = {
        "SerialNumber": "00000000",
        "SMBIOSMemoryType": 34,
        "FormFactor": 8,
    }
    module = WindowsInspectionProvider._memory_module(row)
    assert module.serial_number is None


def test_cli_defaults_to_human_and_supports_details_json(monkeypatch: pytest.MonkeyPatch):
    inspection = SystemInspection(
        identity=SystemIdentity(device_name="EDEN-PC"),
        configuration=WindowsConfiguration(edition="Windows Test"),
        current_state=SystemState(last_boot_time=datetime(2026, 1, 1, tzinfo=UTC)),
    )
    mocked = AsyncMock(return_value=inspection)
    monkeypatch.setattr(WindowsInspectionProvider, "system", mocked)
    runner = CliRunner()
    human = runner.invoke(app, ["inspect", "system"])
    assert human.exit_code == 0, human.output
    assert "Identity" in human.stdout
    assert "Device name: EDEN-PC" in human.stdout

    structured = runner.invoke(app, ["inspect", "system", "--details", "--json"])
    assert structured.exit_code == 0, structured.output
    payload = json.loads(structured.stdout)
    assert payload[0]["data"]["identity"]["device_name"] == "EDEN-PC"
    assert payload[0]["data"]["identity"]["manufacturer"] is None
    assert mocked.await_args_list[-1].kwargs == {"details": True}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "output,code,expected",
    [
        (b'[{"Name":"Fixture"}]', 0, None),
        (b"private error text", 1, "ExecutionFailed"),
        (b"not json", 0, "InvalidToolOutput"),
    ],
)
async def test_windows_adapter_output(
    monkeypatch: pytest.MonkeyPatch,
    output: bytes,
    code: int,
    expected: str | None,
):
    class Process:
        returncode = code

        async def communicate(self, data: bytes):
            payload = json.loads(data)
            assert payload["class_name"] == "Win32_Processor"
            assert payload["namespace"] == "root/cimv2"
            return output, None

    monkeypatch.setattr("sys_eden.windows.sys.platform", "win32")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(return_value=Process()))
    query = CimQuery(class_name="Win32_Processor", properties=["Name"])
    if expected is None:
        assert await WindowsCimReader().query(query) == [{"Name": "Fixture"}]
    else:
        with pytest.raises(InspectionError, match=expected):
            await WindowsCimReader().query(query)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [TimeoutError, asyncio.CancelledError])
async def test_windows_adapter_reaps_process_on_interruption(
    monkeypatch: pytest.MonkeyPatch,
    failure: type[BaseException],
):
    class Process:
        returncode = None
        killed = False
        reaped = False

        async def communicate(self, data: bytes):
            raise failure()

        def kill(self):
            self.killed = True

        async def wait(self):
            self.reaped = True

    process = Process()
    monkeypatch.setattr("sys_eden.windows.sys.platform", "win32")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(return_value=process))
    query = CimQuery(class_name="Win32_Processor", properties=["Name"])
    expected = asyncio.CancelledError if failure is asyncio.CancelledError else InspectionError
    with pytest.raises(expected):
        await WindowsCimReader().query(query)
    assert process.killed
    assert process.reaped
