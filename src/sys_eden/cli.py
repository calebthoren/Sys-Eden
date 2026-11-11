import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal, NoReturn

import typer
from pydantic import ValidationError
from pydantic_settings import SettingsError
from typer._click.core import Context as ClickContext
from typer._click.exceptions import ClickException
from typer._click.globals import get_current_context
from typer.core import TyperGroup

from sys_eden.config import Settings, load_settings
from sys_eden.core import Core
from sys_eden.core_application import CoreLifecycleState
from sys_eden.core_client import CoreUnavailable
from sys_eden.core_rpc import CoreRpcError, LocalCoreClient
from sys_eden.direct_work import follow_conversation
from sys_eden.inspection import InspectionResult
from sys_eden.inspection_format import render_human
from sys_eden.interactive_cli import InteractiveCli
from sys_eden.json_contract import (
    EdenJsonEnvelope,
    JsonAssociations,
    JsonError,
    JsonProvenance,
)
from sys_eden.report_knowledge import ReportKnowledgeView, render_report_knowledge
from sys_eden.report_models import (
    ComponentTag,
    PurposeTag,
    ReportPriority,
    ReportSearch,
    ReportState,
    ReportStatus,
    ReportSummary,
)
from sys_eden.report_views import render_report_summary
from sys_eden.settings_view import settings_view
from sys_eden.storage_status import StorageStatus
from sys_eden.storage_views import render_storage_status


class EdenGroup(TyperGroup):
    """Keep parser failures machine-readable when a direct command asks for JSON."""

    def parse_args(self, ctx: ClickContext, args: list[str]) -> list[str]:
        ctx.meta["eden_json_requested"] = "--json" in args
        return super().parse_args(ctx, args)

    def invoke(self, ctx: ClickContext) -> Any:
        try:
            return super().invoke(ctx)
        except ClickException as error:
            if not ctx.meta.get("eden_json_requested"):
                raise
            typer.echo(EdenJsonEnvelope[object](
                type="cli.request", status="error", request_id="cli-request",
                generated_at=datetime.now(UTC),
                error=JsonError(code="request.invalid", message=error.format_message()),
            ).model_dump_json(indent=2))
            raise typer.Exit(error.exit_code) from None


app = typer.Typer(
    name="eden",
    help="Sys Eden - local Windows system intelligence and maintenance.",
    invoke_without_command=True,
    cls=EdenGroup,
)
report_app = typer.Typer(help="Search and inspect durable structured reports.")
model_app = typer.Typer(help="Inspect and use the configured local model provider.")
core_app = typer.Typer(help="Start, stop, or inspect the normal-user Eden Core.")
settings_app = typer.Typer(help="Inspect user-facing Eden settings.")
task_app = typer.Typer(help="Inspect and control durable Eden work.")
class ChatGroup(TyperGroup):
    """Keep ``eden chat <message>`` alongside unambiguous management commands."""

    def parse_args(self, ctx: Any, args: list[str]) -> list[str]:
        if not args or (args[0] not in self.commands and args[0] != "--help"):
            args = ["send", *args]
        return super().parse_args(ctx, args)


chat_app = typer.Typer(
    help="Talk with Eden and manage conversations.",
    cls=ChatGroup,
)
chats_app = typer.Typer(help="Compatibility alias for conversation management.")
storage_app = typer.Typer(help="Inspect Eden storage attribution and recommendations.")
app.add_typer(report_app, name="report")
app.add_typer(model_app, name="model")
app.add_typer(core_app, name="core")
app.add_typer(settings_app, name="settings")
app.add_typer(task_app, name="task")
app.add_typer(chat_app, name="chat")
app.add_typer(chats_app, name="chats")
app.add_typer(storage_app, name="storage")

SUPPORTED_INSPECTION_COMPONENTS = (
    "system",
    "cpu",
    "ram",
    "gpu",
    "storage",
    "network",
    "processes",
    "services",
    "startup",
    "drivers",
    "software",
    "events",
    "crashes",
    "boot",
)


@app.callback()
def main(ctx: typer.Context) -> None:
    """Sys Eden command-line interface."""
    if ctx.invoked_subcommand is not None:
        return
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        typer.echo(ctx.get_help())
        raise typer.Exit(2)
    settings = _settings_or_exit()
    InteractiveCli(settings, LocalCoreClient(settings)).run()


def _core_json(status: object, *, request_id: str) -> str:
    envelope = EdenJsonEnvelope[object](
        type="core.status",
        status="partial" if isinstance(status, dict) and status.get("state") == "unavailable" else "success",
        request_id=request_id,
        generated_at=datetime.now(UTC),
        data=status,
    )
    return envelope.model_dump_json(indent=2)


def _rpc_or_exit(method: str, *, quiet: bool = False, **params: object) -> Any:
    try:
        return LocalCoreClient(_settings_or_exit()).call(method, **params)
    except CoreUnavailable:
        if quiet:
            raise typer.Exit(1) from None
        _command_error(
            method, "core.unavailable",
            "Eden Core is unreachable. Check eden core status; explicitly start it with eden core start.",
            retryable=True,
        )
    except CoreRpcError as error:
        if quiet:
            raise typer.Exit(1) from None
        _command_error(method, error.code, str(error), retryable=error.retryable)


