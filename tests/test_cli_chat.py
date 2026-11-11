import json

from typer.testing import CliRunner

import sys_eden.cli as cli_module
from sys_eden.cli import app
from sys_eden.core_rpc import CoreRpcError, RpcError


def test_direct_task_reconcile_uses_core_without_starting_a_worker(monkeypatch):
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_rpc(method: str, **params: object) -> dict[str, object]:
        calls.append((method, params))
        return {"id": "TSK-TEST", "state": "failed"}

    monkeypatch.setattr(cli_module, "_rpc_or_exit", fake_rpc)
    result = CliRunner().invoke(
        app, ["task", "reconcile", "TSK-TEST", "--outcome", "failed",
              "--reason", "Reviewed the interrupted fixture"],
    )
    assert result.exit_code == 0
    assert "no worker was restarted" in result.stdout
    assert calls == [(
        "task.reconcile",
        {"task_id": "TSK-TEST", "safe_to_resume": False,
         "message": "Reviewed the interrupted fixture"},
    )]


def test_task_show_explains_recovery_checkpoint_and_no_running_worker(monkeypatch):
    monkeypatch.setattr(cli_module, "_rpc_or_exit", lambda *_args, **_kwargs: {
        "task": {
            "id": "TSK-TEST", "title": "Generated investigation",
            "state": "recovery_required", "objective": "Read-only fixture",
            "active_elapsed_seconds": 1.5, "resume_state": "observing",
            "final_summary": None, "progress": None,
        },
        "events": [], "checkpoints": [{
            "reason": "recovery", "completed_steps": ["Collect fixture"],
            "pending_steps": ["Review fixture"],
        }],
    })
    result = CliRunner().invoke(app, ["task", "show", "TSK-TEST"])
    assert result.exit_code == 0
    assert "no worker is running" in result.stdout
    assert "Review fixture" in result.stdout
    assert "task reconcile" in result.stdout


def test_json_rpc_failure_is_one_structured_envelope(monkeypatch):
    class FailingClient:
        def __init__(self, _settings: object) -> None:
            pass

        def call(self, _method: str, **_params: object) -> object:
            raise CoreRpcError(RpcError(code="request.invalid", message="Generated failure"))

    monkeypatch.setattr(cli_module, "LocalCoreClient", FailingClient)
    monkeypatch.setattr(cli_module, "_settings_or_exit", lambda: object())
    result = CliRunner().invoke(app, ["task", "list", "--json"])
    assert result.exit_code == 1
    envelope = json.loads(result.stdout)
    assert envelope["eden_json"] == 1
    assert envelope["status"] == "error"
    assert envelope["error"]["code"] == "request.invalid"
    assert envelope["data"] is None
    assert result.stderr == ""


def test_json_confirmation_failure_never_prompts_or_prints_non_json():
    result = CliRunner().invoke(app, ["chat", "delete", "CHT-TEST", "--json"])
    assert result.exit_code == 1
    envelope = json.loads(result.stdout)
    assert envelope["status"] == "error"
    assert envelope["error"]["code"] == "confirmation.required"
    assert result.stderr == ""


def test_parser_failure_with_json_flag_is_structured():
    result = CliRunner().invoke(app, ["report", "close", "RPT-TEST", "--json"])
    assert result.exit_code != 0
    envelope = json.loads(result.stdout)
    assert envelope["type"] == "cli.request"
    assert envelope["error"]["code"] == "request.invalid"
    assert result.stderr == ""


def test_direct_report_close_uses_core_and_does_not_compact_chat(monkeypatch):
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_rpc(method: str, **params: object) -> dict[str, object]:
        calls.append((method, params))
        return {"retention_candidates": [], "transcripts_changed": False}

    monkeypatch.setattr(cli_module, "_rpc_or_exit", fake_rpc)
    result = CliRunner().invoke(
        app,
        ["report", "close", "rpt-test", "--status", "failed",
         "--summary", "Generated summary", "--outcome", "Generated outcome"],
    )

    assert result.exit_code == 0
    assert "no conversation transcripts were changed" in result.stdout
    assert calls == [(
        "report.close",
        {"report_id": "rpt-test", "status": "failed",
         "summary": "Generated summary", "outcome": "Generated outcome"},
    )]


def test_retention_review_requires_explicit_confirmation(monkeypatch):
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_rpc(method: str, **params: object) -> list[dict[str, object]]:
        calls.append((method, params))
        return []

    monkeypatch.setattr(cli_module, "_rpc_or_exit", fake_rpc)
    runner = CliRunner()
    rejected = runner.invoke(app, ["report", "review-retention", "rpt-test"])
    accepted = runner.invoke(
        app,
        ["report", "review-retention", "rpt-test", "--confirm-evidence-reviewed",
         "--unique-evidence", "CHT-PROTECTED"],
    )

    assert rejected.exit_code != 0
    assert accepted.exit_code == 0
    assert calls == [(
        "report.review_retention",
        {"report_id": "rpt-test", "evidence_reviewed": True,
         "unique_evidence_ids": ["CHT-PROTECTED"]},
    )]


def test_singular_chat_management_command_does_not_become_a_message(monkeypatch):
    methods: list[str] = []

    def fake_rpc(method: str, **_params):
        methods.append(method)
        return [{"id": "CHT-TEST", "transcript_state": "full", "title": "Test chat"}]

    monkeypatch.setattr(cli_module, "_rpc_or_exit", fake_rpc)

    result = CliRunner().invoke(app, ["chat", "list"])

    assert result.exit_code == 0
    assert "CHT-TEST" in result.stdout
    assert methods == ["conversation.list"]


def test_chat_message_short_form_uses_the_send_command(monkeypatch):
    methods: list[str] = []

    def fake_rpc(method: str, **_params):
        methods.append(method)
        if method == "client.connect":
            return {"id": "CLI-TEST"}
        if method == "conversation.create_temporary":
            return {"conversation": {"id": "TMP-TEST"}}
        if method == "conversation.send":
            return {"response": "Generated fake answer."}
        return {}

    monkeypatch.setattr(cli_module, "_rpc_or_exit", fake_rpc)

    class FakeClient:
        def __init__(self, _settings):
            pass

        def call(self, method, **params):
            return fake_rpc(method, **params)

    monkeypatch.setattr(cli_module, "LocalCoreClient", FakeClient)
    result = CliRunner().invoke(app, ["chat", "Generated question"])

    assert result.exit_code == 0
    assert "Generated fake answer." in result.stdout
    assert methods == [
        "client.connect",
        "conversation.create_temporary",
        "conversation.send",
        "conversation.discard_client_temporary",
        "client.disconnect",
    ]


def test_chat_management_subcommand_help_is_specific_to_subcommand():
    result = CliRunner().invoke(app, ["chat", "compact", "--help"])

    assert result.exit_code == 0
    assert "Usage: eden chat compact" in result.stdout
    assert "--yes" in result.stdout
