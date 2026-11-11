"""Acceptance regressions for the remaining Milestone 5 application paths."""

import asyncio
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from typer.testing import CliRunner

import sys_eden.cli as cli_module
import sys_eden.direct_work as direct_work_module
from sys_eden.cli import app
from sys_eden.cli_design import HomeView, render_home
from sys_eden.config import ModelSettings, Settings
from sys_eden.conversation_models import ConversationRole, ReportLinkRole, TranscriptState
from sys_eden.conversation_repository import ConversationRepository
from sys_eden.conversation_service import ConversationService
from sys_eden.core_application import CoreApplication, CoreLifecycleState
from sys_eden.core_client import CoreUnavailable
from sys_eden.core_presence import record_presence
from sys_eden.core_rpc import CoreRpcDispatcher, CoreRpcError, LocalCoreClient, RpcError, RpcRequest
from sys_eden.diagnostics import (
    DiagnosticAssessment,
    DiagnosticConfidence,
    DiagnosticProgress,
    DiagnosticResult,
)
from sys_eden.direct_work import follow_conversation
from sys_eden.models import FakeModelProvider, ModelRequest, ModelResponse
from sys_eden.progress_views import render_work_status
from sys_eden.report_models import Report
from sys_eden.report_repository import ReportRepository
from sys_eden.storage import Database
from sys_eden.storage_views import render_storage_status
from sys_eden.task_engine import ProgressUpdate, TaskEngine
from sys_eden.task_models import TaskConversationLink, TaskOrigin, TaskState, TechnicalOperation
from sys_eden.task_timing import TaskTimingEstimator


def responder(request: ModelRequest) -> ModelResponse:
    schema = request.output_schema or {}
    title = schema.get("title")
    structured = None
    if title == "MaterialContribution":
        part = json.loads(request.prompt)["conversation_part"]["content"]
        structured = ({"material": True, "summary": "User constraint: keep the fixture offline."}
                      if "offline" in part else {"material": False, "summary": None})
    elif title == "ConversationIntent":
        structured = {"operation": "chat"}
    return ModelResponse(provider="fake", model_id=request.model_id,
                         text="Generated test answer.", structured_data=structured)


@pytest.fixture
def application(tmp_path: Path):
    instance = CoreApplication(
        Settings(data_directory=tmp_path, model=ModelSettings(provider="fake")),
        FakeModelProvider(responder=responder),
    )
    instance.start()
    try:
        yield instance
    finally:
        instance.stop()
        instance.close()


def rpc(application: CoreApplication, method: str, **params: Any) -> Any:
    response = CoreRpcDispatcher(application).dispatch(RpcRequest(method=method, params=params))
    assert response.ok, response.error
    return response.result


def report_and_chat(application: CoreApplication):
    report = application.reports.create(Report(id="RPT-FIXTURE", title="Fixture", objective="Review fixture constraints"))
    conversation = application.conversation_service.create_saved(title="Fixture chat")
    return report, conversation.conversation.id


def test_link_extracts_material_knowledge_and_filler_does_not_replace_it(application):
    report, conversation_id = report_and_chat(application)
    application.conversation_service.append(conversation_id, role=ConversationRole.USER,
                                            content="Keep this generated fixture offline.")
    linked = rpc(application, "conversation.link_report", conversation_id=conversation_id,
                 report_id=report.id, contribution_summary=None)
    assert linked["contribution_summary"] == "User constraint: keep the fixture offline."
    assert linked["contribution_through_sequence"] == 1
    answered = rpc(application, "conversation.send", conversation_id=conversation_id, message="Thanks")
    assert not answered["report_contribution_updated"]
    view = application.report_knowledge.get(report.id)
    assert [item.summary for item in view.supporting_information] == [linked["contribution_summary"]]
    assert "Thanks" not in view.model_dump_json()
    assert len(application.conversations.get(conversation_id).messages) == 3
    assert application.tasks.list() == []


