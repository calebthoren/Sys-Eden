import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Event
from typing import Any

import pytest

import sys_eden.core_rpc as core_rpc_module
from sys_eden.config import ModelSettings, Settings
from sys_eden.conversation_models import ReportLinkRole, TranscriptState
from sys_eden.core_application import CoreApplication
from sys_eden.core_rpc import (
    CoreRpcDispatcher,
    LocalCoreClient,
    RpcRequest,
    ensure_core_authkey,
    rpc_endpoint,
)
from sys_eden.diagnostics import (
    DiagnosticAssessment,
    DiagnosticConfidence,
    DiagnosticProgress,
    DiagnosticResult,
)
from sys_eden.models import FakeModelProvider
from sys_eden.report_models import Report, ReportState
from sys_eden.task_engine import ProgressUpdate
from sys_eden.task_models import (
    InterruptionMode,
    TaskControlRequest,
    TaskConversationLink,
    TaskState,
    TechnicalOperation,
)


def _fake_diagnosis() -> DiagnosticResult:
    return DiagnosticResult(
        model_id="fake-diagnostic",
        provider="fake",
        assessment=DiagnosticAssessment(
            summary="Generated test evidence was reviewed.",
            confidence=DiagnosticConfidence(
                diagnostic=0.8, research=0, execution=0, safety=1, overall=0.7,
                rationale="Generated test evidence only.",
            ),
            explanation="No real machine was inspected.",
        ),
        context_character_count=1,
    )


class _TestDiagnosticAssessor:
    def __init__(self, started: Event | None = None, release: Event | None = None) -> None:
        self.started = started
        self.release = release

    async def assess(
        self, *, concern: str, component: str = "system", snapshot: Any | None = None,
        historical_capsules: list[dict[str, Any]] | None = None,
        progress: DiagnosticProgress | None = None,
    ) -> DiagnosticResult:
        if self.started is not None:
            self.started.set()
        while self.release is not None and not self.release.is_set():
            await asyncio.sleep(0.01)
        return _fake_diagnosis()


class _FailingDiagnosticAssessor(_TestDiagnosticAssessor):
    async def assess(
        self, *, concern: str, component: str = "system", snapshot: Any | None = None,
        historical_capsules: list[dict[str, Any]] | None = None,
        progress: DiagnosticProgress | None = None,
    ) -> DiagnosticResult:
        raise RuntimeError("generated assessor failure")


def _application(path: Path) -> CoreApplication:
    return CoreApplication(
        Settings(
            data_directory=path,
            model=ModelSettings(provider="fake", default_model="fake-diagnostic"),
        ),
        FakeModelProvider(),
    )


@pytest.mark.skipif(os.name != "nt", reason="Windows Core launch options")
@pytest.mark.parametrize("windowed_interpreter_available", [True, False])
def test_core_launch_has_no_visible_terminal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, windowed_interpreter_available: bool
) -> None:
    python = tmp_path / "python.exe"
    pythonw = tmp_path / "pythonw.exe"
    if windowed_interpreter_available:
        pythonw.touch()
    monkeypatch.setattr(core_rpc_module.sys, "executable", str(python))
    launched: list[tuple[list[str], dict[str, object]]] = []

    def capture_launch(command: list[str], **options: object) -> None:
        launched.append((command, options))

    monkeypatch.setattr(core_rpc_module.subprocess, "Popen", capture_launch)
    LocalCoreClient(Settings(data_directory=tmp_path))._launch()

    assert len(launched) == 1
    command, options = launched[0]
    assert command == [
        str(pythonw if windowed_interpreter_available else python),
        "-m", "sys_eden.core_host",
    ]
    assert options["creationflags"] == core_rpc_module.subprocess.CREATE_NO_WINDOW
    assert options["stdin"] == core_rpc_module.subprocess.DEVNULL
    assert options["stdout"] == core_rpc_module.subprocess.DEVNULL
    assert options["stderr"] == core_rpc_module.subprocess.DEVNULL


def test_read_only_diagnosis_creates_a_linked_durable_task(tmp_path: Path) -> None:
    application = _application(tmp_path)
    application.start()
    application.chat.diagnostics = _TestDiagnosticAssessor()
    dispatcher = CoreRpcDispatcher(application)
    try:
        conversation = application.conversation_service.create_saved(title="Diagnostic fixture")
        response = dispatcher.dispatch(RpcRequest(
            method="conversation.send",
            params={"conversation_id": conversation.conversation.id,
                    "message": "Check generated GPU evidence", "diagnostic_component": "gpu"},
        ))

        assert response.ok
        assert isinstance(response.result, dict)
        task = application.tasks.get(response.result["task_id"])
        assert task.state is TaskState.COMPLETED
        assert task.progress is not None
        assert task.progress.current_phase == "collecting_evidence"
        assert task.progress.eta_status.value == "unavailable"
        assert application.tasks.conversations_for_task(task.id)[0].conversation_id == (
            conversation.conversation.id
        )
        assert task.final_summary is not None
        assert "Generated test evidence" in task.final_summary
    finally:
        application.stop()
        application.close()


