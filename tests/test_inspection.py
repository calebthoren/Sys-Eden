import asyncio
import json
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock

import pytest
from pydantic import JsonValue, ValidationError
from typer.testing import CliRunner

from sys_eden.cli import app
from sys_eden.inspection import (
    CimQuery,
    EventQuery,
    InspectionError,
    InspectionResult,
    collect,
)
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
    EventDetails,
    EventRecord,
    EventsInspection,
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
            "Win32_StartupCommand": [
                {
                    "Name": "Fixture Startup",
                    "Caption": "Fixture Startup App",
                    "Location": "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run",
                    "User": "fixture-user",
                    "Command": '"C:\\Apps\\startup.exe" --quiet',
                    "Description": "Fixture startup entry",
                    "UserSID": "S-1-5-21-fixture",
                }
            ],
            "Win32_PnPEntity": [
                {
                    "DeviceID": "PCI\\VEN_FIXTURE",
                    "Name": "Fixture GPU",
                    "PNPClass": "Display",
                    "Status": "OK",
                    "ConfigManagerErrorCode": 0,
                    "HardwareID": ["PCI\\VEN_FIXTURE&DEV_0001"],
                    "CompatibleID": ["PCI\\CC_0300"],
                    "Service": "fixture-display",
                    "LocationInformation": "PCI bus 1",
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

    async def installed_software(self) -> list[dict[str, JsonValue]]:
        return [
            {
                "DisplayName": "Fixture App",
                "DisplayVersion": "1.2.3",
                "Publisher": "Fixture Publisher",
                "InstallDate": "20260102",
                "InstallLocation": "C:\\Apps\\Fixture",
                "InstallSource": "C:\\Installers",
                "RegistrySource": "HKLM:\\...\\Fixture",
                "UninstallIdentifier": "Fixture",
                "ProductIdentifier": "{fixture-product}",
                "Scope": "machine",
                "Architecture": "x64",
                "InstallChannel": "MSI",
            }
        ]

    async def graphics_adapters(self) -> list[dict[str, JsonValue]]:
        return [
            {
                "Name": "Fixture GPU",
                "VendorId": 0x1234,
                "DeviceId": 0x5678,
                "DedicatedVideoMemory": 12 * 1024**3,
                "SharedSystemMemory": 16 * 1024**3,
                "AdapterLuid": "0000000000000001",
                "CapacitySource": "DXGI",
            }
        ]

    async def service_dependencies(self) -> list[dict[str, JsonValue]]:
        return [
            {
                "Antecedent": "RpcSs",
                "Dependent": "FixtureService",
                "TypeOfDependency": 3,
            },
            {
                "Antecedent": "FixtureService",
                "Dependent": "DependentFixture",
                "TypeOfDependency": 3,
            },
        ]

    async def storage_reliability(self) -> list[dict[str, JsonValue]]:
        return [
            {
                "DeviceId": 0,
                "FriendlyName": "Fixture NVMe",
                "Temperature": 39,
                "ReadErrorsTotal": 2,
                "WriteErrorsTotal": 1,
                "Wear": 4,
                "PowerOnHours": 1200,
            }
        ]

    async def volume_encryption(self) -> list[dict[str, JsonValue]]:
        return [
            {
                "DriveLetter": "C:",
                "VolumeStatus": "FullyEncrypted",
                "ProtectionStatus": "On",
                "EncryptionMethod": "XTS-AES 256",
            }
        ]

    async def trim_configuration(self) -> list[dict[str, JsonValue]]:
        return [
            {
                "FileSystem": "NTFS",
                "DeleteNotificationsEnabled": True,
            }
        ]

    async def network_statistics(self) -> list[dict[str, JsonValue]]:
        return [
            {
                "Name": "Ethernet",
                "InterfaceDescription": "Fixture 2.5GbE Adapter",
                "ReceiveBytesPerSecond": 4096,
                "SendBytesPerSecond": 1024,
                "SampleSeconds": 0.5,
                "ReceivedPacketErrors": 2,
                "OutboundPacketErrors": 1,
                "ReceivedDiscardedPackets": 4,
                "OutboundDiscardedPackets": 3,
            }
        ]

    async def wifi_quality(self) -> list[dict[str, JsonValue]]:
        return [
            {
                "InterfaceGuid": "{fixture-guid}",
                "InterfaceDescription": "Fixture 2.5GbE Adapter",
                "SignalQuality": 82,
                "ReceiveRateKbps": 866000,
                "TransmitRateKbps": 780000,
            }
        ]

    async def query_events(self, request: EventQuery) -> list[dict[str, JsonValue]]:
        if request.log_names == ["Application"]:
            return [
                {
                    "Timestamp": "2026-01-03T12:00:00Z",
                    "Level": "Error",
                    "Provider": "Application Error",
                    "EventId": 1000,
                    "Channel": "Application",
                    "Message": "Fixture application crashed.",
                    "RecordId": 100,
                    "EventData": {
                        "AppName": "fixture.exe",
                        "AppVersion": "1.2.3",
                        "ModuleName": "fixture.dll",
                        "ModuleVersion": "4.5.6",
                        "ExceptionCode": "0xc0000005",
                        "ExceptionOffset": "0x10",
                    },
                },
                {
                    "Timestamp": "2026-01-02T12:00:00Z",
                    "Level": "Error",
                    "Provider": "Application Error",
                    "EventId": 1000,
                    "Channel": "Application",
                    "Message": "Fixture application crashed again.",
                    "RecordId": 90,
                    "EventData": {
                        "AppName": "fixture.exe",
                        "ModuleName": "fixture.dll",
                        "ExceptionCode": "0xc0000005",
                    },
                },
        ]
        if request.log_names == ["System"] and request.event_ids:
            if request.provider_names == ["Microsoft-Windows-Kernel-General"]:
                return [
                    {
                        "Timestamp": "2026-01-03T09:59:50Z",
                        "Level": "Information",
                        "Provider": "Microsoft-Windows-Kernel-General",
                        "EventId": 12,
                        "Channel": "System",
                        "Message": "The operating system started.",
                        "RecordId": 201,
                        "EventData": {},
                    }
                ]
            if request.provider_names and request.provider_names != ["EventLog"]:
                return []
            return [
                {
                    "Timestamp": "2026-01-03T10:00:00Z",
                    "Level": "Information",
                    "Provider": "EventLog",
                    "EventId": 6005,
                    "Channel": "System",
                    "Message": "Event Log service started.",
                    "RecordId": 200,
                    "EventData": {},
                },
                {
                    "Timestamp": "2026-01-03T09:55:00Z",
                    "Level": "Information",
                    "Provider": "EventLog",
                    "EventId": 6006,
                    "Channel": "System",
                    "Message": "Event Log service stopped.",
                    "RecordId": 199,
                    "EventData": {},
                },
            ]
        if request.log_names == ["Microsoft-Windows-Diagnostics-Performance/Operational"]:
            return [
                {
                    "Timestamp": "2026-01-03T10:00:30Z",
                    "Level": "Information",
                    "Provider": "Diagnostics-Performance",
                    "EventId": 100,
                    "Channel": request.log_names[0],
                    "Message": "Windows started.",
                    "RecordId": 300,
                    "EventData": {"BootTime": "12345"},
                },
                {
                    "Timestamp": "2026-01-03T10:00:31Z",
                    "Level": "Warning",
                    "Provider": "Diagnostics-Performance",
                    "EventId": 101,
                    "Channel": request.log_names[0],
                    "Message": "An application delayed startup.",
                    "RecordId": 301,
                    "EventData": {"FileName": "fixture.exe"},
                },
            ]
        return [
            {
                "Timestamp": "2026-01-03T11:00:00Z",
                "Level": "Warning",
                "Provider": "Fixture Provider",
                "EventId": 7,
                "Channel": "System",
                "Message": "A fixture warning.\nAdditional context.",
                "RecordId": 400,
                "Task": "Fixture Task",
                "Opcode": "Info",
                "ProcessId": 10,
                "ThreadId": 20,
                "ActivityId": "fixture-activity",
                "EventData": {"Device": "fixture"},
            }
        ]


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
    reader = FixtureReader()
    provider = WindowsInspectionProvider(reader, graphics_reader=reader)
    basic = await provider.gpu(details=False)
    assert len(basic.adapters) == 1
    adapter = basic.adapters[0]
    assert adapter.identity.name == "Fixture GPU"
    assert adapter.identity.adapter_type == "hardware"
    assert adapter.configuration.dedicated_vram_bytes == 12 * 1024**3
    assert adapter.current_state.utilization_percent is None
    assert adapter.current_state.primary
    assert adapter.details is None

    detailed = await provider.gpu(details=True)
    assert detailed.adapters[0].details is not None
    assert detailed.adapters[0].details.driver_provider == "Fixture Driver Provider"
    assert detailed.adapters[0].details.driver_inf == "fixture.inf"
    assert detailed.adapters[0].details.display_resolution == "2560x1440"
    assert detailed.adapters[0].details.dedicated_vram_source == "DXGI"
    assert detailed.adapters[0].details.shared_system_memory_bytes == 16 * 1024**3


@pytest.mark.asyncio
async def test_gpu_preserves_unavailable_vram_when_dxgi_provider_fails():
    class FailedGraphicsReader:
        async def graphics_adapters(self) -> list[dict[str, JsonValue]]:
            raise InspectionError("CapabilityUnavailable")

    result = await WindowsInspectionProvider(
        FixtureReader(), graphics_reader=FailedGraphicsReader()
    ).gpu(details=False)
    assert result.adapters[0].configuration.dedicated_vram_bytes is None
    assert result.warnings[0].source == "DXGI adapter inventory"


def test_vendor_gpu_capacity_overrides_dxgi_capacity_without_adding_telemetry():
    dxgi = [
        {
            "Name": "Fixture GPU",
            "DedicatedVideoMemory": 11 * 1024**3,
            "VendorId": 0x1234,
        }
    ]
    vendor = [
        {
            "Name": "Fixture GPU",
            "DedicatedVideoMemory": 12 * 1024**3,
            "CapacitySource": "Vendor inventory",
        }
    ]
    merged = WindowsCimReader._merge_graphics_memory(dxgi, vendor)
    assert merged[0]["DedicatedVideoMemory"] == 12 * 1024**3
    assert merged[0]["CapacitySource"] == "Vendor inventory"
    assert "Utilization" not in merged[0]


@pytest.mark.asyncio
async def test_storage_reports_disks_volumes_details_and_low_space_observation():
    reader = FixtureReader()
    provider = WindowsInspectionProvider(
        reader,
        storage_reliability_reader=reader,
        storage_trim_reader=reader,
        volume_encryption_reader=reader,
    )
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
    assert detailed.physical_disks[0].details.temperature_celsius == 39
    assert detailed.physical_disks[0].details.read_errors == 2
    assert detailed.physical_disks[0].details.wear_percent == 4
    assert detailed.volumes[0].details is not None
    assert detailed.volumes[0].details.encryption_status == "FullyEncrypted"
    assert detailed.volumes[0].details.encryption_protection == "On"
    assert detailed.trim_configuration[0].delete_notifications_enabled


@pytest.mark.asyncio
async def test_storage_optional_provider_failures_preserve_base_inventory():
    class FailedStorageReader:
        async def storage_reliability(self) -> list[dict[str, JsonValue]]:
            raise InspectionError("PermissionDenied")

        async def volume_encryption(self) -> list[dict[str, JsonValue]]:
            raise InspectionError("PermissionDenied")

        async def trim_configuration(self) -> list[dict[str, JsonValue]]:
            raise InspectionError("CapabilityUnavailable")

    reader = FixtureReader()
    failed = FailedStorageReader()
    result = await WindowsInspectionProvider(
        reader,
        storage_reliability_reader=failed,
        storage_trim_reader=failed,
        volume_encryption_reader=failed,
    ).storage(details=True)
    assert result.physical_disks[0].details is not None
    assert result.physical_disks[0].details.temperature_celsius is None
    assert result.volumes[0].details is not None
    assert result.volumes[0].details.encryption_status is None
    assert result.trim_configuration == []
    assert {warning.code for warning in result.warnings} == {
        "PermissionDenied",
        "CapabilityUnavailable",
    }


@pytest.mark.asyncio
async def test_network_default_and_details_are_scoped_and_structured():
    reader = FixtureReader()
    provider = WindowsInspectionProvider(
        reader,
        network_statistics_reader=reader,
        wifi_quality_reader=reader,
    )
    basic = await provider.network(details=False)
    assert len(basic.adapters) == 1
    adapter = basic.adapters[0]
    assert adapter.identity.classification == "Ethernet"
    assert adapter.current_state.connected
    assert adapter.current_state.link_speed_bps == 2500000000
    assert adapter.current_state.ipv4_addresses == ["192.0.2.10"]
    assert adapter.current_state.ipv6_addresses == ["2001:db8::10"]
    assert adapter.current_state.receive_bytes_per_second == 4096
    assert adapter.current_state.send_bytes_per_second == 1024
    assert adapter.current_state.throughput_measurement == "derived"
    assert adapter.current_state.wifi_signal_percent == 82
    assert adapter.current_state.wifi_receive_link_speed_bps == 866_000_000
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
    assert item.receive_errors == 2
    assert item.send_discards == 3
    assert item.throughput_sample_seconds == 0.5
    assert detailed.adapters[0].current_state.wifi_ssid is None


@pytest.mark.asyncio
async def test_network_statistics_failure_preserves_adapter_inventory():
    class FailedStatisticsReader:
        async def network_statistics(self) -> list[dict[str, JsonValue]]:
            raise InspectionError("PermissionDenied")

    result = await WindowsInspectionProvider(
        FixtureReader(), network_statistics_reader=FailedStatisticsReader()
    ).network(details=False)
    assert result.adapters[0].current_state.receive_bytes_per_second is None
    assert result.warnings[0].source == "Network adapter statistics"


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
    provider = WindowsInspectionProvider(reader, service_dependency_reader=reader)
    basic = await provider.services(details=False)
    assert basic.services[0].identity.name == "FixtureService"
    assert basic.services[0].configuration.startup_type == "Auto"
    assert basic.services[0].current_state.state == "Running"
    assert basic.services[0].details is None

    detailed = await provider.services(details=True)
    assert detailed.services[0].details is not None
    assert detailed.services[0].details.service_account == "LocalSystem"
    assert detailed.services[0].details.pid == 123
    assert detailed.services[0].details.dependencies == ["RpcSs"]
    assert detailed.services[0].details.dependent_services == ["DependentFixture"]


@pytest.mark.asyncio
async def test_service_dependency_failure_preserves_service_inventory():
    class FailedDependencyReader:
        async def service_dependencies(self) -> list[dict[str, JsonValue]]:
            raise InspectionError("PermissionDenied")

    result = await WindowsInspectionProvider(
        FixtureReader(), service_dependency_reader=FailedDependencyReader()
    ).services(details=True)
    assert result.services[0].details is not None
    assert result.services[0].details.dependencies == []
    assert result.warnings[0].source == "Service dependency inventory"


@pytest.mark.asyncio
async def test_startup_preserves_unknown_enabled_state_and_adds_source_details():
    provider = WindowsInspectionProvider(FixtureReader())
    basic = await provider.startup(details=False)
    assert basic.items[0].identity.name == "Fixture Startup"
    assert basic.items[0].configuration.enabled is None
    assert basic.items[0].configuration.source_type == "registry"
    assert basic.items[0].configuration.scope == "user"
    assert basic.items[0].details is None

    detailed = await provider.startup(details=True)
    assert detailed.items[0].details is not None
    assert detailed.items[0].details.user_sid == "S-1-5-21-fixture"
    assert detailed.items[0].details.arguments is None


@pytest.mark.asyncio
async def test_driver_inventory_correlates_device_status_and_details():
    provider = WindowsInspectionProvider(FixtureReader())
    basic = await provider.drivers(details=False)
    display = next(item for item in basic.drivers if item.identity.device_name == "Fixture GPU")
    assert display.identity.device_class == "Display"
    assert display.configuration.version == "1.2.3"
    assert display.health_status == "OK"
    assert display.details is None

    detailed = await provider.drivers(details=True)
    display = next(item for item in detailed.drivers if item.identity.device_name == "Fixture GPU")
    assert display.details is not None
    assert display.details.inf_name == "fixture.inf"
    assert display.details.hardware_ids == ["PCI\\VEN_FIXTURE&DEV_0001"]
    assert display.details.problem_code == 0


@pytest.mark.asyncio
async def test_software_uses_registry_inventory_without_installer_provider():
    reader = FixtureReader()
    provider = WindowsInspectionProvider(reader, software_reader=reader)
    basic = await provider.software(details=False)
    assert basic.applications[0].identity.name == "Fixture App"
    assert basic.applications[0].configuration.installation_scope == "machine"
    assert basic.applications[0].configuration.install_date == date(2026, 1, 2)
    assert basic.applications[0].details is None

    detailed = await provider.software(details=True)
    assert detailed.applications[0].details is not None
    assert detailed.applications[0].details.architecture == "x64"
    assert detailed.applications[0].details.install_channel == "MSI"


@pytest.mark.asyncio
async def test_events_use_bounded_relevant_filter_and_curated_details():
    reader = FixtureReader()
    provider = WindowsInspectionProvider(reader, event_reader=reader)
    basic = await provider.events(details=False)
    assert "last 24 hours" in basic.filter_description
    assert basic.events[0].summary == "A fixture warning. Additional context."
    assert basic.events[0].details is None

    detailed = await provider.events(details=True)
    assert detailed.events[0].details is not None
    assert detailed.events[0].details.record_id == 400
    assert detailed.events[0].details.event_data == {"Device": "fixture"}


@pytest.mark.asyncio
async def test_crashes_group_matching_events_without_claiming_causality():
    reader = FixtureReader()
    result = await WindowsInspectionProvider(reader, event_reader=reader).crashes(details=True)
    assert len(result.crashes) == 1
    crash = result.crashes[0]
    assert crash.affected_application == "fixture.exe"
    assert crash.faulting_module == "fixture.dll"
    assert crash.exception_code == "0xc0000005"
    assert crash.recurrence_count == 2
    assert crash.details is not None
    assert crash.details.application_version == "1.2.3"


@pytest.mark.asyncio
async def test_crashes_filter_unrelated_wer_and_do_not_guess_kernel_fields():
    class WerReader(FixtureReader):
        async def query_events(self, request: EventQuery) -> list[dict[str, JsonValue]]:
            return [
                {
                    "Timestamp": "2026-01-03T12:00:00Z",
                    "EventId": 1001,
                    "EventData": {"EventName": "StoreAgentInstallFailure1", "P1": "Update"},
                },
                {
                    "Timestamp": "2026-01-03T11:00:00Z",
                    "EventId": 1001,
                    "RecordId": 80,
                    "EventData": {
                        "EventName": "LiveKernelEvent",
                        "P1": "193",
                        "P4": "ffff0000",
                        "P7": "0_0",
                        "HashedBucket": "fixture-bucket",
                    },
                },
            ]

    result = await WindowsInspectionProvider(WerReader(), event_reader=WerReader()).crashes(
        details=True
    )
    assert len(result.crashes) == 1
    crash = result.crashes[0]
    assert crash.crash_type == "LiveKernelEvent"
    assert crash.affected_application is None
    assert crash.faulting_module is None
    assert crash.exception_code is None
    assert crash.details is not None
    assert crash.details.bucket_id == "fixture-bucket"
    assert crash.details.event_data == {
        "EventName": "LiveKernelEvent",
        "HashedBucket": "fixture-bucket",
    }


def test_human_event_output_sanitizes_console_direction_markers():
    data = EventsInspection(
        filter_description="fixture",
        events=[
            EventRecord(
                summary="A \u200edirectional marker",
                details=EventDetails(full_message="Line one\nLine two \u200evalue"),
            )
        ],
    )
    timestamp = datetime.now(UTC)
    rendered = render_human(
        InspectionResult(
            capability="events",
            started_at=timestamp,
            finished_at=timestamp,
            success=True,
            data=data,
        )
    )
    assert "\u200e" not in rendered
    assert "Line one Line two value" in rendered


@pytest.mark.asyncio
async def test_boot_correlates_records_as_evidence_and_reports_duration():
    reader = FixtureReader()
    result = await WindowsInspectionProvider(reader, event_reader=reader).boot(details=True)
    assert result.previous_shutdown == "normal"
    assert result.latest_boot_duration_ms == 12345
    assert result.recent_boot_times[0] == datetime(2026, 1, 3, 9, 59, 50, tzinfo=UTC)
    assert result.startup_warnings[0].event_id == 101
    assert result.evidence is not None
    assert any(item.event_id == 6005 for item in result.evidence)


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

        async def startup(self, *, details: bool):
            raise InspectionError("PermissionDenied")

        async def drivers(self, *, details: bool):
            raise InspectionError("PermissionDenied")

        async def software(self, *, details: bool):
            raise InspectionError("PermissionDenied")

        async def events(self, *, details: bool):
            raise InspectionError("PermissionDenied")

        async def crashes(self, *, details: bool):
            raise InspectionError("PermissionDenied")

        async def boot(self, *, details: bool):
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


@pytest.mark.asyncio
async def test_windows_software_reader_validates_structured_output(
    monkeypatch: pytest.MonkeyPatch,
):
    reader = WindowsCimReader()
    execute = AsyncMock(return_value=b'[{"DisplayName":"Fixture App"}]')
    monkeypatch.setattr(reader, "_execute", execute)
    assert await reader.installed_software() == [{"DisplayName": "Fixture App"}]
    await_call = execute.await_args
    assert await_call is not None
    assert await_call.args[1] == b""


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method_name", "payload"),
    [
        (
            "service_dependencies",
            b'[{"Antecedent":"RpcSs","Dependent":"FixtureService"}]',
        ),
        (
            "trim_configuration",
            b'[{"FileSystem":"NTFS","DeleteNotificationsEnabled":true}]',
        ),
        (
            "network_statistics",
            b'[{"Name":"Wi-Fi","ReceiveBytesPerSecond":1024}]',
        ),
    ],
)
async def test_specialized_windows_readers_validate_structured_output(
    monkeypatch: pytest.MonkeyPatch,
    method_name: str,
    payload: bytes,
):
    reader = WindowsCimReader()
    execute = AsyncMock(return_value=payload)
    monkeypatch.setattr(reader, "_execute", execute)
    method = getattr(reader, method_name)
    rows = await method()
    assert len(rows) == 1
    assert execute.await_args is not None
    assert execute.await_args.args[1] == b""


@pytest.mark.asyncio
async def test_windows_wifi_quality_reader_maps_native_permission_failure(
    monkeypatch: pytest.MonkeyPatch,
):
    def denied() -> list[dict[str, JsonValue]]:
        raise PermissionError("denied")

    monkeypatch.setattr("sys_eden.windows_native.query_wifi_quality", denied)
    with pytest.raises(InspectionError, match="PermissionDenied"):
        await WindowsCimReader().wifi_quality()


@pytest.mark.asyncio
async def test_windows_graphics_reader_uses_vendor_capacity_over_dxgi(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "sys_eden.windows_native.query_dxgi_adapters",
        lambda: [{"Name": "Fixture GPU", "DedicatedVideoMemory": 11 * 1024**3}],
    )
    reader = WindowsCimReader()
    monkeypatch.setattr(
        reader,
        "_nvidia_memory_inventory",
        AsyncMock(
            return_value=[
                {
                    "Name": "Fixture GPU",
                    "DedicatedVideoMemory": 12 * 1024**3,
                    "CapacitySource": "NVIDIA SMI",
                }
            ]
        ),
    )
    rows = await reader.graphics_adapters()
    assert rows[0]["DedicatedVideoMemory"] == 12 * 1024**3
    assert rows[0]["CapacitySource"] == "NVIDIA SMI"


@pytest.mark.asyncio
async def test_windows_graphics_reader_keeps_vendor_fallback_when_dxgi_fails(
    monkeypatch: pytest.MonkeyPatch,
):
    def unavailable() -> list[dict[str, JsonValue]]:
        raise OSError("DXGI unavailable")

    monkeypatch.setattr("sys_eden.windows_native.query_dxgi_adapters", unavailable)
    reader = WindowsCimReader()
    monkeypatch.setattr(
        reader,
        "_nvidia_memory_inventory",
        AsyncMock(
            return_value=[
                {
                    "Name": "Fixture GPU",
                    "DedicatedVideoMemory": 1,
                    "CapacitySource": "NVIDIA SMI",
                }
            ]
        ),
    )
    assert await reader.graphics_adapters() == [
        {
            "Name": "Fixture GPU",
            "DedicatedVideoMemory": 1,
            "CapacitySource": "NVIDIA SMI",
        }
    ]


def test_event_query_rejects_unbounded_or_arbitrary_logs():
    with pytest.raises(ValidationError):
        EventQuery.model_validate(
            {"log_names": ["Security"], "since_hours": 24, "limit": 50}
        )
    with pytest.raises(ValidationError):
        EventQuery(log_names=["System"], since_hours=24, limit=501)
    with pytest.raises(ValidationError):
        EventQuery.model_validate(
            {
                "log_names": ["System"],
                "provider_names": ["Untrusted Provider"],
                "since_hours": 24,
                "limit": 10,
            }
        )


@pytest.mark.asyncio
async def test_windows_event_reader_validates_structured_output(
    monkeypatch: pytest.MonkeyPatch,
):
    reader = WindowsCimReader()
    execute = AsyncMock(return_value=b'[{"EventId":7,"Channel":"System"}]')
    monkeypatch.setattr(reader, "_execute", execute)
    request = EventQuery(log_names=["System"], since_hours=24, limit=10)
    assert await reader.query_events(request) == [{"EventId": 7, "Channel": "System"}]
    await_call = execute.await_args
    assert await_call is not None
    assert json.loads(await_call.args[1])["limit"] == 10