def test_filler_only_link_does_not_create_a_report_summary(application):
    report, conversation_id = report_and_chat(application)
    application.conversation_service.append(conversation_id, role=ConversationRole.USER, content="Hello")
    link = rpc(application, "conversation.link_report", conversation_id=conversation_id, report_id=report.id)
    assert link["contribution_summary"] is None
    assert link["contribution_through_sequence"] == 1
    assert application.report_knowledge.get(report.id).supporting_information == []


def test_failed_contribution_refresh_preserves_knowledge_and_blocks_retention(application):
    report, conversation_id = report_and_chat(application)
    application.conversation_service.append(conversation_id, role=ConversationRole.USER, content="offline")
    rpc(application, "conversation.link_report", conversation_id=conversation_id, report_id=report.id)
    application.conversation_service.append(conversation_id, role=ConversationRole.USER, content="New correction")
    application.contributions.provider = FakeModelProvider()  # Omits the required structured response.
    result = rpc(application, "report.close", report_id=report.id, status="failed",
                 summary="Fixture outcome reviewed", outcome="Unresolved fixture")
    assert result["contribution_warnings"]
    candidates = rpc(application, "report.review_retention", report_id=report.id,
                     evidence_reviewed=True, unique_evidence_ids=[])
    assert not candidates[0]["eligible"]
    assert "latest conversation" in candidates[0]["reason"]
    assert application.conversations.get(conversation_id).conversation.transcript_state is TranscriptState.FULL
    assert application.report_knowledge.get(report.id).supporting_information[0].summary.endswith("offline.")


def test_summary_only_contribution_preserves_temporary_privacy_and_ownership(application):
    report, _ = report_and_chat(application)
    client_id = rpc(application, "client.connect")["id"]
    temporary = application.conversation_service.create_temporary(title="Private fixture", owner_client_id=client_id)
    conversation_id = temporary.conversation.id
    application.conversation_service.append(conversation_id, role=ConversationRole.USER, content="Keep the fixture offline")
    rejected = CoreRpcDispatcher(application).dispatch(RpcRequest(method="conversation.contribute_temporary",
        params={"conversation_id": conversation_id, "report_id": report.id, "client_id": "WRONG"}))
    assert not rejected.ok
    contribution = rpc(application, "conversation.contribute_temporary", conversation_id=conversation_id,
                       report_id=report.id, client_id=client_id)
    assert contribution["material"] and not contribution["transcript_saved"]
    assert application.conversations.links_for_report(report.id) == []
    application.conversation_service.discard_temporary(conversation_id)
    assert application.report_knowledge.get(report.id).supporting_information[0].summary.endswith("offline.")


def test_explicit_relink_is_atomic_and_repeat_link_preserves_contribution(application):
    first, conversation_id = report_and_chat(application)
    second = application.reports.create(Report(id="RPT-SECOND", title="Second fixture", objective="Review related constraints"))
    application.conversation_service.append(conversation_id, role=ConversationRole.USER, content="offline")
    rpc(application, "conversation.link_report", conversation_id=conversation_id, report_id=first.id)
    again = rpc(application, "conversation.link_report", conversation_id=conversation_id, report_id=first.id)
    assert again["contribution_summary"]
    rejected = CoreRpcDispatcher(application).dispatch(RpcRequest(method="conversation.link_report",
        params={"conversation_id": conversation_id, "report_id": "MISSING"}))
    assert not rejected.ok
    assert application.conversations.links_for_conversation(conversation_id)[0].report_id == first.id
    rpc(application, "conversation.link_report", conversation_id=conversation_id, report_id=second.id)
    assert [link.report_id for link in application.conversations.links_for_conversation(conversation_id)] == [second.id]