def test_temporary_diagnosis_task_does_not_retain_private_chat_text(tmp_path: Path) -> None:
    application = _application(tmp_path)
    application.start()
    application.chat.diagnostics = _TestDiagnosticAssessor()
    dispatcher = CoreRpcDispatcher(application)
    private_message = "Private generated test: investigate the GPU"
    try:
        conversation = application.conversation_service.create_temporary(
            title="Temporary fixture", owner_client_id="CLI-TEST"
        )
        response = dispatcher.dispatch(RpcRequest(
            method="conversation.send",
            params={"conversation_id": conversation.conversation.id,
                    "message": private_message, "diagnostic_component": "gpu"},
        ))
        assert response.ok
        assert isinstance(response.result, dict)
        task = application.tasks.get(response.result["task_id"])
        application.conversation_service.discard_temporary(conversation.conversation.id)

        retained = [task.objective, task.final_summary or ""]
        retained.extend(event.message for event in application.tasks.events(task.id))
        assert all(private_message not in value for value in retained)
        assert task.final_summary is not None
        assert "Generated test evidence was reviewed" not in task.final_summary
    finally:
        application.stop()
        application.close()


def test_ordinary_chat_does_not_create_a_durable_task(tmp_path: Path) -> None:
    application = _application(tmp_path)
    application.start()
    dispatcher = CoreRpcDispatcher(application)
    try:
        conversation = application.conversation_service.create_saved(title="Chat fixture")
        response = dispatcher.dispatch(RpcRequest(
            method="conversation.send",
            params={"conversation_id": conversation.conversation.id,
                    "message": "Hello from a generated test"},
        ))

        assert response.ok
        assert isinstance(response.result, dict)
        assert "task_id" not in response.result
        assert application.tasks.list() == []
    finally:
        application.stop()
        application.close()


def test_conversation_warning_is_persisted_before_non_stoppable_work(tmp_path: Path) -> None:
    application = _application(tmp_path)
    application.start()
    dispatcher = CoreRpcDispatcher(application)
    try:
        conversation = application.conversation_service.create_saved(title="Warning fixture")
        task = application.task_engine.create_task(title="Fixture", objective="Generated work")
        application.tasks.link_conversation(TaskConversationLink(
            task_id=task.id, conversation_id=conversation.conversation.id,
            linked_at=datetime.now(UTC),
        ))
        application.task_engine.transition(task.id, TaskState.OBSERVING, message="Ready")
        operation = TechnicalOperation(
            kind="fixture", summary="Generated provider wait",
            interruption_mode=InterruptionMode.SAFE_BOUNDARY_ONLY,
            non_stoppable_reason="The call cannot be interrupted after it begins.",
        )
        application.task_engine.announce_non_stoppable_segment(task.id, operation)
        warnings = dispatcher.dispatch(RpcRequest(
            method="conversation.warnings",
            params={"conversation_id": conversation.conversation.id},
        ))
        assert warnings.ok
        assert isinstance(warnings.result, list)
        assert len(warnings.result) == 1
        assert "next safe boundary" in warnings.result[0]["message"]
        application.task_engine.record_progress(task.id, ProgressUpdate(
            current_phase="Generated wait", completed_major_steps=[],
            technical_operation=operation,
        ), message="Entered fixture wait")
        assert application.tasks.events(task.id)[-1].event_type.value == (
            "non_stoppable_segment_entered"
        )
    finally:
        application.stop()
        application.close()


def test_failed_diagnosis_leaves_a_terminal_audit_task(tmp_path: Path) -> None:
    application = _application(tmp_path)
    application.start()
    application.chat.diagnostics = _FailingDiagnosticAssessor()
    dispatcher = CoreRpcDispatcher(application)
    try:
        conversation = application.conversation_service.create_saved(title="Failure fixture")
        response = dispatcher.dispatch(RpcRequest(
            method="conversation.send",
            params={"conversation_id": conversation.conversation.id,
                    "message": "Check generated GPU evidence", "diagnostic_component": "gpu"},
        ))

        assert not response.ok
        tasks = application.tasks.tasks_for_conversation(conversation.conversation.id)
        assert len(tasks) == 1
        assert tasks[0].state is TaskState.FAILED
        assert tasks[0].final_summary is not None
        assert "generated assessor failure" not in tasks[0].final_summary
    finally:
        application.stop()
        application.close()


