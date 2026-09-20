"""Fixed read-only CIM script executed as the current user without shell interpolation."""

import asyncio
import csv
import os
import subprocess
import sys
from pathlib import Path

from pydantic import JsonValue, TypeAdapter, ValidationError

from sys_eden.inspection import CimQuery, EventQuery, InspectionError

_ROWS = TypeAdapter(list[dict[str, JsonValue]])
_SCRIPT = """
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
try {
    $request = [Console]::In.ReadToEnd() | ConvertFrom-Json
    $rows = @(Get-CimInstance -Namespace $request.namespace -ClassName $request.class_name |
        Select-Object -First $request.limit -Property $request.properties)
    ConvertTo-Json -InputObject $rows -Depth 5 -Compress
} catch {
    exit 1
}
"""

_SOFTWARE_SCRIPT = """
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$roots = @(
    @{Path='HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*'; Scope='machine'; Architecture='x64'},
    @{Path='HKLM:\\Software\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*'; Scope='machine'; Architecture='x86'},
    @{Path='HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*'; Scope='user'; Architecture=$null}
)
$rows = foreach ($root in $roots) {
    Get-ItemProperty -Path $root.Path -ErrorAction SilentlyContinue |
        Where-Object { $_.DisplayName } |
        ForEach-Object {
            [PSCustomObject]@{
                DisplayName = $_.DisplayName
                DisplayVersion = $_.DisplayVersion
                Publisher = $_.Publisher
                InstallDate = $_.InstallDate
                InstallLocation = $_.InstallLocation
                InstallSource = $_.InstallSource
                RegistrySource = $_.PSPath
                UninstallIdentifier = $_.PSChildName
                ProductIdentifier = if ($_.WindowsInstaller -eq 1) { $_.PSChildName } else { $null }
                Scope = $root.Scope
                Architecture = $root.Architecture
                InstallChannel = if ($_.WindowsInstaller -eq 1) { 'MSI' } else { 'registry' }
            }
        }
}
ConvertTo-Json -InputObject @($rows) -Depth 4 -Compress
"""

_SERVICE_DEPENDENCY_SCRIPT = """
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$rows = foreach ($relation in @(Get-CimInstance -ClassName Win32_DependentService)) {
    [PSCustomObject]@{
        Antecedent = $relation.Antecedent.Name
        Dependent = $relation.Dependent.Name
        TypeOfDependency = $relation.TypeOfDependency
    }
}
ConvertTo-Json -InputObject @($rows) -Depth 3 -Compress
"""