@pytest.mark.asyncio
async def test_report_context_is_scoped_to_the_selected_chat(application):
    report, conversation_id = report_and_chat(application)
    application.conversation_service.link_saved_conversation(conversation_id, report.id,
        role=ReportLinkRole.PRIMARY, contribution_summary=None)
    unrelated = application.conversation_service.create_saved(title="Unrelated")
    application.conversation_service.append(unrelated.conversation.id, role=ConversationRole.USER,
                                            content="PRIVATE-UNRELATED-RAW-HISTORY")
    prompts = []
    def record(request):
        prompts.append(request.prompt)
        return responder(request)
    application.chat.provider = FakeModelProvider(responder=record)
    await application.chat.send(conversation_id, "Explain the objective")
    ordinary = prompts[-1]
    assert report.objective in ordinary and "PRIMARY_REPORT" in ordinary
    assert "PRIVATE-UNRELATED-RAW-HISTORY" not in "\n".join(prompts)


@pytest.mark.asyncio
async def test_unreachable_core_distinguishes_crash_from_confirmed_stop(tmp_path, monkeypatch):
    client = LocalCoreClient(Settings(data_directory=tmp_path))
    def disconnected(*_args, **_params):
        raise CoreUnavailable("Fixture disconnected")
    monkeypatch.setattr(client, "call", disconnected)
    assert (await client.status()).state is CoreLifecycleState.STOPPED
    record_presence(tmp_path, state="running")
    assert (await client.status()).state is CoreLifecycleState.UNAVAILABLE
    view = render_home(HomeView(core_state=CoreLifecycleState.UNAVAILABLE))
    assert "state is unknown" in view and "Retry" in view
    with pytest.raises(CoreUnavailable, match="could not be confirmed"):
        await client.stop_core()
    record_presence(tmp_path, state="stopped")
    assert (await client.stop_core()).state is CoreLifecycleState.STOPPED


class BoundaryAssessor:
    def __init__(self):
        self.started = Event()
        self.release = Event()
        self.generated = Event()

    async def assess(self, *, concern: str, component: str = "system", snapshot: Any = None,
                     historical_capsules: Any = None, progress: DiagnosticProgress | None = None):
        self.started.set()
        while not self.release.is_set():
            await asyncio.sleep(0.01)
        if progress:
            await progress("generating_assessment", "Reviewing generated fixture evidence.",
                           TechnicalOperation(kind="fixture", summary="Fixture only"))
        self.generated.set()
        return DiagnosticResult(model_id="fake-diagnostic", provider="fake", context_character_count=10,
            assessment=DiagnosticAssessment(summary="Fixture conclusion", explanation="Read-only fixture",
                confidence=DiagnosticConfidence(diagnostic=.5, research=0, execution=0, safety=1,
                                                overall=.5, rationale="Fixture")))


@pytest.mark.parametrize("next_action", ["resume", "cancel", "shutdown"])
def test_live_pause_retains_continuation_and_shutdown_releases_it(application, next_action):
    assessor = BoundaryAssessor()
    application.chat.diagnostics = assessor
    conversation = application.conversation_service.create_saved(title="Pause fixture")
    dispatcher = CoreRpcDispatcher(application)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(dispatcher.dispatch, RpcRequest(method="conversation.send", params={
            "conversation_id": conversation.conversation.id, "message": "Check fixture", "diagnostic_component": "gpu"}))
        try:
            assert assessor.started.wait(3)
            task = application.tasks.tasks_for_conversation(conversation.conversation.id)[0]
            rpc(application, "task.pause", task_id=task.id)
            assessor.release.set()
            deadline = time.monotonic() + 3
            while application.tasks.get(task.id).state is not TaskState.PAUSED and time.monotonic() < deadline:
                time.sleep(.01)
            assert application.tasks.get(task.id).state is TaskState.PAUSED
            assert not assessor.generated.is_set() and not future.done()
            if next_action == "shutdown":
                application.prepare_stop()
            else:
                rpc(application, f"task.{next_action}", task_id=task.id)
            response = future.result(timeout=3)
            if next_action == "resume":
                assert response.ok and assessor.generated.is_set()
                assert application.tasks.get(task.id).state is TaskState.COMPLETED
            else:
                assert not response.ok and not assessor.generated.is_set()
                assert application.tasks.get(task.id).state is (
                    TaskState.PAUSED if next_action == "shutdown" else TaskState.CANCELED)
                if next_action == "shutdown":
                    application.stop()
                    assert application.tasks.checkpoints(task.id)[-1].reason.value == "intentional_shutdown"
        finally:
            assessor.release.set()
            if not future.done():
                application.stop_conversation_work(conversation.conversation.id, hard=True)


