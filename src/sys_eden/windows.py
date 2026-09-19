"""Fixed read-only CIM script executed as the current user without shell interpolation."""

import asyncio
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