_TRIM_CONFIGURATION_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$output = @(& "$env:SystemRoot\System32\fsutil.exe" behavior query DisableDeleteNotify 2>$null)
if ($LASTEXITCODE -ne 0) { exit 1 }
$rows = foreach ($line in $output) {
    if ($line -match '^\s*(?<filesystem>\S+)\s+DisableDeleteNotify\s*=\s*(?<value>[01])') {
        [PSCustomObject]@{
            FileSystem = $matches.filesystem
            DeleteNotificationsEnabled = ($matches.value -eq '0')
        }
    }
}
ConvertTo-Json -InputObject @($rows) -Depth 3 -Compress
"""

_NETWORK_STATISTICS_SCRIPT = """
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$before = @(Get-NetAdapterStatistics -ErrorAction Stop)
$timer = [Diagnostics.Stopwatch]::StartNew()
Start-Sleep -Milliseconds 500
$after = @(Get-NetAdapterStatistics -ErrorAction Stop)
$timer.Stop()
$elapsed = $timer.Elapsed.TotalSeconds
$byName = @{}
foreach ($item in $before) { $byName[[string]$item.Name] = $item }
$rows = foreach ($item in $after) {
    $previous = $byName[[string]$item.Name]
    $receiveRate = $null
    $sendRate = $null
    if ($null -ne $previous -and $elapsed -gt 0) {
        $receiveRate = [Math]::Max(0, [int64](($item.ReceivedBytes - $previous.ReceivedBytes) / $elapsed))
        $sendRate = [Math]::Max(0, [int64](($item.SentBytes - $previous.SentBytes) / $elapsed))
    }
    [PSCustomObject]@{
        Name = $item.Name
        InterfaceDescription = $item.InterfaceDescription
        ReceiveBytesPerSecond = $receiveRate
        SendBytesPerSecond = $sendRate
        SampleSeconds = $elapsed
        ReceivedPacketErrors = $item.ReceivedPacketErrors
        OutboundPacketErrors = $item.OutboundPacketErrors
        ReceivedDiscardedPackets = $item.ReceivedDiscardedPackets
        OutboundDiscardedPackets = $item.OutboundDiscardedPackets
    }
}
ConvertTo-Json -InputObject @($rows) -Depth 3 -Compress
"""

_EVENT_SCRIPT = """
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$request = [Console]::In.ReadToEnd() | ConvertFrom-Json
$filter = @{
    LogName = @($request.log_names)
    StartTime = (Get-Date).AddHours(-[double]$request.since_hours)
}
if (@($request.event_ids).Count -gt 0) { $filter.Id = @($request.event_ids) }
if (@($request.levels).Count -gt 0) { $filter.Level = @($request.levels) }
if (@($request.provider_names).Count -gt 0) { $filter.ProviderName = @($request.provider_names) }
$events = @()
try {
    $events = @(Get-WinEvent -FilterHashtable $filter -MaxEvents $request.limit -ErrorAction Stop)
} catch {
    if ($_.FullyQualifiedErrorId -notlike 'NoMatchingEventsFound*') { exit 1 }
}
$rows = foreach ($event in $events) {
    $eventData = @{}
    $processId = $null
    $threadId = $null
    $activityId = $null
    if ($request.include_event_data) {
        try {
            [xml]$eventXml = $event.ToXml()
            $index = 0
            foreach ($node in @($eventXml.Event.EventData.Data)) {
                $key = if ($node.Name) { [string]$node.Name } else { "value_$index" }
                $eventData[$key] = [string]$node.InnerText
                $index++
            }
            $processId = $eventXml.Event.System.Execution.ProcessID
            $threadId = $eventXml.Event.System.Execution.ThreadID
            $activityId = $eventXml.Event.System.Correlation.ActivityID
        } catch {}
    }
    $message = $null
    try { $message = $event.Message } catch {}
    [PSCustomObject]@{
        Timestamp = if ($event.TimeCreated) { $event.TimeCreated.ToUniversalTime().ToString('o') } else { $null }
        Level = $event.LevelDisplayName
        LevelCode = $event.Level
        Provider = $event.ProviderName
        EventId = $event.Id
        Channel = $event.LogName
        Message = $message
        RecordId = $event.RecordId
        Task = $event.TaskDisplayName
        Opcode = $event.OpcodeDisplayName
        ProcessId = $processId
        ThreadId = $threadId
        ActivityId = $activityId
        EventData = $eventData
    }
}
ConvertTo-Json -InputObject @($rows) -Depth 8 -Compress
"""


class WindowsCimReader:
    async def query(self, request: CimQuery) -> list[dict[str, JsonValue]]:
        stdout = await self._execute(_SCRIPT, request.model_dump_json().encode("utf-8"))
        try:
            return _ROWS.validate_json(stdout)
        except ValidationError as error:
            raise InspectionError("InvalidToolOutput") from error

    async def installed_software(self) -> list[dict[str, JsonValue]]:
        stdout = await self._execute(_SOFTWARE_SCRIPT, b"")
        try:
            return _ROWS.validate_json(stdout)
        except ValidationError as error:
            raise InspectionError("InvalidToolOutput") from error

    async def graphics_adapters(self) -> list[dict[str, JsonValue]]:
        from sys_eden.windows_native import query_dxgi_adapters

        dxgi_rows: list[dict[str, JsonValue]] = []
        dxgi_error: OSError | None = None
        try:
            async with asyncio.timeout(5):
                dxgi_rows = await asyncio.to_thread(query_dxgi_adapters)
        except TimeoutError as error:
            raise InspectionError("ToolTimeout") from error
        except OSError as error:
            dxgi_error = error
        nvidia_rows = await self._nvidia_memory_inventory()
        if not dxgi_rows and not nvidia_rows and dxgi_error is not None:
            raise InspectionError("CapabilityUnavailable") from dxgi_error
        return self._merge_graphics_memory(dxgi_rows, nvidia_rows)

    async def service_dependencies(self) -> list[dict[str, JsonValue]]:
        stdout = await self._execute(_SERVICE_DEPENDENCY_SCRIPT, b"")
        try:
            return _ROWS.validate_json(stdout)
        except ValidationError as error:
            raise InspectionError("InvalidToolOutput") from error

    async def trim_configuration(self) -> list[dict[str, JsonValue]]:
        stdout = await self._execute(_TRIM_CONFIGURATION_SCRIPT, b"")
        try:
            return _ROWS.validate_json(stdout)
        except ValidationError as error:
            raise InspectionError("InvalidToolOutput") from error

    async def network_statistics(self) -> list[dict[str, JsonValue]]:
        stdout = await self._execute(_NETWORK_STATISTICS_SCRIPT, b"")
        try:
            return _ROWS.validate_json(stdout)
        except ValidationError as error:
            raise InspectionError("InvalidToolOutput") from error

    async def wifi_quality(self) -> list[dict[str, JsonValue]]:
        from sys_eden.windows_native import query_wifi_quality

        try:
            async with asyncio.timeout(5):
                return await asyncio.to_thread(query_wifi_quality)
        except TimeoutError as error:
            raise InspectionError("ToolTimeout") from error
        except PermissionError as error:
            raise InspectionError("PermissionDenied") from error
        except OSError as error:
            raise InspectionError("CapabilityUnavailable") from error

    async def _nvidia_memory_inventory(self) -> list[dict[str, JsonValue]]:
        executable = Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32/nvidia-smi.exe"
        if not executable.is_file():
            return []
        try:
            process = await asyncio.create_subprocess_exec(
                str(executable),
                "--query-gpu=name,memory.total,pci.bus_id",
                "--format=csv,noheader,nounits",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except OSError:
            return []
        try:
            async with asyncio.timeout(5):
                stdout, _ = await process.communicate()
        except (TimeoutError, asyncio.CancelledError) as error:
            if process.returncode is None:
                process.kill()
            await process.wait()
            if isinstance(error, asyncio.CancelledError):
                raise
            return []
        if process.returncode != 0:
            return []
        rows: list[dict[str, JsonValue]] = []
        for fields in csv.reader(stdout.decode("utf-8", errors="replace").splitlines()):
            if len(fields) != 3:
                continue
            name, memory_mib, pci_bus_id = (field.strip() for field in fields)
            try:
                capacity = int(memory_mib) * 1024**2
            except ValueError:
                continue
            rows.append(
                {
                    "Name": name,
                    "DedicatedVideoMemory": capacity,
                    "PciBusId": pci_bus_id,
                    "CapacitySource": "NVIDIA SMI",
                }
            )
        return rows

    @staticmethod
    def _merge_graphics_memory(
        dxgi_rows: list[dict[str, JsonValue]],
        vendor_rows: list[dict[str, JsonValue]],
    ) -> list[dict[str, JsonValue]]:
        merged = [row | {"CapacitySource": "DXGI"} for row in dxgi_rows]
        for vendor in vendor_rows:
            name = vendor.get("Name")
            matches = []
            if isinstance(name, str):
                for row in merged:
                    row_name = row.get("Name")
                    if isinstance(row_name, str) and row_name.casefold() == name.casefold():
                        matches.append(row)
            if not matches:
                merged.append(vendor)
                continue
            for match in matches:
                match.update(vendor)
        return merged

    async def query_events(self, request: EventQuery) -> list[dict[str, JsonValue]]:
        stdout = await self._execute(_EVENT_SCRIPT, request.model_dump_json().encode("utf-8"))
        try:
            return _ROWS.validate_json(stdout)
        except ValidationError as error:
            raise InspectionError("InvalidToolOutput") from error

    async def _execute(self, script: str, input_data: bytes) -> bytes:
        if sys.platform != "win32":
            raise InspectionError("CapabilityUnavailable")
        executable = (
            Path(os.environ.get("SystemRoot", "C:/Windows"))
            / "System32/WindowsPowerShell/v1.0/powershell.exe"
        )
        try:
            process = await asyncio.create_subprocess_exec(
                str(executable),
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                script,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except OSError as error:
            raise InspectionError("CapabilityUnavailable") from error
        try:
            async with asyncio.timeout(20):
                stdout, _ = await process.communicate(input_data)
        except (TimeoutError, asyncio.CancelledError) as error:
            if process.returncode is None:
                process.kill()
            await process.wait()
            if isinstance(error, asyncio.CancelledError):
                raise
            raise InspectionError("ToolTimeout") from error
        if process.returncode != 0:
            raise InspectionError("ExecutionFailed")
        return stdout