class TimingClock:
    def __init__(self):
        self.elapsed = 0.0

    def now(self):
        return datetime(2026, 10, 7, tzinfo=UTC) + timedelta(seconds=self.elapsed)

    def monotonic(self):
        return self.elapsed


def test_estimates_require_comparable_real_history_and_exclude_paused_time(application):
    clock = TimingClock()
    engine = TaskEngine(application.tasks, application.runtime_sessions, clock=clock)
    engine.runtime_session = application.task_engine.runtime_session
    operation = TechnicalOperation(kind="diagnostic_inference", provider="fixture", model_id="fixture-model",
                                   model_loaded=True, context_characters=1000, summary="Fixture operation")
    estimator = TaskTimingEstimator(application.tasks)
    assert estimator.estimate(operation) is None
    for index, duration in enumerate((8, 10, 12)):
        task = engine.create_task(title="Timing fixture", objective="Generated timing in isolated database")
        engine.transition(task.id, TaskState.DIAGNOSING, message="Start fixture", progress=ProgressUpdate(
            current_phase="Reasoning", completed_major_steps=[], technical_operation=operation))
        clock.elapsed += duration / 2
        engine.request_pause(task.id)
        engine.reach_safe_boundary(task.id)
        clock.elapsed += 1000  # Should not contribute to operation duration.
        engine.resume(task.id)
        clock.elapsed += duration / 2
        engine.transition(task.id, TaskState.COMPLETED, message="Fixture complete")
        if index < 2:
            assert estimator.estimate(operation) is None
    estimate = estimator.estimate(operation)
    assert estimate and estimate.minimum_seconds == 6 and estimate.maximum_seconds == 18
    assert estimator.estimate(operation.model_copy(update={"model_loaded": False})) is None
    assert estimator.estimate(operation.model_copy(update={"model_id": "different"})) is None
    assert estimator.estimate(operation.model_copy(update={"context_characters": 10000})) is None
    synthetic = engine.create_task(title="Synthetic", objective="Fixture", origin=TaskOrigin.SYNTHETIC_TEST)
    engine.transition(synthetic.id, TaskState.DIAGNOSING, message="Start fixture", progress=ProgressUpdate(
        current_phase="Reasoning", completed_major_steps=[], technical_operation=operation))
    clock.elapsed += 100
    engine.transition(synthetic.id, TaskState.COMPLETED, message="Fixture complete")
    assert estimator.estimate(operation) == estimate
    overrun = render_work_status({"phase": "reasoning", "detail": "Fixture", "operation_elapsed_seconds": 20,
        "task": {"progress": {"eta_status": "range", "eta_min_seconds": 6, "eta_max_seconds": 18}}})
    assert "exceeded the previous range" in overrun


def test_direct_progress_keeps_lease_alive_and_discloses_one_warning(monkeypatch):
    release = Event()
    calls = []
    ticks = iter(range(0, 200, 4))
    monkeypatch.setattr(direct_work_module.time, "monotonic", lambda: next(ticks))
    polls = 0
    def call(method, **params):
        nonlocal polls
        calls.append((method, params))
        if method == "conversation.send":
            assert release.wait(3)
            return {"response": "Fixture answer"}
        if method == "conversation.work_status":
            polls += 1
            if polls >= 3:
                release.set()
            return {"phase": "collecting_evidence", "detail": "Read-only fixture", "elapsed_seconds": 4,
                    "technical_operation": {"provider": "fixture", "tool": "Typed reader"}}
        if method == "conversation.warnings":
            return [{"id": "WARNING-1", "message": "Fixture next safe boundary"}]
        return {}
    shown = []
    result = follow_conversation(call, client_id="CLI-FIXTURE", conversation_id="TMP-FIXTURE",
        message="Fixture", diagnostic_component=None, details=True, emit=shown.append, poll_seconds=.001)
    assert result["response"] == "Fixture answer"
    assert any(method == "client.heartbeat" and params["client_id"] == "CLI-FIXTURE" for method, params in calls)
    assert sum("WARNING" in line for line in shown) == 1
    assert any("Typed reader" in line and "Elapsed" in line for line in shown)