def _json_result(
    type_name: str, data: object, *, request_id: str,
    status: Literal["success", "partial"] = "success",
) -> str:
    associations = JsonAssociations()
    provenance = JsonProvenance()
    warnings: list[str] = []
    def is_synthetic(item: dict[str, Any]) -> bool:
        return (item.get("origin") == "synthetic_test" or item.get("synthetic") is True
                or item.get("generated_test_data") is True or item.get("provider") == "fake")
    if isinstance(data, dict):
        warnings = [str(data[key]) for key in (
            "summary_warning", "report_contribution_warning", "contribution_warning"
        ) if data.get(key)]
        warnings.extend(str(item) for item in data.get("contribution_warnings", []))
        nested_task = data.get("task")
        task = nested_task if isinstance(nested_task, dict) else data
        associations = JsonAssociations(
            conversation_id=data.get("conversation_id"),
            task_id=(data.get("task_id") or task.get("id")
                     if type_name.startswith("task.") else data.get("task_id")),
            report_id=(data.get("report_id") or task.get("active_report_id")
                       or (data.get("report") or {}).get("id")),
        )
        provenance = JsonProvenance(
            synthetic=is_synthetic(task), contains_synthetic=is_synthetic(task),
            source="fake_model_provider" if task.get("provider") == "fake" else None,
        )
    elif isinstance(data, list):
        records = [item for item in data if isinstance(item, dict)]
        flags = [is_synthetic(item) for item in records]
        provenance = JsonProvenance(synthetic=bool(flags) and all(flags), contains_synthetic=any(flags))
    return EdenJsonEnvelope[object](
        type=type_name,
        status="partial" if warnings else status,
        request_id=request_id,
        generated_at=datetime.now(UTC),
        associations=associations,
        provenance=provenance,
        data=data,
        warnings=warnings,
        data_version=2 if type_name == "report.detail" else 1,
    ).model_dump_json(indent=2)


def _json_requested() -> bool:
    context = get_current_context(silent=True)
    while context is not None:
        if context.params.get("json_output") is True:
            return True
        context = context.parent
    return False


def _command_error(
    type_name: str, code: str, message: str, *, retryable: bool = False
) -> NoReturn:
    if _json_requested():
        context = get_current_context(silent=True)
        params = context.params if context is not None else {}
        typer.echo(EdenJsonEnvelope[object](
            type=type_name, status="error", request_id=type_name,
            generated_at=datetime.now(UTC),
            associations=JsonAssociations(
                conversation_id=params.get("conversation_id"),
                task_id=params.get("task_id"),
                report_id=params.get("report_id"),
            ),
            error=JsonError(code=code, message=message, retryable=retryable),
        ).model_dump_json(indent=2))
    else:
        typer.echo(f"Core error [{code}]: {message}" if code.startswith("core.")
                   else message, err=True)
    raise typer.Exit(1)