def test_closing_report_generates_candidates_without_compacting_transcripts(tmp_path: Path) -> None:
    application = _application(tmp_path)
    application.start()
    dispatcher = CoreRpcDispatcher(application)
    try:
        report = application.reports.create(
            Report(id="rpt-retention-test", title="Generated report", objective="Review retention")
        )
        conversation = application.conversation_service.create_saved(title="Linked fixture")
        application.conversation_service.link_saved_conversation(
            conversation.conversation.id, report.id,
            role=ReportLinkRole.PRIMARY,
            contribution_summary="Generated evidence and conclusion were preserved.",
        )
        response = dispatcher.dispatch(RpcRequest(
            method="report.close",
            params={"report_id": report.id, "status": "failed",
                    "summary": "Generated evidence was reviewed.",
                    "outcome": "No resolution in this generated test."},
        ))

        assert response.ok
        assert isinstance(response.result, dict)
        assert response.result["report"]["state"] == "closed"
        assert not response.result["retention_candidates"][0]["eligible"]
        assert "unique transcript evidence" in response.result["retention_candidates"][0]["reason"]
        assert response.result["transcripts_changed"] is False
        assert application.conversations.get(
            conversation.conversation.id
        ).conversation.transcript_state is TranscriptState.FULL
        review = dispatcher.dispatch(RpcRequest(
            method="report.retention_candidates", params={"report_id": report.id}
        ))
        assert review.ok
        assert review.result == response.result["retention_candidates"]
        unconfirmed = dispatcher.dispatch(RpcRequest(
            method="report.review_retention", params={"report_id": report.id}
        ))
        assert not unconfirmed.ok
        confirmed = dispatcher.dispatch(RpcRequest(
            method="report.review_retention",
            params={"report_id": report.id, "evidence_reviewed": True,
                    "unique_evidence_ids": []},
        ))
        assert confirmed.ok
        assert isinstance(confirmed.result, list)
        assert confirmed.result[0]["eligible"]
        assert application.conversations.get(
            conversation.conversation.id
        ).conversation.transcript_state is TranscriptState.FULL
    finally:
        application.stop()
        application.close()


def test_invalid_report_closure_leaves_report_open(tmp_path: Path) -> None:
    application = _application(tmp_path)
    application.start()
    dispatcher = CoreRpcDispatcher(application)
    try:
        report = application.reports.create(
            Report(id="rpt-open-test", title="Generated open report", objective="Stay open")
        )
        response = dispatcher.dispatch(RpcRequest(
            method="report.close",
            params={"report_id": report.id, "status": "resolved",
                    "summary": "Generated summary.", "outcome": "Claimed resolved without verification."},
        ))

        assert not response.ok
        assert application.reports.get(report.id).state is ReportState.OPEN
        assert application.conversations.retention_candidates(report.id) == []
    finally:
        application.stop()
        application.close()


@pytest.mark.parametrize(
    ("hard", "through_task"), [(False, False), (True, False), (False, True)]
)
def test_stop_reaches_active_diagnostic_without_storing_a_partial_answer(
    tmp_path: Path, hard: bool, through_task: bool
) -> None:
    application = _application(tmp_path)
    application.start()
    started = Event()
    release = Event()
    application.chat.diagnostics = _TestDiagnosticAssessor(started, release)
    dispatcher = CoreRpcDispatcher(application)
    conversation = application.conversation_service.create_saved(title="Stop fixture")
    with ThreadPoolExecutor(max_workers=1) as workers:
        try:
            future = workers.submit(
                dispatcher.dispatch,
                RpcRequest(
                    method="conversation.send",
                    params={"conversation_id": conversation.conversation.id,
                            "message": "Check generated GPU evidence",
                            "diagnostic_component": "gpu"},
                ),
            )
            assert started.wait(timeout=3)
            live = dispatcher.dispatch(RpcRequest(
                method="conversation.work_status",
                params={"conversation_id": conversation.conversation.id},
            ))
            assert live.ok
            assert isinstance(live.result, dict)
            assert live.result["task"]["state"] == "observing"
            assert live.result["task"]["progress"]["eta_status"] == "unavailable"
            assert live.result["elapsed_seconds"] >= 0
            if through_task:
                stopped = dispatcher.dispatch(RpcRequest(
                    method="task.cancel", params={"task_id": live.result["task"]["id"]},
                ))
            else:
                stopped = dispatcher.dispatch(RpcRequest(
                    method="conversation.stop",
                    params={"conversation_id": conversation.conversation.id, "hard": hard},
                ))
            assert stopped.ok
            assert isinstance(stopped.result, dict)
            affected_id = (
                stopped.result["id"] if through_task else stopped.result["affected_task_ids"][0]
            )
            pending = application.tasks.get(affected_id)
            if hard:
                assert pending.state is TaskState.CANCELED
            else:
                assert pending.state is TaskState.OBSERVING
                assert pending.control_request is TaskControlRequest.CANCEL
            release.set()
            response = future.result(timeout=3)
            assert not response.ok
            assert response.error is not None
            assert response.error.code == "work.stopped"
            task = application.tasks.get(affected_id)
            assert task.state is TaskState.CANCELED
            aggregate = application.conversation_service.get_for_core(conversation.conversation.id)
            assert [message.role.value for message in aggregate.messages] == ["user"]
        finally:
            release.set()
            application.stop()
            application.close()