def test_direct_chat_failure_leaves_one_json_envelope(monkeypatch):
    def setup_rpc(method, **_params):
        return {"id": "CLI-FIXTURE"} if method == "client.connect" else {"conversation": {"id": "TMP-FIXTURE"}}
    class FailingClient:
        def __init__(self, settings):
            pass
        def call(self, method, **params):
            raise CoreRpcError(RpcError(code="model.unavailable", message="Fixture model missing"))
    monkeypatch.setattr(cli_module, "_rpc_or_exit", setup_rpc)
    monkeypatch.setattr(cli_module, "LocalCoreClient", FailingClient)
    result = CliRunner().invoke(app, ["chat", "Fixture request", "--json"])
    assert result.exit_code == 1
    envelope = json.loads(result.stdout)
    assert envelope["error"]["code"] == "model.unavailable"
    assert "Fixture model missing" not in result.stderr


def test_upgrade_from_0005_preserves_transcripts_and_backs_up_database(tmp_path):
    path = tmp_path / "eden.db"
    config = Config()
    config.set_main_option("script_location", str(Path(cli_module.__file__).parent / "migrations"))
    database = Database(path)
    with database.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0005")
    repository = ConversationRepository(database)
    conversations = ConversationService(repository, ReportRepository(database))
    conversation = conversations.create_saved(title="Migration fixture")
    conversations.append(conversation.conversation.id, role=ConversationRole.USER,
                         content="Generated migration evidence")
    database.close()
    reopened = Database(path)
    try:
        reopened.initialize()
        retained = ConversationRepository(reopened).get(conversation.conversation.id)
        assert retained.messages[0].content == "Generated migration evidence"
        assert path.with_suffix(".pre-0005.db").exists()
        with reopened.session() as session:
            assert session.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0006"
            columns = session.execute(text("PRAGMA table_info(report_conversation_links)")).all()
            assert "contribution_through_sequence" in {row[1] for row in columns}
    finally:
        reopened.close()


def test_storage_human_view_shows_budgets_reserve_and_record_counts(application):
    view = render_storage_status(application.storage_status.status(), details=True)
    assert "Budget remaining" in view and "Protected free-space reserve" in view
    assert "Conversations full" in view and "Active report links" in view
    assert "Estimated reclaimable" in view


@pytest.mark.parametrize("summary_only", [False, True])
def test_direct_report_chat_uses_core_and_keeps_persistence_explicit(application, monkeypatch, tmp_path, summary_only):
    report, _ = report_and_chat(application)
    dispatcher = CoreRpcDispatcher(application)
    class ClientAdapter:
        def __init__(self, _settings):
            pass
        def call(self, method, **params):
            response = dispatcher.dispatch(RpcRequest(method=method, params=params))
            if not response.ok:
                assert response.error
                raise CoreRpcError(response.error)
            return response.result
    monkeypatch.setattr(cli_module, "LocalCoreClient", ClientAdapter)
    monkeypatch.setattr(cli_module, "_settings_or_exit", lambda: application.settings)
    output = tmp_path / "fixture-export.json"
    args = ["chat", "Keep the fixture offline", "--report", report.id, "--json", "--output", str(output)]
    if summary_only:
        args.append("--summary-only")
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert json.loads(output.read_text(encoding="utf-8")) == payload
    assert payload["associations"]["report_id"] == report.id
    assert payload["provenance"]["synthetic"]  # This inference used the fake provider.
    links = application.conversations.links_for_report(report.id)
    if summary_only:
        assert payload["data"]["persistence"] == "temporary" and links == []
        assert application.conversation_service.temporary_for_client("CLI-UNKNOWN") == []
        assert application.conversations.standalone_contributions_for_report(report.id)
        assert len(application.conversations.list()) == 1  # Only the original fixture chat.
    else:
        assert payload["data"]["persistence"] == "saved" and len(links) == 1
        assert links[0].contribution_summary and "offline" in links[0].contribution_summary
    refused = CliRunner().invoke(app, args)
    assert refused.exit_code == 1
    assert json.loads(refused.stdout)["error"]["code"] == "export.invalid"
    assert json.loads(output.read_text(encoding="utf-8")) == payload