@core_app.command("status")
def core_status(
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Show whether the separate Eden Core process is running."""
    try:
        status = asyncio.run(LocalCoreClient(_settings_or_exit()).status())
    except (CoreUnavailable, CoreRpcError) as error:
        _command_error("core.status", "core.unavailable", str(error), retryable=True)
    if json_output:
        typer.echo(_core_json(status.model_dump(mode="json"), request_id="core-status"))
    else:
        typer.echo(f"Core is {status.state.value}.")
    if status.state is CoreLifecycleState.UNAVAILABLE:
        if not json_output:
            typer.echo("The runtime state is unknown. Retry eden core status or explicitly use eden core start.")
        raise typer.Exit(1)


@core_app.command("start")
def core_start(
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Start Eden Core; report success if it is already running."""
    client = LocalCoreClient(_settings_or_exit())
    try:
        before = asyncio.run(client.status())
        status = asyncio.run(client.start_core())
    except (CoreUnavailable, CoreRpcError) as error:
        _command_error("core.status", "core.start_failed", str(error), retryable=True)
    if json_output:
        typer.echo(_core_json(status.model_dump(mode="json"), request_id="core-start"))
    elif before.state is CoreLifecycleState.RUNNING:
        typer.echo("Core is already running.")
    else:
        typer.echo("Core started.")


@core_app.command("stop")
def core_stop(
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Gracefully stop Eden Core; report success if it is already stopped."""
    client = LocalCoreClient(_settings_or_exit())
    try:
        before = asyncio.run(client.status())
        status = asyncio.run(client.stop_core())
    except (CoreUnavailable, CoreRpcError) as error:
        _command_error("core.status", "core.stop_failed", str(error), retryable=True)
    if json_output:
        typer.echo(_core_json(status.model_dump(mode="json"), request_id="core-stop"))
    elif before.state is CoreLifecycleState.STOPPED:
        typer.echo("Core is already stopped.")
    else:
        typer.echo("Core stopped cleanly.")


@settings_app.command("show")
def settings_show(
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Show non-secret Eden settings."""
    settings = _settings_or_exit()
    payload = settings_view(settings)
    if json_output:
        typer.echo(
            EdenJsonEnvelope[dict[str, object]](
                type="settings.view",
                status="success",
                request_id="settings-show",
                generated_at=datetime.now(UTC),
                data=payload,
            ).model_dump_json(indent=2)
        )
    else:
        typer.echo(json.dumps(payload, indent=2))


@task_app.command("list")
def task_list(
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """List durable tasks; completed work is retained but not active."""
    payload = _rpc_or_exit("task.list")
    if json_output:
        typer.echo(_json_result("task.list", payload, request_id="task-list"))
        return
    tasks = list(payload)
    if not tasks:
        typer.echo("No durable tasks.")
        return
    for task in tasks:
        synthetic = " — GENERATED TEST TASK" if task["origin"] == "synthetic_test" else ""
        typer.echo(f"{task['id']}  {task['state']}  {task['title']}{synthetic}")


@task_app.command("show")
def task_show(
    task_id: Annotated[str, typer.Argument()],
    details: Annotated[bool, typer.Option("--details")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Show current task state and optionally its technical history."""
    payload = _rpc_or_exit("task.get", task_id=task_id)
    if json_output:
        typer.echo(_json_result("task.detail", payload, request_id="task-show"))
        return
    task = payload["task"]
    lines = [
        f"{task['id']} — {task['title']}",
        f"State: {task['state']}",
        f"Objective: {task['objective']}",
        f"Elapsed: {task['active_elapsed_seconds']:.1f} seconds",
    ]
    if task["state"] == "recovery_required":
        lines.extend([
            "Recovery review required: no worker is running this task.",
            f"Previous state: {task.get('resume_state') or 'unknown'}",
            (
                "Review the checkpoint, then use eden task reconcile <id> "
                "--outcome failed --reason <what you reviewed>."
            ),
        ])
        checkpoints = payload["checkpoints"]
        if checkpoints:
            checkpoint = checkpoints[-1]
            lines.extend([
                f"Last checkpoint: {checkpoint['reason']}",
                "Completed: " + "; ".join(checkpoint["completed_steps"]),
                "Pending: " + "; ".join(checkpoint["pending_steps"]),
            ])
    if task["final_summary"]:
        lines.append(f"Summary: {task['final_summary']}")
    progress = task.get("progress")
    if progress:
        lines.append(f"Current phase: {progress['current_phase']}")
        if progress["current_operation"]:
            lines.append(f"Current operation: {progress['current_operation']}")
        if progress["completed_major_steps"]:
            lines.append("Completed: " + "; ".join(progress["completed_major_steps"]))
        if progress["waiting_reason"]:
            lines.append(f"Waiting: {progress['waiting_reason']}")
        if progress["eta_status"] == "range":
            lines.append(
                f"ETA: {progress['eta_min_seconds']:.0f}–{progress['eta_max_seconds']:.0f} seconds"
            )
        elif progress["eta_status"] == "estimating":
            lines.append("ETA: estimating")
        else:
            lines.append("ETA: unavailable")
    if details:
        lines.append(f"Events: {len(payload['events'])}")
        lines.append(f"Checkpoints: {len(payload['checkpoints'])}")
        lines.extend(f"- {event['message']}" for event in payload["events"])
        if progress and progress["technical_operation"]:
            technical = progress["technical_operation"]
            lines.append(f"Technical operation: {technical['summary']}")
            if technical["provider"]:
                lines.append(f"Provider: {technical['provider']}")
            if technical["tool"]:
                lines.append(f"Tool: {technical['tool']}")
            if technical["sanitized_command"]:
                lines.append(f"Command: {technical['sanitized_command']}")
    typer.echo("\n".join(lines))


def _task_control(task_id: str, action: str, *, json_output: bool) -> None:
    payload = _rpc_or_exit(f"task.{action}", task_id=task_id)
    if json_output:
        typer.echo(_json_result(f"task.{action}", payload, request_id=f"task-{action}"))
    else:
        typer.echo(f"{payload['id']} is {payload['state']}.")


@task_app.command("pause")
def task_pause(
    task_id: Annotated[str, typer.Argument()],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Request pause at the next safe boundary."""
    _task_control(task_id, "pause", json_output=json_output)


@task_app.command("resume")
def task_resume(
    task_id: Annotated[str, typer.Argument()],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Resume a safely paused task; this does not rejoin a conversation."""
    _task_control(task_id, "resume", json_output=json_output)


@task_app.command("cancel")
def task_cancel(
    task_id: Annotated[str, typer.Argument()],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Request cancellation at the next safe boundary."""
    _task_control(task_id, "cancel", json_output=json_output)


@task_app.command("reconcile")
def task_reconcile(
    task_id: Annotated[str, typer.Argument()],
    outcome: Annotated[str, typer.Option("--outcome", help="failed or paused (synthetic only).")],
    reason: Annotated[str, typer.Option("--reason", help="What was checked and concluded.")],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Resolve recovery-required work without falsely restarting a worker."""
    if outcome not in {"failed", "paused"}:
        if json_output:
            _command_error("task.reconciliation", "request.invalid", "outcome must be failed or paused")
        raise typer.BadParameter("outcome must be failed or paused")
    payload = _rpc_or_exit(
        "task.reconcile", task_id=task_id, safe_to_resume=outcome == "paused", message=reason
    )
    if json_output:
        typer.echo(_json_result("task.reconciliation", payload, request_id="task-reconcile"))
    else:
        typer.echo(f"{task_id} reconciled as {payload['state']}; no worker was restarted.")


@chat_app.command("list")
@chats_app.command("list")
def chats_list(
    limit: Annotated[int, typer.Option(min=1, max=1000)] = 100,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """List persistent conversations; temporary chats belong to their live client."""
    payload = _rpc_or_exit("conversation.list", limit=limit)
    if json_output:
        typer.echo(_json_result("conversation.list", payload, request_id="chats-list"))
    elif not payload:
        typer.echo("No saved conversations.")
    else:
        for conversation in payload:
            typer.echo(
                f"{conversation['id']}  {conversation['transcript_state']}  {conversation['title']}"
            )


@chat_app.command("show")
@chats_app.command("show")
def chats_show(
    conversation_id: Annotated[str, typer.Argument()],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Show a saved conversation transcript."""
    payload = _rpc_or_exit("conversation.get", conversation_id=conversation_id)
    if json_output:
        typer.echo(_json_result("conversation.detail", payload, request_id="chats-show"))
        return
    typer.echo(f"{payload['conversation']['id']} — {payload['conversation']['title']}")
    for message in payload["messages"]:
        typer.echo(f"{message['role']}: {message['content']}")


def _set_chat_pin(conversation_id: str, *, pinned: bool, json_output: bool) -> None:
    payload = _rpc_or_exit("conversation.pin", conversation_id=conversation_id, pinned=pinned)
    if json_output:
        typer.echo(_json_result("conversation.pin", payload, request_id="chats-pin"))
    else:
        typer.echo(f"{conversation_id} {'pinned' if pinned else 'unpinned'}.")


@chat_app.command("pin")
@chats_app.command("pin")
def chats_pin(
    conversation_id: Annotated[str, typer.Argument()],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Protect a saved conversation from ordinary retention cleanup."""
    _set_chat_pin(conversation_id, pinned=True, json_output=json_output)


@chat_app.command("unpin")
@chats_app.command("unpin")
def chats_unpin(
    conversation_id: Annotated[str, typer.Argument()],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Remove explicit retention protection from a saved conversation."""
    _set_chat_pin(conversation_id, pinned=False, json_output=json_output)


@chat_app.command("delete")
@chats_app.command("delete")
def chats_delete(
    conversation_id: Annotated[str, typer.Argument()],
    yes: Annotated[bool, typer.Option("--yes", help="Confirm transcript deletion.")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Delete transcript content without silently deleting report knowledge."""
    if not yes:
        if json_output:
            _command_error(
                "conversation.delete", "confirmation.required",
                "Pass --yes to confirm non-interactive transcript deletion.",
            )
        current = _rpc_or_exit("conversation.get", conversation_id=conversation_id)
        typer.echo(
            f"{conversation_id}: delete {len(current['messages'])} retained messages and its "
            "rolling summary. Report knowledge and links remain. "
            "This one-shot command cannot be undone with /restore; deletion is permanent."
        )
        if not typer.confirm("Continue with transcript deletion?", default=False):
            typer.echo("Canceled.")
            return
    payload = _rpc_or_exit("conversation.delete", conversation_id=conversation_id)
    if json_output:
        typer.echo(_json_result("conversation.delete", payload, request_id="chats-delete"))
    else:
        typer.echo(f"Deleted transcript content for {conversation_id}.")


@chat_app.command("compact")
@chats_app.command("compact")
def chats_compact(
    conversation_id: Annotated[str, typer.Argument()],
    yes: Annotated[
        bool,
        typer.Option("--yes", help="Confirm replacement of older transcript detail with a summary."),
    ] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Summarize context and explicitly compact older transcript messages."""
    if not yes:
        if json_output:
            _command_error(
                "conversation.compact", "confirmation.required",
                "Pass --yes to confirm non-interactive transcript compaction.",
            )
        current = _rpc_or_exit("conversation.get", conversation_id=conversation_id)
        count = len(current["messages"])
        removable = max(0, count - 12)
        typer.echo(
            f"{conversation_id}: {count} retained messages; up to {removable} older messages "
            "will be replaced by a rolling summary. Report links remain."
        )
        if not typer.confirm("Continue with transcript compaction?", default=False):
            typer.echo("Canceled.")
            return
    payload = _rpc_or_exit("conversation.compact", conversation_id=conversation_id)
    if json_output:
        typer.echo(_json_result("conversation.compact", payload, request_id="chat-compact"))
    else:
        state = payload["conversation"]["transcript_state"]
        typer.echo(f"{conversation_id} context compacted ({state}).")


@chat_app.command("export")
@chats_app.command("export")
def chats_export(
    conversation_id: Annotated[str, typer.Argument()],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Export a portable JSON copy of one saved conversation and its transcript."""
    payload = _rpc_or_exit("conversation.export", conversation_id=conversation_id)
    serialized = json.dumps(payload, indent=2, sort_keys=True)
    if output is None:
        typer.echo(serialized)
        return
    try:
        with output.open("x", encoding="utf-8") as stream:
            stream.write(serialized)
            stream.write("\n")
    except FileExistsError:
        typer.echo(f"Refusing to overwrite existing export: {output}", err=True)
        raise typer.Exit(1) from None
    typer.echo(f"Exported conversation to {output}")


@storage_app.command("status")
def storage_status_command(
    details: Annotated[bool, typer.Option("--details")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Show read-only storage usage and attribution."""
    payload = _rpc_or_exit("storage.status")
    if json_output:
        typer.echo(_json_result("storage.status", payload, request_id="storage-status"))
        return
    typer.echo(render_storage_status(StorageStatus.model_validate(payload), details=details))


@storage_app.command("recommendations")
def storage_recommendations_command(
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Show read-only cleanup recommendations without changing data."""
    payload = _rpc_or_exit("storage.recommendations")
    if json_output:
        typer.echo(
            _json_result("storage.recommendations", payload, request_id="storage-recommendations")
        )
    elif not payload:
        typer.echo("No storage cleanup recommendations.")
    else:
        for item in payload:
            typer.echo(f"{item['priority']}. {item['action']} — {item['reason']}")


def _storage_category(category: str, *, details: bool, json_output: bool) -> None:
    payload = _rpc_or_exit("storage.category", category=category)
    if json_output:
        typer.echo(
            _json_result(
                f"storage.{category}", payload, request_id=f"storage-{category}"
            )
        )
        return
    typer.echo(f"{category.title()} storage")
    for name, value in payload["attribution"].items():
        typer.echo(f"{name.replace('_', ' ').title()}: {value} bytes")
    if details:
        typer.echo(json.dumps(payload, indent=2))


@storage_app.command("reports")
def storage_reports_command(
    details: Annotated[bool, typer.Option("--details")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Show report storage attribution without changing data."""
    _storage_category("reports", details=details, json_output=json_output)


@storage_app.command("conversations")
def storage_conversations_command(
    details: Annotated[bool, typer.Option("--details")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Show Full/Compact conversation storage and reclaimable estimates."""
    _storage_category("conversations", details=details, json_output=json_output)


@storage_app.command("attachments")
def storage_attachments_command(
    details: Annotated[bool, typer.Option("--details")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Show attachment storage attribution without changing data."""
    _storage_category("attachments", details=details, json_output=json_output)


@app.command()
def health(
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Check Core, storage, configuration, and the local model provider."""
    try:
        settings = load_settings()
    except (ValidationError, SettingsError):
        if json_output:
            typer.echo(EdenJsonEnvelope[object](
                type="health.status", status="error", request_id="health",
                generated_at=datetime.now(UTC),
                data={"configuration": "error"},
                error=JsonError(code="configuration.invalid", message="Configuration is invalid."),
            ).model_dump_json(indent=2))
        else:
            typer.echo("Configuration is invalid.", err=True)
        raise typer.Exit(1) from None
    client = LocalCoreClient(settings)
    try:
        if asyncio.run(client.status()).state is CoreLifecycleState.RUNNING:
            summary = client.call("health")
        else:
            summary = asyncio.run(Core(settings).health()).model_dump(mode="json")
    except (CoreUnavailable, CoreRpcError) as error:
        _command_error("health.status", "core.unavailable", str(error), retryable=True)
    if json_output:
        typer.echo(_json_result(
            "health.status", summary, request_id="health",
            status="success" if summary["core"] == "ok" else "partial",
        ))
    else:
        provider = summary["model_provider"]
        typer.echo(
            "\n".join(
                (
                    f"Core: {summary['core']}",
                    f"Database: {summary['database']}",
                    f"Model provider: {'available' if provider['available'] else 'unavailable'}",
                )
            )
        )
    if summary["core"] != "ok":
        raise typer.Exit(1)


def _validate_inspection_component(component: str) -> str:
    normalized = "system" if component == "os" else component
    if normalized != "all" and normalized not in SUPPORTED_INSPECTION_COMPONENTS:
        if _json_requested():
            _command_error(
                "inspection.result", "request.invalid",
                "Supported components: all, " + ", ".join(SUPPORTED_INSPECTION_COMPONENTS),
            )
        raise typer.BadParameter(
            "Supported components: all, " + ", ".join(SUPPORTED_INSPECTION_COMPONENTS)
        )
    return normalized


@app.command()
def inspect(
    component: Annotated[str, typer.Argument()] = "system",
    details: Annotated[
        bool, typer.Option("--details", help="Show curated diagnostic and inventory fields.")
    ] = False,
    json_output: Annotated[
        bool, typer.Option("--json", help="Emit the structured result as JSON.")
    ] = False,
    only_scope: Annotated[str | None, typer.Option("--only", help="Limit collection to this component.")] = None,
) -> None:
    """Inspect local Windows state without changing the machine."""
    component = _validate_inspection_component(component)
    if only_scope is not None:
        only_scope = _validate_inspection_component(only_scope)
        if only_scope == "all" or (component not in {"system", only_scope}):
            _command_error("inspection.result", "request.invalid",
                           "--only requires one component consistent with the requested area.")
        component = only_scope
    payload = _rpc_or_exit("inspection.inspect", component=component, details=details)
    results = [InspectionResult.model_validate(item) for item in payload]
    if json_output:
        typer.echo(_json_result(
            "inspection.result", payload, request_id="inspect",
            status="success" if all(result.success for result in results) else "partial",
        ))
    else:
        typer.echo("\n\n".join(render_human(result) for result in results))
    if any(not result.success for result in results):
        raise typer.Exit(1)


def _settings_or_exit() -> Settings:
    try:
        return load_settings()
    except (ValidationError, SettingsError):
        _command_error("configuration", "configuration.invalid", "Configuration is invalid.")


@model_app.command("health")
def model_health(
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Check the configured local model runtime without sending a prompt."""
    payload = _rpc_or_exit("model.health")
    if json_output:
        typer.echo(_json_result(
            "model.health", payload, request_id="model-health",
            status="success" if payload["available"] else "partial",
        ))
    else:
        typer.echo(
            f"Model provider {payload['provider']}: "
            f"{'available' if payload['available'] else 'unavailable'}"
        )
    if not payload["available"]:
        raise typer.Exit(1)


@model_app.command("list")
def model_list(json_output: Annotated[bool, typer.Option("--json")] = False) -> None:
    """List models installed in the configured local runtime."""
    models = _rpc_or_exit("model.list")
    if json_output:
        typer.echo(_json_result("model.list", models, request_id="model-list"))
    elif not models:
        typer.echo("No models are installed in the configured local runtime.")
    else:
        for model in models:
            size = (
                f"{model['disk_size_bytes'] / (1024**3):.1f} GiB"
                if model["disk_size_bytes"] is not None
                else "size unavailable"
            )
            state = "loaded" if model["loaded"] else "installed"
            locality = "local" if model["local"] else "non-local (blocked)"
            typer.echo(f"{model['model_id']}  {size}  {state}  {locality}")


@chat_app.command("send")
def chat(
    message: Annotated[
        str | None,
        typer.Argument(help="Question or request for Eden."),
    ] = None,
    save: Annotated[
        bool,
        typer.Option("--save", "--persist", help="Save this conversation for later resumption."),
    ] = False,
    conversation_id: Annotated[str | None, typer.Option("--conversation")] = None,
    report_id: Annotated[str | None, typer.Option("--report")] = None,
    summary_only: Annotated[bool, typer.Option(
        "--summary-only", help="Contribute material knowledge to --report without saving the transcript."
    )] = False,
    inspect_scope: Annotated[str | None, typer.Option("--inspect")] = None,
    only_scope: Annotated[
        str | None,
        typer.Option("--only", help="Use only this read-only inspection area."),
    ] = None,
    details: Annotated[bool, typer.Option("--details", help="Show sanitized live operation details.")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
    output: Annotated[Path | None, typer.Option("--output", help="Write JSON to a new file; requires --json.")] = None,
) -> None:
    """Use the Milestone 5 Core-backed conversation workflow."""
    if output is not None and (not json_output or output.exists()):
        _command_error("conversation.response", "export.invalid",
                       "--output requires --json and a path that does not already exist.")
    if summary_only and (report_id is None or save or conversation_id is not None):
        _command_error("conversation.response", "request.invalid",
                       "--summary-only requires --report and a new temporary chat; omit --save and --conversation.")
    if message is None and json_output:
        _command_error("conversation.response", "request.invalid",
                       "A message is required for non-interactive JSON output.")
    concern = message or typer.prompt("What would you like to ask Eden?")
    requested_scope = only_scope or inspect_scope
    if requested_scope is not None:
        requested_scope = _validate_inspection_component(requested_scope)
        if requested_scope == "all":
            if json_output:
                _command_error("conversation.response", "request.invalid",
                               "chat inspection requires one starting area")
            raise typer.BadParameter("chat inspection requires one starting area")
    client_id = str(_rpc_or_exit("client.connect")["id"])
    active_id = conversation_id
    temporary_id: str | None = None
    try:
        if active_id is None:
            created = _rpc_or_exit(
                "conversation.create_temporary",
                client_id=client_id,
                title=_conversation_title(concern),
            )
            active_id = str(created["conversation"]["id"])
            temporary_id = active_id
        else:
            _rpc_or_exit("conversation.get", conversation_id=active_id, client_id=client_id)
        if report_id is not None:
            _rpc_or_exit("report.show", report_id=report_id)
        if report_id is not None and not summary_only:
            if active_id.startswith("TMP-"):
                persisted = _rpc_or_exit("conversation.persist", conversation_id=active_id)
                active_id = str(persisted["conversation"]["id"])
                temporary_id = None
            _rpc_or_exit("conversation.link_report", conversation_id=active_id,
                         report_id=report_id, role="primary", contribution_summary=None)
        typer.echo(
            (
                f"Collecting read-only {requested_scope} evidence and preparing a local response..."
                if requested_scope
                else "Reviewing the conversation and preparing a local response..."
            ),
            err=True,
        )
        try:
            result = follow_conversation(
                LocalCoreClient(_settings_or_exit()).call,
                client_id=client_id, conversation_id=active_id, message=concern,
                diagnostic_component=requested_scope, details=details,
                emit=lambda line: typer.echo(line, err=True),
            )
        except CoreUnavailable:
            _command_error("conversation.response", "core.unavailable",
                           "The Core connection ended; check its status before retrying.", retryable=True)
        except CoreRpcError as error:
            _command_error("conversation.response", error.code, str(error), retryable=error.retryable)
        if save and active_id.startswith("TMP-"):
            persisted = _rpc_or_exit("conversation.persist", conversation_id=active_id)
            active_id = str(persisted["conversation"]["id"])
            temporary_id = None
        if summary_only:
            _rpc_or_exit("conversation.contribute_temporary", conversation_id=active_id,
                         report_id=report_id, client_id=client_id)
        payload = {
            **result,
            "conversation_id": active_id,
            "persistence": "temporary" if active_id.startswith("TMP-") else "saved",
            "report_id": report_id or result.get("report_id"),
        }
        if json_output:
            serialized = _json_result("conversation.response", payload, request_id="chat")
            if output is not None:
                try:
                    with output.open("x", encoding="utf-8") as stream:
                        stream.write(serialized + "\n")
                except OSError:
                    _command_error("conversation.response", "export.failed", "The JSON export could not be written.")
            typer.echo(serialized)
        else:
            typer.echo(str(result["response"]))
            if result.get("report_contribution_warning"):
                typer.echo(str(result["report_contribution_warning"]), err=True)
            if not active_id.startswith("TMP-"):
                typer.echo(f"\nSaved conversation: {active_id}")
            if summary_only:
                typer.echo("\nMaterial report contribution reviewed; the transcript remains temporary.")
    finally:
        if temporary_id is not None:
            try:
                _rpc_or_exit(
                    "conversation.discard_client_temporary",
                    quiet=True,
                    client_id=client_id,
                    include_working=True,
                )
            except typer.Exit:
                pass
        try:
            _rpc_or_exit("client.disconnect", quiet=True, client_id=client_id)
        except typer.Exit:
            pass


@chat_app.command("stop")
def chat_stop(
    conversation_id: Annotated[str, typer.Argument()],
    hard: Annotated[bool, typer.Option("--hard", help="Request immediate cancellation.")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Stop current work in one saved conversation without stopping Core."""
    payload = _rpc_or_exit("conversation.stop", conversation_id=conversation_id, hard=hard)
    if json_output:
        typer.echo(_json_result("conversation.stop", payload, request_id="chat-stop"))
    else:
        typer.echo("Hard stop requested." if hard else "Safe stop requested.")


@chat_app.command("summarize")
def chat_summarize(
    conversation_id: Annotated[str, typer.Argument()],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Compact model context while retaining the full saved transcript."""
    payload = _rpc_or_exit("conversation.summarize", conversation_id=conversation_id)
    if json_output:
        typer.echo(_json_result("conversation.summary", payload, request_id="chat-summarize"))
    else:
        typer.echo("Conversation context summarized; the transcript was retained.")


@chat_app.command("unlink")
def chat_unlink(
    conversation_id: Annotated[str, typer.Argument()],
    report_id: Annotated[str, typer.Option("--report")],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Remove one report association while retaining the saved transcript."""
    payload = _rpc_or_exit("conversation.unlink_report", conversation_id=conversation_id,
                           report_id=report_id)
    if json_output:
        typer.echo(_json_result("conversation.unlink", payload, request_id="chat-unlink"))
    else:
        typer.echo(f"Unlinked report {report_id}.")


def _conversation_title(message: str) -> str:
    compact = " ".join(message.split())
    return compact if len(compact) <= 80 else compact[:77].rstrip() + "..."


@report_app.command("list")
def report_list(
    query: Annotated[str | None, typer.Option("--query", "-q")] = None,
    state: Annotated[ReportState | None, typer.Option()] = None,
    status: Annotated[ReportStatus | None, typer.Option()] = None,
    priority: Annotated[ReportPriority | None, typer.Option()] = None,
    purpose: Annotated[PurposeTag | None, typer.Option()] = None,
    component: Annotated[ComponentTag | None, typer.Option()] = None,
    chain: Annotated[str | None, typer.Option()] = None,
    limit: Annotated[int, typer.Option(min=1, max=1000)] = 100,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """List reports using metadata-first search and filters."""
    reports = [
        ReportSummary.model_validate(item) for item in _rpc_or_exit(
            "report.list", query=ReportSearch(
                query=query,
                state=state,
                status=status,
                priority=priority,
                purpose_tag=purpose,
                component_tag=component,
                chain_id=chain,
                limit=limit,
            ).model_dump(mode="json")
        )
    ]
    if json_output:
        typer.echo(
            _json_result(
                "report.list", [item.model_dump(mode="json") for item in reports],
                request_id="report-list",
            )
        )
    elif reports:
        typer.echo("\n".join(render_report_summary(item) for item in reports))
    else:
        typer.echo("No reports found.")


@report_app.command("show")
def report_show(
    report_id: Annotated[str, typer.Argument()],
    capsule: Annotated[bool, typer.Option("--capsule")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Show a generated human view, compact AI capsule, or canonical JSON."""
    if capsule and json_output:
        _command_error("report.detail", "request.invalid", "Choose either --capsule or --json")
        raise typer.BadParameter("Choose either --capsule or --json")
    view = ReportKnowledgeView.model_validate(_rpc_or_exit("report.show", report_id=report_id))
    if capsule:
        typer.echo(view.capsule.model_dump_json(indent=2))
    elif json_output:
        typer.echo(
            _json_result(
                "report.detail", view.model_dump(mode="json"), request_id="report-show",
            )
        )
    else:
        typer.echo(render_report_knowledge(view))


@report_app.command("close")
def report_close(
    report_id: Annotated[str, typer.Argument()],
    status: Annotated[ReportStatus, typer.Option("--status")],
    summary: Annotated[str, typer.Option("--summary")],
    outcome: Annotated[str, typer.Option("--outcome")],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Close a reviewed report and list candidates; never compact transcripts."""
    payload = _rpc_or_exit(
        "report.close", report_id=report_id, status=status.value,
        summary=summary, outcome=outcome,
    )
    if json_output:
        typer.echo(_json_result("report.closed", payload, request_id="report-close"))
        return
    typer.echo(f"Closed {report_id}; no conversation transcripts were changed.")
    for candidate in payload["retention_candidates"]:
        state = "Reviewable" if candidate["eligible"] else "Protected"
        typer.echo(f"{state}: {candidate['conversation_id']} — {candidate['reason']}")


@report_app.command("retention")
def report_retention(
    report_id: Annotated[str, typer.Argument()],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """View a closed report's transcript-retention review without changing data."""
    payload = _rpc_or_exit("report.retention_candidates", report_id=report_id)
    if json_output:
        typer.echo(_json_result("report.retention", payload, request_id="report-retention"))
        return
    if not payload:
        typer.echo("No conversation-retention candidates for this report.")
    for candidate in payload:
        state = "Reviewable" if candidate["eligible"] else "Protected"
        typer.echo(f"{state}: {candidate['conversation_id']} — {candidate['reason']}")


@report_app.command("review-retention")
def report_review_retention(
    report_id: Annotated[str, typer.Argument()],
    confirm_evidence_reviewed: Annotated[
        bool, typer.Option("--confirm-evidence-reviewed")
    ] = False,
    unique_evidence: Annotated[list[str] | None, typer.Option("--unique-evidence")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Record explicit evidence review; named transcripts stay protected."""
    if not confirm_evidence_reviewed:
        if json_output:
            _command_error(
                "report.retention_review", "confirmation.required",
                "Review linked transcripts and pass --confirm-evidence-reviewed first.",
            )
        raise typer.BadParameter(
            "Review linked transcripts and pass --confirm-evidence-reviewed first."
        )
    payload = _rpc_or_exit(
        "report.review_retention", report_id=report_id, evidence_reviewed=True,
        unique_evidence_ids=unique_evidence or [],
    )
    if json_output:
        typer.echo(_json_result("report.retention_review", payload, request_id="report-review"))
        return
    for candidate in payload:
        state = "Reviewable" if candidate["eligible"] else "Protected"
        typer.echo(f"{state}: {candidate['conversation_id']} — {candidate['reason']}")
    if not payload:
        typer.echo("No linked conversations need retention review.")


@report_app.command("export")
def report_export(
    report_id: Annotated[str, typer.Argument()],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Export the complete canonical report as portable JSON."""
    payload = str(_rpc_or_exit("report.export", report_id=report_id))
    if output is None:
        typer.echo(payload)
        return
    try:
        with output.open("x", encoding="utf-8") as stream:
            stream.write(payload)
            stream.write("\n")
    except FileExistsError:
        typer.echo(f"Refusing to overwrite existing export: {output}", err=True)
        raise typer.Exit(1) from None
    typer.echo(f"Exported report to {output}")
