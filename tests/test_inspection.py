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
                    "CurrentHorizontalResolution": 2560,
                    "CurrentVerticalResolution": 1440,
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