def test_direct_report_view_and_export_share_tiered_core_contract(application, monkeypatch):
    report, conversation_id = report_and_chat(application)
    application.conversation_service.append(conversation_id, role=ConversationRole.USER,
                                            content="Keep the generated fixture offline")
    rpc(application, "conversation.link_report", conversation_id=conversation_id, report_id=report.id)
    monkeypatch.setattr(cli_module, "_rpc_or_exit", lambda method, **params: rpc(application, method, **params))
    shown = CliRunner().invoke(app, ["report", "show", report.id, "--json"])
    payload = json.loads(shown.stdout)
    assert payload["data_version"] == 2 and payload["associations"]["report_id"] == report.id
    assert payload["data"]["supporting_information"][0]["summary"].endswith("offline.")
    assert payload["data"]["linked_artifacts"][0]["conversation_id"] == conversation_id
    assert "Keep the generated fixture offline" not in shown.stdout
    exported = json.loads(application.report_service.export_json(report.id))
    assert exported["data_version"] == 2 and exported["data"] == payload["data"]


def test_task_list_json_exposes_mixed_synthetic_provenance():
    payload = json.loads(cli_module._json_result("task.list", [
        {"id": "TSK-REAL", "origin": "user"}, {"id": "TST-FIXTURE", "origin": "synthetic_test"}
    ], request_id="fixture"))
    assert not payload["provenance"]["synthetic"]
    assert payload["provenance"]["contains_synthetic"]


def test_saving_a_live_temporary_request_rebinds_work_and_keeps_the_response(application):
    assessor = BoundaryAssessor()
    application.chat.diagnostics = assessor
    client_id = rpc(application, "client.connect")["id"]
    temporary = application.conversation_service.create_temporary(title="Promotion fixture", owner_client_id=client_id)
    original_id = temporary.conversation.id
    dispatcher = CoreRpcDispatcher(application)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(dispatcher.dispatch, RpcRequest(method="conversation.send", params={
            "conversation_id": original_id, "message": "Check the generated fixture",
            "diagnostic_component": "gpu"}))
        try:
            assert assessor.started.wait(3)
            task_id = application.active_conversation_task_id(original_id)
            saved = rpc(application, "conversation.persist", conversation_id=original_id)
            saved_id = saved["conversation"]["id"]
            assert saved_id.startswith("CHT-")
            assert application.active_conversation_task_id(saved_id) == task_id
            assert application.active_conversation_task_id(original_id) is None
            # The client's disconnect cleanup must leave the newly saved request alone.
            rpc(application, "conversation.discard_client_temporary", client_id=client_id, include_working=True)
            rpc(application, "client.disconnect", client_id=client_id)
            assessor.release.set()
            response = future.result(timeout=3)
            assert response.ok and isinstance(response.result, dict)
            assert response.result["conversation_id"] == saved_id
            assert len(application.conversations.get(saved_id).messages) == 2
            assert application.tasks.conversations_for_task(task_id)[0].conversation_id == saved_id
            assert application.tasks.get(task_id).state is TaskState.COMPLETED
            assert application.conversation_service.resolve_id(original_id) == original_id
        finally:
            assessor.release.set()
            if not future.done():
                application.stop_conversation_work(application.conversation_service.resolve_id(original_id), hard=True)


