import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from sys_eden.config import ModelSettings, Settings
from sys_eden.core_application import (
    CoreApplication,
    CoreLifecycleState,
    SystemServiceState,
)
from sys_eden.core_client import CoreUnavailable, InProcessCoreClient
from sys_eden.core_rpc import CoreRpcDispatcher, RpcRequest
from sys_eden.models import FakeModelProvider
from sys_eden.task_models import TaskState


def _application(path: Path) -> CoreApplication:
    return CoreApplication(
        Settings(
            data_directory=path,
            model=ModelSettings(provider="fake", default_model="fake-diagnostic"),
        ),
        FakeModelProvider(),
    )


@pytest.mark.asyncio
async def test_client_can_open_stopped_start_core_and_return_to_same_stopped_state(
    tmp_path: Path,
):
    application = _application(tmp_path)
    client = InProcessCoreClient(application)
    try:
        assert (await client.status()).state is CoreLifecycleState.STOPPED
        assert (await client.status()).system_service is SystemServiceState.NOT_IMPLEMENTED
        with pytest.raises(CoreUnavailable, match="does not start Core automatically"):
            await client.list_tasks()

        running = await client.start_core()
        assert running.state is CoreLifecycleState.RUNNING
        assert running.runtime_session_id is not None
        assert await client.list_tasks() == []

        stopped = await client.stop_core()
        assert stopped.state is CoreLifecycleState.STOPPED
        with pytest.raises(CoreUnavailable):
            await client.list_tasks()
    finally:
        application.close()


def test_core_restart_detects_interrupted_synthetic_work_and_marks_it_recovery_required(
    tmp_path: Path,
):
    first = _application(tmp_path)
    first.start()
    synthetic = first.synthetic_tasks.create_checkpoint_demo()
    assert synthetic.id.startswith("TST-")
    first.close()  # Deliberately simulates a killed Core: no clean-stop record.

    restarted = _application(tmp_path)
    try:
        status = restarted.start()
        assert status.interrupted_previous_session_id is not None
        assert status.recovered_task_ids == [synthetic.id]
        recovered = restarted.tasks.get(synthetic.id)
        assert recovered.state is TaskState.RECOVERY_REQUIRED
        assert recovered.synthetic
        assert all(event.generated_test_data for event in restarted.tasks.events(synthetic.id))
    finally:
        restarted.stop()
        restarted.close()


def test_killed_isolated_core_process_recovers_synthetic_task(tmp_path: Path) -> None:
    ready_path = tmp_path / "synthetic-task-ready.txt"
    script = (
        "import os, time\n"
        "from pathlib import Path\n"
        "from sys_eden.config import ModelSettings, Settings\n"
        "from sys_eden.core_application import CoreApplication\n"
        "from sys_eden.models import FakeModelProvider\n"
        "settings = Settings(data_directory=Path(os.environ['EDEN_DATA_DIRECTORY']), "
        "model=ModelSettings(provider='fake', default_model='fake-diagnostic'))\n"
        "app = CoreApplication(settings, FakeModelProvider())\n"
        "app.start()\n"
        "task = app.synthetic_tasks.create_checkpoint_demo()\n"
        "Path(os.environ['EDEN_TEST_READY_PATH']).write_text(task.id, encoding='utf-8')\n"
        "time.sleep(30)\n"
    )
    environment = os.environ.copy()
    environment["EDEN_DATA_DIRECTORY"] = str(tmp_path)
    environment["EDEN_TEST_READY_PATH"] = str(ready_path)
    process = subprocess.Popen(
        [sys.executable, "-c", script],
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    try:
        deadline = time.monotonic() + 10
        while not ready_path.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        assert ready_path.exists(), "isolated Core did not start its synthetic test task"
        task_id = ready_path.read_text(encoding="utf-8")
        process.kill()
        process.wait(timeout=5)

        restarted = _application(tmp_path)
        try:
            status = restarted.start()
            assert status.recovered_task_ids == [task_id]
            assert restarted.tasks.get(task_id).state is TaskState.RECOVERY_REQUIRED
            reconciled = CoreRpcDispatcher(restarted).dispatch(RpcRequest(
                method="task.reconcile",
                params={"task_id": task_id, "safe_to_resume": True,
                        "message": "Generated checkpoint verified."},
            ))
            assert reconciled.ok
            assert restarted.tasks.get(task_id).state is TaskState.PAUSED
        finally:
            restarted.stop()
            restarted.close()
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
