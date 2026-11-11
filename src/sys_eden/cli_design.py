"""UI-independent Milestone 5 CLI vocabulary and text presentation."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from sys_eden.core_application import CoreLifecycleState
from sys_eden.task_models import TaskState, TechnicalOperation


class CommandDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    slash: str | None
    direct: str | None
    description: str
    navigation_only: bool = False


class ModifierDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    description: str
    works_with: tuple[str, ...]


COMMANDS = (
    CommandDefinition(slash="/details", direct="eden chat --details",
                      description="Show or hide sanitized details for current conversation work."),
    CommandDefinition(
        slash="/retry", direct="eden core status",
        description="Check the Core connection again without starting it.", navigation_only=True,
    ),
    CommandDefinition(slash="/new", direct="eden chat", description="Open a new temporary chat."),
    CommandDefinition(
        slash="/home", direct=None, description="Return to the home screen.", navigation_only=True
    ),
    CommandDefinition(
        slash="/resume <CHT-or-TMP-id>",
        direct="eden chat --conversation <CHT-id>",
        description="Rejoin a thread; omit the ID to browse conversations.",
    ),
    CommandDefinition(
        slash="/save",
        direct="eden chat --save",
        description="Save the current temporary conversation.",
    ),
    CommandDefinition(
        slash="/compact",
        direct="eden chat summarize <CHT-id>",
        description="Summarize model context; direct compact requires confirmation to prune transcript detail.",
    ),
    CommandDefinition(slash="/pin", direct="eden chat pin <CHT-id>",
                      description="Protect the saved conversation from retention cleanup."),
    CommandDefinition(slash="/unpin", direct="eden chat unpin <CHT-id>",
                      description="Remove explicit conversation retention protection."),
    CommandDefinition(slash="/storage [--details]", direct="eden storage status [--details]",
                      description="Inspect shared storage budgets and attribution without cleanup."),
    CommandDefinition(
        slash="/delete [id]",
        direct="eden chat delete <CHT-id>",
        description="Confirm chat deletion; /restore can undo it until this CLI session closes. Direct deletion is permanent.",
    ),
    CommandDefinition(
        slash="/restore [id]",
        direct=None,
        description="Restore a chat deleted during this CLI session; omit the ID to choose from a list.",
    ),
    CommandDefinition(
        slash="/chats", direct="eden chat list", description="Browse conversations."
    ),
    CommandDefinition(
        slash="/inspect [area]",
        direct='eden chat "Investigate this PC" --inspect <area>',
        description="Run a read-only diagnosis, starting with the requested area.",
    ),
    CommandDefinition(
        slash="/tasks",
        direct="eden task list",
        description="Browse durable work and monitoring tasks.",
    ),
    CommandDefinition(
        slash="/task reconcile <id> failed | <review reason>",
        direct="eden task reconcile <id> --outcome failed --reason <text>",
        description="Close an interrupted attempt after reviewing its checkpoint; no worker restarts.",
    ),
    *(CommandDefinition(slash=f"/task {action} <id>", direct=f"eden task {action} <id>",
                        description=f"{action.capitalize()} durable work at a safe boundary.")
      for action in ("pause", "resume", "cancel")),
    CommandDefinition(
        slash="/monitoring [task-id]",
        direct="eden task show <task-id>",
        description="Browse monitoring tasks or open one by ID.",
    ),
    CommandDefinition(
        slash="/reports", direct="eden report list", description="Browse durable reports."
    ),
    CommandDefinition(
        slash="/report <RPT-id>",
        direct="eden chat --report <RPT-id>",
        description="Save the current chat and link it to a report; use unlink to remove it.",
    ),
    CommandDefinition(
        slash="/report close <id> <status> | <summary> | <outcome>",
        direct="eden report close <id> --status <status> --summary <text> --outcome <text>",
        description="Close a reviewed report and list retention candidates without compacting chat.",
    ),
    CommandDefinition(
        slash="/report retention <id>",
        direct="eden report retention <id>",
        description="View saved transcript-retention candidates for a report.",
    ),
    CommandDefinition(
        slash="/report review-retention <id> confirmed [unique-chat-ids]",
        direct="eden report review-retention <id> --confirm-evidence-reviewed",
        description="Confirm unique-evidence review; list IDs that must remain protected.",
    ),
    CommandDefinition(
        slash="/models", direct="eden model list", description="Browse installed local models."
    ),
    CommandDefinition(
        slash="/health", direct="eden health", description="View Core and provider health."
    ),
    CommandDefinition(
        slash="/stop",
        direct="eden chat stop <CHT-id> [--hard]",
        description="Request a safe stop for work in this conversation.",
        navigation_only=True,
    ),
    CommandDefinition(
        slash="/corestart",
        direct="eden core start",
        description="Start Eden Core; harmless if it is already running.",
    ),
    CommandDefinition(
        slash="/corestop",
        direct="eden core stop",
        description="Gracefully stop Eden Core; harmless if it is already stopped.",
    ),
    CommandDefinition(
        slash="/settings", direct="eden settings show", description="View or change Eden settings."
    ),
    CommandDefinition(
        slash="/help",
        direct="eden --help",
        description="Open this scrollable command and modifier reference.",
    ),
    CommandDefinition(
        slash="/exit", direct=None, description="Close only this CLI client.", navigation_only=True
    ),
)

MODIFIERS = (
    ModifierDefinition(
        name="--json",
        description="Return the stable Eden JSON envelope; direct-command progress uses stderr.",
        works_with=(
            "chat",
            "inspect",
            "task show/list",
            "report show/list",
            "model list/health",
            "storage",
        ),
    ),
    ModifierDefinition(
        name="--details",
        description="Include expanded technical detail without changing the operation.",
        works_with=("chat", "inspect", "task show", "storage status/reports/conversations/attachments"),
    ),
    ModifierDefinition(
        name="--inspect <area>",
        description="Start a chat investigation in this area; Eden may expand when evidence justifies it.",
        works_with=("chat",),
    ),
    ModifierDefinition(
        name="--only <area>",
        description="Make the named inspection area a hard boundary.",
        works_with=("chat", "inspect"),
    ),
    ModifierDefinition(
        name="--output <path>",
        description="Write an export or artifact to a new file instead of stdout.",
        works_with=("report export", "chats export", "chat --json"),
    ),
)


class ConversationPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    activity: str
    detail: str | None = None


class MonitoringPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    state: TaskState = TaskState.MONITORING


class HomeView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    core_state: CoreLifecycleState
    active_conversations: list[ConversationPreview] = Field(default_factory=list)
    monitoring_tasks: list[MonitoringPreview] = Field(default_factory=list)
    preview_limit: int = Field(default=5, ge=3, le=5)


def render_help() -> str:
    lines = ["Eden commands", ""]
    for command in COMMANDS:
        forms = "  |  ".join(value for value in (command.slash, command.direct) if value)
        lines.append(f"{forms}\n    {command.description}")
    lines.extend(["", "Modifiers"])
    for modifier in MODIFIERS:
        supported = ", ".join(modifier.works_with)
        lines.append(f"{modifier.name}\n    {modifier.description}\n    Works with: {supported}")
    lines.extend(["", "Press Esc to return."])
    return "\n".join(lines)


def render_non_stoppable_warning(operation: TechnicalOperation, *, ansi: bool = True) -> str | None:
    if operation.non_stoppable_reason is None:
        return None
    heading = "WARNING - ENTERING A NON-STOPPABLE SEGMENT"
    if ansi:
        heading = f"\x1b[1m\x1b[93m{heading}\x1b[0m"
    else:
        heading = f"!!! {heading} !!!"
    return (
        f"{heading}\n"
        f"{operation.non_stoppable_reason}\n"
        "A stop request will take effect at the next safe boundary."
    )


def render_home(view: HomeView) -> str:
    if view.core_state is CoreLifecycleState.STOPPED:
        return "Eden Core: stopped"
    if view.core_state is CoreLifecycleState.UNAVAILABLE:
        return (
            "Eden Core: unavailable\nThe connection failed; Core's runtime state is unknown.\n"
            "Retry checks the connection. Start Core is an explicit lifecycle request."
        )

    monitoring = view.monitoring_tasks[: view.preview_limit]
    lines = ["Core: running", "", "Monitoring"]
    lines.extend(f"  {item.id}  {item.title}" for item in monitoring)
    if not monitoring:
        lines.append("  None")
    if len(view.monitoring_tasks) > view.preview_limit:
        lines.append(f"  [See all {len(view.monitoring_tasks)}]")
    if any(item.id.startswith("TMP-") for item in view.active_conversations):
        lines.extend(
            [
                "",
                "Warning: temporary conversations remain in this CLI session. Closing it may discard them.",
            ]
        )
    return "\n".join(lines)
