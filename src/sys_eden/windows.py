"""Fixed read-only CIM script executed as the current user without shell interpolation."""

import asyncio
import os
import subprocess
import sys
from pathlib import Path

from pydantic import JsonValue, TypeAdapter, ValidationError

from sys_eden.inspection import CimQuery, InspectionError

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


class WindowsCimReader:
    async def query(self, request: CimQuery) -> list[dict[str, JsonValue]]:
        if sys.platform != "win32":
            raise InspectionError("CapabilityUnavailable")
        executable = (
            Path(os.environ.get("SystemRoot", "C:/Windows"))
            / "System32/WindowsPowerShell/v1.0/powershell.exe"
        )
        try:
            process = await asyncio.create_subprocess_exec(
                str(executable), "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", _SCRIPT,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except OSError as error:
            raise InspectionError("CapabilityUnavailable") from error
        try:
            async with asyncio.timeout(20):
                stdout, _ = await process.communicate(request.model_dump_json().encode("utf-8"))
        except (TimeoutError, asyncio.CancelledError) as error:
            if process.returncode is None:
                process.kill()
            await process.wait()
            if isinstance(error, asyncio.CancelledError):
                raise
            raise InspectionError("ToolTimeout") from error
        if process.returncode != 0:
            raise InspectionError("ExecutionFailed")
        try:
            return _ROWS.validate_json(stdout)
        except ValidationError as error:
            raise InspectionError("InvalidToolOutput") from error