def test_rpc_dispatcher_exposes_core_owned_services_without_ui_logic(tmp_path):
    application = _application(tmp_path)
    application.start()
    dispatcher = CoreRpcDispatcher(application)
    try:
        connected = dispatcher.dispatch(RpcRequest(method="client.connect"))
        assert connected.ok
        assert isinstance(connected.result, dict)
        assert connected.result["id"].startswith("CLI-")

        temporary = dispatcher.dispatch(
            RpcRequest(
                method="conversation.create_temporary",
                params={"client_id": connected.result["id"], "title": "RPC chat"},
            )
        )
        assert temporary.ok
        assert isinstance(temporary.result, dict)
        assert temporary.result["conversation"]["id"].startswith("TMP-")

        temporary_id = temporary.result["conversation"]["id"]
        visible_to_owner = dispatcher.dispatch(
            RpcRequest(
                method="conversation.get",
                params={
                    "conversation_id": temporary_id,
                    "client_id": connected.result["id"],
                },
            )
        )
        assert visible_to_owner.ok
        hidden_without_owner = dispatcher.dispatch(
            RpcRequest(
                method="conversation.get",
                params={"conversation_id": temporary_id},
            )
        )
        assert not hidden_without_owner.ok

        tasks = dispatcher.dispatch(RpcRequest(method="task.list"))
        assert tasks.ok
        assert isinstance(tasks.result, list)
        assert tasks.result == []
    finally:
        application.stop()
        application.close()


def test_core_auth_key_is_stable_and_endpoint_is_scoped_to_data_directory(tmp_path):
    first = Settings(data_directory=tmp_path / "first")
    second = Settings(data_directory=tmp_path / "second")
    key = ensure_core_authkey(first)
    assert len(key) == 32
    assert ensure_core_authkey(first) == key
    assert rpc_endpoint(first)[0] != rpc_endpoint(second)[0]


def test_cli_disconnect_discards_restore_right_and_undo_copy(tmp_path):
    application = _application(tmp_path)
    application.start()
    dispatcher = CoreRpcDispatcher(application)
    try:
        connected = dispatcher.dispatch(RpcRequest(method="client.connect"))
        assert connected.ok and isinstance(connected.result, dict)
        client_id = connected.result["id"]
        created = dispatcher.dispatch(
            RpcRequest(
                method="conversation.create_temporary",
                params={"client_id": client_id, "title": "Undo test"},
            )
        )
        assert created.ok and isinstance(created.result, dict)
        conversation_id = created.result["conversation"]["id"]
        deleted = dispatcher.dispatch(
            RpcRequest(
                method="conversation.delete_staged",
                params={"client_id": client_id, "conversation_id": conversation_id},
            )
        )
        assert deleted.ok
        restorable = dispatcher.dispatch(
            RpcRequest(method="conversation.restorable", params={"client_id": client_id})
        )
        assert restorable.ok and isinstance(restorable.result, list)
        assert [item["id"] for item in restorable.result] == [conversation_id]
        assert dispatcher.dispatch(
            RpcRequest(method="client.disconnect", params={"client_id": client_id})
        ).ok
        assert not dispatcher.dispatch(
            RpcRequest(
                method="conversation.restore",
                params={"client_id": client_id, "conversation_id": conversation_id},
            )
        ).ok
        assert not dispatcher.dispatch(
            RpcRequest(method="client.heartbeat", params={"client_id": client_id})
        ).ok
    finally:
        application.stop()
        application.close()