def test_explicit_discard_stops_only_the_owning_clients_work(application):
    assessor = BoundaryAssessor()
    application.chat.diagnostics = assessor
    owner = rpc(application, "client.connect")["id"]
    other = rpc(application, "client.connect")["id"]
    temporary = application.conversation_service.create_temporary(title="Discard fixture", owner_client_id=owner)
    unrelated = application.conversation_service.create_temporary(title="Other client", owner_client_id=other)
    dispatcher = CoreRpcDispatcher(application)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(dispatcher.dispatch, RpcRequest(method="conversation.send", params={
            "conversation_id": temporary.conversation.id, "message": "Fixture request",
            "diagnostic_component": "gpu"}))
        try:
            assert assessor.started.wait(3)
            rpc(application, "conversation.discard_client_temporary", client_id=owner, include_working=True)
            assessor.release.set()
            response = future.result(timeout=3)
            assert not response.ok and response.error is not None and response.error.code == "work.stopped"
            assert not assessor.generated.is_set()
            assert application.conversation_service.get_current(unrelated.conversation.id, owner_client_id=other)
            assert application.status.state is CoreLifecycleState.RUNNING
        finally:
            assessor.release.set()
            if not future.done():
                application.stop_conversation_work(temporary.conversation.id, hard=True)


def test_closed_cli_process_does_not_wait_for_background_rpc_workers():
    script = (
        "from threading import Event\n"
        "from sys_eden.client_workers import ClientRequestWorkers\n"
        "started = Event()\n"
        "release = Event()\n"
        "def wait_for_core():\n"
        "    started.set()\n"
        "    release.wait(30)\n"
        "workers = ClientRequestWorkers()\n"
        "workers.submit(wait_for_core)\n"
        "assert started.wait(3)\n"
        "workers.shutdown(wait=False)\n"
        "print('fixture-client-exited')\n"
    )
    process = subprocess.Popen([sys.executable, "-c", script], stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    try:
        output, error = process.communicate(timeout=5)
        assert process.returncode == 0, error
        assert output.strip() == "fixture-client-exited"
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=3)


def test_reclaimable_storage_requires_current_evidence_review_and_no_unfinished_work(application):
    report, conversation_id = report_and_chat(application)
    application.conversation_service.append(conversation_id, role=ConversationRole.USER,
                                            content="Generated evidence needs retention review")
    application.conversation_service.link_saved_conversation(conversation_id, report.id,
        role=ReportLinkRole.PRIMARY, contribution_summary="Generated constraint and evidence were extracted.")
    rpc(application, "report.close", report_id=report.id, status="failed",
        summary="Fixture evidence retained", outcome="Fixture remains unresolved")
    status = application.storage_status.status()
    assert status.attribution.estimated_reclaimable == 0
    assert status.attribution.protected > 0 and status.largest_consumers[0].protected
    rpc(application, "report.review_retention", report_id=report.id,
        evidence_reviewed=True, unique_evidence_ids=[])
    assert application.storage_status.status().attribution.estimated_reclaimable > 0
    task = application.task_engine.create_task(title="Unfinished fixture", objective="Generated work")
    application.tasks.link_conversation(TaskConversationLink(task_id=task.id, conversation_id=conversation_id,
                                                            linked_at=datetime.now(UTC)))
    assert application.storage_status.status().attribution.estimated_reclaimable == 0
    application.task_engine.request_cancel(task.id)
    assert application.storage_status.status().attribution.estimated_reclaimable > 0
    application.conversation_service.append(conversation_id, role=ConversationRole.USER,
                                            content="New unique evidence after the review")
    assert application.storage_status.status().attribution.estimated_reclaimable == 0
    candidate = application.conversations.retention_candidates(report.id)[0]
    assert not candidate.eligible and "transcript changed" in candidate.reason
