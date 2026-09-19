import asyncio
import json
from unittest.mock import AsyncMock

import pytest
from pydantic import JsonValue, ValidationError
from typer.testing import CliRunner

from sys_eden.cli import app
from sys_eden.inspection import CimQuery, InspectionError, collect
from sys_eden.windows import WindowsCimReader


@pytest.mark.asyncio
async def test_collector_uses_structured_query():
    class Reader:
        async def query(self, request: CimQuery) -> list[dict[str, JsonValue]]:
            assert request.class_name == "Win32_Processor"
            assert "Name" in request.properties
            return [{"Name": "Fixture CPU", "NumberOfCores": 4}]

    result = await collect("cpu", Reader())
    assert result.success
    assert result.data[0]["NumberOfCores"] == 4
    assert result.finished_at >= result.started_at


@pytest.mark.asyncio
async def test_collector_reports_failure_without_claiming_empty_success():
    class Reader:
        async def query(self, request: CimQuery) -> list[dict[str, JsonValue]]:
            raise InspectionError("PermissionDenied")

    result = await collect("ram", Reader())
    assert not result.success
    assert result.error == "PermissionDenied"


def test_generic_query_rejects_mutating_provider_and_script_properties():
    with pytest.raises(ValidationError):
        CimQuery.model_validate({"class_name": "Win32_Product", "properties": ["Name"]})
    with pytest.raises(ValidationError):
        CimQuery(class_name="Win32_Processor", properties=["Name; exit"])


def test_cli_component_is_positional(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(WindowsCimReader, "query", AsyncMock(return_value=[{"Name": "Fixture"}]))
    result = CliRunner().invoke(app, ["inspect", "cpu"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)[0]["capability"] == "cpu"


@pytest.mark.asyncio
@pytest.mark.parametrize("output,code,expected", [
    (b'[{"Name":"Fixture"}]', 0, None),
    (b'private error text', 1, "ExecutionFailed"),
    (b'not json', 0, "InvalidToolOutput"),
])
async def test_windows_adapter_output(
    monkeypatch: pytest.MonkeyPatch, output: bytes, code: int, expected: str | None,
):
    class Process:
        returncode = code

        async def communicate(self, data: bytes):
            assert json.loads(data)["class_name"] == "Win32_Processor"
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
    monkeypatch: pytest.MonkeyPatch, failure: type[BaseException],
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
