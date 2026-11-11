"""Small interactive client shell built only on Core client operations."""

from __future__ import annotations

import asyncio
import json
import time
from concurrent.futures import Future
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Event, Thread
from typing import Any

from sys_eden.cli_design import (
    COMMANDS,
    ConversationPreview,
    HomeView,
    render_help,
    render_home,
)
from sys_eden.client_workers import ClientRequestWorkers
from sys_eden.config import Settings
from sys_eden.core_application import CoreLifecycleState, CoreRuntimeStatus
from sys_eden.core_rpc import CoreRpcError, LocalCoreClient
from sys_eden.inspection_service import SUPPORTED_INSPECTION_COMPONENTS
from sys_eden.progress_views import render_work_status
from sys_eden.settings_view import settings_view
from sys_eden.storage_status import StorageStatus
from sys_eden.storage_views import render_storage_status
from sys_eden.terminal_navigation import (
    LiveTerminal,
    TerminalButton,
    TerminalCommand,
    TerminalListItem,
    read_chat_bar,
    select_button,
    select_list,
    show_escape_view,
)

STOPPED_BUTTONS = (
    TerminalButton("Start Core", "start-core"),
    TerminalButton("More", "more"),
)

RUNNING_BUTTONS = (
    TerminalButton("Conversations", "conversations"),
    TerminalButton("Monitoring", "monitoring"),
)

THREAD_BUTTONS = (
    TerminalButton("Home", "home"),
    TerminalButton("Conversations", "conversations"),
    TerminalButton("Monitoring", "monitoring"),
)

COMMAND_SUGGESTIONS = tuple(
    TerminalCommand(
        label=command.slash,
        completion=(
            command.slash.split()[0] + (
                " " if not command.slash.split()[1].startswith("[") else ""
            )
            if len(command.slash.split()) > 1
            else command.slash
        ),
        description=command.description,
    )
    for command in COMMANDS
    if command.slash is not None
)


@dataclass
class ConversationNotice:
    """A client-only notice anchored between existing transcript messages."""

    text: str
    after_sequence: int | None = None


class InteractiveCli:
    def __init__(self, settings: Settings, client: LocalCoreClient):
        self.settings = settings
        self.client = client
        self.client_id: str | None = None
        self.current_conversation_id: str | None = None
        self.pending_new_chat = False
        self._heartbeat_stop = Event()
        self._heartbeat_thread: Thread | None = None
        self._redraw_stop = Event()
        self._redraw_thread: Thread | None = None
        self._workers = ClientRequestWorkers(max_workers=4)
        self._work: dict[str, Future[Any]] = {}
        self._stop_requests: set[str] = set()
        self._pending_messages: dict[str, str] = {}
        self._work_details: dict[str, str] = {}
        self._conversation_notices: dict[str, list[ConversationNotice]] = {}
        self._seen_work_warnings: set[str] = set()
        self._home_notices: list[str] = []
        self._show_stopped_once = False
        self._technical_details = False
        self._conversation_aliases: dict[str, str] = {}
        self._activity_history: list[str] = []
        self._deleted_activity: dict[str, str] = {}
        self._terminal = LiveTerminal(fullscreen=True)

    def run(self) -> None:
        self._terminal.enter()
        self._redraw_stop.clear()
        self._redraw_thread = Thread(
            target=self._animate_work,
            name="eden-cli-progress",
            daemon=True,
        )
        self._redraw_thread.start()
        try:
            self._run_screen()
        finally:
            self._redraw_stop.set()
            if self._redraw_thread is not None:
                self._redraw_thread.join(timeout=1)
            self._terminal.exit()

    def _run_screen(self) -> None:
        while True:
            if self._show_stopped_once:
                status = CoreRuntimeStatus(state=CoreLifecycleState.STOPPED)
                self._show_stopped_once = False
            else:
                try:
                    status = asyncio.run(self.client.status())
                except (CoreRpcError, ConnectionError):
                    status = CoreRuntimeStatus(state=CoreLifecycleState.UNAVAILABLE)
            activity = self._conversation_activity()
            home = render_home(
                HomeView(
                    core_state=status.state,
                    active_conversations=activity,
                    preview_limit=self.settings.cli.home_preview_limit,
                )
            )
            if self._home_notices:
                home += f"\n\n{self._home_notices[-1]}"
            core_running = status.state is CoreLifecycleState.RUNNING
            if not core_running:
                self._terminal.set_activity([], redraw=False)
                selection = select_button(
                    (TerminalButton("Retry connection", "retry"), *STOPPED_BUTTONS)
                    if status.state is CoreLifecycleState.UNAVAILABLE else STOPPED_BUTTONS,
                    content=f"{home}\n\nUse arrow keys to select; press Enter to open.",
                    surface=self._terminal,
                )
                if selection is not None and not self._handle_home_selection(
                    selection, core_running=False
                ):
                    return
                continue

            in_thread = self.current_conversation_id is not None
            if in_thread:
                assert self.current_conversation_id is not None
                self._show_thread_feed(self.current_conversation_id, redraw=False)
                buttons = THREAD_BUTTONS
                header_title = self.current_conversation_id
                content = self._conversation_state(self.current_conversation_id)
            else:
                self._show_home_activity(activity, redraw=False)
                buttons = RUNNING_BUTTONS
                header_title = "SYS EDEN"
                content = home
            result = read_chat_bar(
                buttons,
                context="",
                content=content,
                surface=self._terminal,
                header_title=header_title,
                command_suggestions=self._command_suggestions(),
            )
            if result.canceled:
                if result.cancel_key == "ctrl_c":
                    self._ctrl_c()
                elif self.current_conversation_id is not None:
                    self.current_conversation_id = None
                continue
            if result.message is not None:
                if not self._handle(result.message, core_running=True):
                    return
            elif result.action is not None and not self._handle_home_selection(
                result.action, core_running=True
            ):
                return

    def _handle_home_selection(self, selection: str, *, core_running: bool) -> bool:
        if selection == "retry":
            return self._handle("/retry", core_running=core_running)
        if selection == "start-core":
            return self._handle("/corestart", core_running=core_running)
        if selection == "help":
            return self._handle("/help", core_running=core_running)
        if selection == "settings":
            return self._handle("/settings", core_running=core_running)
        if selection == "exit-client":
            return self._handle("/exit", core_running=core_running)
        if selection == "home":
            self.current_conversation_id = None
            return True
        if selection == "conversations":
            self._show_saved_conversations()
            return True
        if selection == "monitoring":
            self._show_monitoring_tasks()
            return True
        if selection == "more":
            return self._more_menu(core_running=core_running)
        return True

    def _show_saved_conversations(self) -> None:
        try:
            conversations = self._available_conversations()
        except (CoreRpcError, ConnectionError) as error:
            self._notice(f"Could not load conversations: {error}")
            return
        if not conversations:
            show_escape_view("Conversations\n\nNo conversations.", surface=self._terminal)
            return
        selected = select_list(
            tuple(
                TerminalListItem(
                    label=f"{conversation['id']}  {conversation['title']}",
                    description=str(conversation["transcript_state"]),
                    action=str(conversation["id"]),
                )
                for conversation in conversations
            ),
            title="Conversations",
            surface=self._terminal,
        )
        if selected is not None:
            self.current_conversation_id = selected
            self._record_activity(selected)

    def _available_conversations(self) -> list[dict[str, Any]]:
        conversations = list(self.client.call("conversation.list", limit=100))
        if self.client_id is not None:
            temporary = self.client.call(
                "conversation.client_temporary", client_id=self.client_id
            )
            conversations.extend(item["conversation"] for item in temporary)
        return sorted(
            (
                item for item in conversations
                if item["transcript_state"] != "deleted"
            ),
            key=lambda item: str(item.get("updated_at", "")),
            reverse=True,
        )

    def _command_suggestions(self) -> tuple[TerminalCommand, ...]:
        """Supply ID completions from Core, newest first within each command."""
        suggestions = list(COMMAND_SUGGESTIONS)
        try:
            conversations = self._available_conversations()
        except (CoreRpcError, ConnectionError):
            conversations = []
        for command in ("/resume", "/delete"):
            suggestions.extend(
                TerminalCommand(
                    label=f"{command} {item['id']}",
                    completion=f"{command} {item['id']}",
                    description=str(item["title"]),
                )
                for item in conversations
            )
        if self.client_id is not None:
            try:
                restorable = self.client.call(
                    "conversation.restorable", client_id=self.client_id
                )
            except (CoreRpcError, ConnectionError):
                restorable = []
            suggestions.extend(
                TerminalCommand(
                    label=f"/restore {item['id']}",
                    completion=f"/restore {item['id']}",
                    description=str(item["title"]),
                )
                for item in reversed(restorable)
            )
        try:
            tasks = self.client.call("task.list")
        except (CoreRpcError, ConnectionError):
            tasks = []
        suggestions.extend(
            TerminalCommand(
                label=f"/monitoring {task['id']}",
                completion=f"/monitoring {task['id']}",
                description=str(task["title"]),
            )
            for task in sorted(
                (item for item in tasks if item["state"] == "monitoring"),
                key=lambda item: str(item.get("updated_at", "")),
                reverse=True,
            )
        )
        return tuple(suggestions)

    def _show_tasks(self) -> None:
        self._show_task_list(monitoring_only=False)

    def _show_monitoring_tasks(self, task_id: str | None = None) -> None:
        self._show_task_list(monitoring_only=True, task_id=task_id)

    def _show_task_list(
        self, *, monitoring_only: bool, task_id: str | None = None
    ) -> None:
        try:
            tasks = self.client.call("task.list")
        except (CoreRpcError, ConnectionError) as error:
            self._notice(f"Could not load tasks: {error}")
            return
        visible = sorted(
            (task for task in tasks if not monitoring_only or task["state"] == "monitoring"),
            key=lambda item: str(item.get("updated_at", "")),
            reverse=True,
        )
        title = "Monitoring" if monitoring_only else "Tasks"
        if not visible:
            show_escape_view(f"{title}\n\nNo {title.lower()}.", surface=self._terminal)
            return
        selected = task_id or select_list(
            tuple(
                TerminalListItem(
                    label=f"{task['id']}  {task['title']}",
                    description=str(task["state"]),
                    action=str(task["id"]),
                )
                for task in visible
            ),
            title=title,
            surface=self._terminal,
        )
        if selected is None:
            return
        if not any(task["id"] == selected for task in visible):
            self._notice(f"Task {selected} was not found.")
            return
        detail = self.client.call("task.get", task_id=selected)
        task = detail["task"]
        if task["state"] == "recovery_required":
            checkpoints = detail.get("checkpoints", [])
            last_checkpoint = checkpoints[-1] if checkpoints else None
            lines = [
                f"{task['id']} — recovery review required",
                "",
                "The previous Core session ended before this work finished.",
                "No worker is currently running this task.",
                f"Previous state: {task.get('resume_state') or 'unknown'}",
                "",
                "Review the last checkpoint, then mark this attempt failed.",
                "Start a new request if the investigation is still needed.",
                f"/task reconcile {task['id']} failed | <what you reviewed>",
            ]
            if last_checkpoint is not None:
                lines.extend([
                    "",
                    "Last checkpoint:",
                    f"  Reason: {last_checkpoint['reason']}",
                    "  Completed: " + ", ".join(last_checkpoint['completed_steps']),
                    "  Pending: " + ", ".join(last_checkpoint['pending_steps']),
                ])
            if task["origin"] == "synthetic_test":
                lines.append("Synthetic fixtures may also be reconciled as paused.")
            show_escape_view("\n".join(lines), surface=self._terminal)
            return
        conversations = list(detail.get("conversations", []))
        if conversations:
            self.current_conversation_id = str(conversations[0]["conversation_id"])
            self._record_activity(self.current_conversation_id)
            return
        progress = task.get("progress") or {}
        show_escape_view(
            "\n".join(
                (
                    f"{task['id']} — {task['title']}",
                    "",
                    f"State: {task['state']}",
                    f"Objective: {task['objective']}",
                    f"Current phase: {progress.get('current_phase', 'Unavailable')}",
                )
            ),
            surface=self._terminal,
        )

    def _more_menu(self, *, core_running: bool) -> bool:
        choice = select_button(
            (
                TerminalButton("Settings", "settings"),
                TerminalButton("Help", "help"),
                TerminalButton("Exit", "exit"),
            ),
            content="More",
            surface=self._terminal,
        )
        if choice is None:
            return True
        command = {
            "settings": "/settings",
            "help": "/help",
            "exit": "/exit",
        }[choice]
        return self._handle(command, core_running=core_running)

    def _handle(self, value: str, *, core_running: bool) -> bool:
        if not value:
            return True
        if value in {"/retry", "retry"}:
            self._notice("Checking the Core connection again.")
            return True
        if value == "/details":
            self._technical_details = not self._technical_details
            self._notice("Operation details shown." if self._technical_details else "Operation details hidden.")
            return True
        if value in {"/exit", "exit"}:
            return not self._exit()
        if value in {"/help", "help"}:
            show_escape_view(
                render_help(),
                surface=self._terminal,
            )
            return True
        if value in {"/settings", "settings", "3"}:
            show_escape_view(
                "Eden Settings\n\n" + json.dumps(settings_view(self.settings), indent=2),
                surface=self._terminal,
            )
            return True
        if value in {"/corestart", "start", "1"}:
            try:
                before = asyncio.run(self.client.status())
                asyncio.run(self.client.start_core())
            except (CoreRpcError, ConnectionError) as error:
                self._notice(f"Could not start Core: {error}")
                return True
            self._notice(
                "Core is already running."
                if before.state is CoreLifecycleState.RUNNING
                else "Core started."
            )
            return True
        if value in {"/corestop", "stop-core"}:
            try:
                before = asyncio.run(self.client.status())
            except (CoreRpcError, ConnectionError) as error:
                self._notice(f"Could not confirm Core state; stop canceled: {error}")
                return True
            if before.state is CoreLifecycleState.RUNNING:
                choice = select_button(
                    (
                        TerminalButton("Cancel", "cancel"),
                        TerminalButton("Stop Core", "stop-core"),
                    ),
                    content=(
                        "Stop Eden Core?\n\n"
                        "The Eden CLI will stay open on the Core-stopped page. "
                        "Active work may finish or pause during shutdown. "
                        "Unsaved temporary chats and this session's /restore undo copies "
                        "will be lost; saved chats and reports remain.\n\n"
                        "Save anything you want to keep before continuing."
                    ),
                    surface=self._terminal,
                )
                if choice != "stop-core":
                    self._notice("Core stop canceled.")
                    return True
                try:
                    asyncio.run(self.client.stop_core())
                except CoreRpcError as error:
                    self._notice(f"Could not stop Core: {error}")
                    return True
                except ConnectionError:
                    # The host can close its RPC endpoint after accepting stop but
                    # before the response reaches this client. Verify the outcome.
                    try:
                        after = asyncio.run(self.client.status())
                    except (CoreRpcError, ConnectionError):
                        after = CoreRuntimeStatus(state=CoreLifecycleState.UNAVAILABLE)
                    if after.state is CoreLifecycleState.UNAVAILABLE:
                        self._notice("The stop result is unknown because Core is unreachable. Retry the connection.")
                        return True
                    if after.state is CoreLifecycleState.RUNNING:
                        self._notice("Core is still running; stop was not confirmed.")
                        return True
            self._heartbeat_stop.set()
            if self._heartbeat_thread is not None:
                self._heartbeat_thread.join(timeout=1)
            self.client_id = None
            self.current_conversation_id = None
            self._show_stopped_once = True
            if before.state is CoreLifecycleState.STOPPED:
                self._notice("Core is already stopped.")
            else:
                self._notice("Core stopped. The Eden client is still open.")
            return True
        if value == "/more" and not core_running:
            return self._more_menu(core_running=core_running)
        if not core_running:
            self._notice("Core is stopped. Choose Start Core or More.")
            return True
        if value == "/home":
            self.current_conversation_id = None
            return True
        if value == "/new":
            self.current_conversation_id = None
            self.pending_new_chat = True
            return True
        if value == "/resume":
            self._show_saved_conversations()
            return True
        if value.startswith("/resume "):
            conversation_id = value.removeprefix("/resume ").strip().upper()
            if not conversation_id:
                self._notice("Usage: /resume <conversation-id>")
                return True
            client_id = self._connect()
            try:
                aggregate = self.client.call(
                    "conversation.get",
                    conversation_id=conversation_id,
                    client_id=client_id,
                )
            except (CoreRpcError, ConnectionError) as error:
                self._notice(f"Could not open {conversation_id}: {error}")
                return True
            if aggregate["conversation"].get("transcript_state") == "deleted":
                self._notice(f"{conversation_id} is deleted. Use /restore in the original CLI session.")
                return True
            self.current_conversation_id = conversation_id
            self._record_activity(conversation_id)
            return True
        if value in {"/chats", "/chat"}:
            self._show_saved_conversations()
            return True
        if value == "/delete" or value.startswith("/delete "):
            self._delete_chat(value.removeprefix("/delete").strip().upper())
            return True
        if value == "/restore" or value.startswith("/restore "):
            self._restore_chat(value.removeprefix("/restore").strip().upper())
            return True
        if value == "/tasks":
            self._show_tasks()
            return True
        if value.startswith("/task ") and not value.startswith("/task reconcile "):
            parts = value.split()
            if len(parts) != 3 or parts[1] not in {"pause", "resume", "cancel"}:
                self._notice("Usage: /task pause|resume|cancel <task-id>")
                return True
            try:
                result = self.client.call(f"task.{parts[1]}", task_id=parts[2].upper())
            except (CoreRpcError, ConnectionError) as error:
                self._notice(f"Could not {parts[1]} task: {error}")
            else:
                self._notice(f"{result['id']}: {result['state']}")
            return True
        if value in {"/pin", "/unpin"}:
            if self.current_conversation_id is None or self.current_conversation_id.startswith("TMP-"):
                self._notice("Save the current conversation before changing retention protection.")
                return True
            try:
                self.client.call("conversation.pin", conversation_id=self.current_conversation_id,
                                 pinned=value == "/pin")
            except (CoreRpcError, ConnectionError) as error:
                self._notice(f"Could not change retention protection: {error}")
                return True
            self._notice("Conversation pinned." if value == "/pin" else "Conversation unpinned.")
            return True
        if value == "/storage" or value == "/storage --details":
            try:
                status = StorageStatus.model_validate(self.client.call("storage.status"))
            except (CoreRpcError, ConnectionError) as error:
                self._notice(f"Could not inspect storage: {error}")
            else:
                show_escape_view(render_storage_status(status, details=value.endswith("--details")),
                                 surface=self._terminal)
            return True
        if value.startswith("/task reconcile "):
            parts = value.removeprefix("/task reconcile ").split("|", 1)
            heading = parts[0].strip().split()
            if len(parts) != 2 or len(heading) != 2 or heading[1] not in {"failed", "paused"}:
                self._notice("Usage: /task reconcile <id> failed | <review reason>")
                return True
            try:
                result = self.client.call(
                    "task.reconcile", task_id=heading[0].upper(),
                    safe_to_resume=heading[1] == "paused", message=parts[1].strip(),
                )
            except (CoreRpcError, ConnectionError) as error:
                self._notice(f"Could not reconcile task: {error}")
            else:
                self._notice(
                    f"{result['id']} reconciled as {result['state']}; no worker restarted."
                )
            return True
        if value == "/monitoring":
            self._show_monitoring_tasks()
            return True
        if value.startswith("/monitoring "):
            task_id = value.removeprefix("/monitoring ").strip().upper()
            self._show_monitoring_tasks(task_id or None)
            return True
        if value == "/save":
            self._save_current()
            return True
        if value == "/compact":
            self._compact_current()
            return True
        if value == "/reports":
            self._show_reports()
            return True
        if value == "/models":
            self._show_models()
            return True
        if value == "/health":
            self._show_health()
            return True
        if value.startswith("/report close "):
            self._close_report_command(value.removeprefix("/report close ").strip())
            return True
        if value.startswith("/report retention "):
            self._show_report_retention(value.removeprefix("/report retention ").strip())
            return True
        if value.startswith("/report review-retention "):
            self._review_report_retention_command(
                value.removeprefix("/report review-retention ").strip()
            )
            return True
        if value.startswith("/report "):
            self._report_command(value.removeprefix("/report ").strip())
            return True
        if value == "/stop":
            self._request_stop()
            return True
        if value == "/inspect" or value.startswith("/inspect "):
            component = value.removeprefix("/inspect").strip() or "system"
            component = "system" if component == "os" else component
            if component not in SUPPORTED_INSPECTION_COMPONENTS:
                self._notice("Usage: /inspect [system|cpu|memory|disk|network|gpu]")
                return True
            self._send_message(value, diagnostic_component=component)
            return True
        if value.startswith("/"):
            self._notice("Unknown command. Run /help to see every command.")
            return True
        self._send_message(value)
        return True

    def _save_current(self) -> None:
        conversation_id = self.current_conversation_id
        if conversation_id is None:
            self._notice("There is no current conversation to save.")
            return
        if not conversation_id.startswith("TMP-"):
            self._notice(f"{conversation_id} is already saved.")
            return
        try:
            persisted = self.client.call(
                "conversation.persist", conversation_id=conversation_id
            )
        except (CoreRpcError, ConnectionError) as error:
            self._notice(f"Could not save this conversation: {error}")
            return
        saved_id = str(persisted["conversation"]["id"])
        self._conversation_aliases[conversation_id] = saved_id
        if conversation_id in self._stop_requests:
            self._stop_requests.discard(conversation_id)
            self._stop_requests.add(saved_id)
        self.current_conversation_id = saved_id
        if conversation_id in self._activity_history:
            self._activity_history.remove(conversation_id)
        self._record_activity(saved_id)
        if conversation_id in self._work:
            self._work[saved_id] = self._work.pop(conversation_id)
        if conversation_id in self._pending_messages:
            self._pending_messages[saved_id] = self._pending_messages.pop(conversation_id)
        if conversation_id in self._work_details:
            self._work_details[saved_id] = self._work_details.pop(conversation_id)
        if conversation_id in self._conversation_notices:
            self._conversation_notices[saved_id] = self._conversation_notices.pop(
                conversation_id
            )
        self._notice(f"Conversation saved as {saved_id}.")

    def _delete_chat(self, requested_id: str) -> None:
        conversation_id = requested_id or self.current_conversation_id
        if conversation_id is None:
            self._notice("Open a conversation or use /delete <conversation-id>.")
            return
        future = self._work.get(conversation_id)
        if future is not None and not future.done():
            self._notice("Wait for this conversation's response before deleting it.")
            return
        warning = (
            f"Delete {conversation_id}? Its transcript will disappear now.\n\n"
            "You can restore it with /restore until this Eden CLI session closes. "
            "After that, the chat is deleted for good. Report knowledge and links remain."
        )
        choice = select_button(
            (TerminalButton("Cancel", "cancel"), TerminalButton("Delete chat", "delete")),
            content=warning,
            surface=self._terminal,
        )
        if choice != "delete":
            return
        try:
            client_id = self._connect()
            deleted = self.client.call(
                "conversation.delete_staged",
                conversation_id=conversation_id,
                client_id=client_id,
            )
        except (CoreRpcError, ConnectionError) as error:
            if "Unknown Core method: conversation.delete_staged" in str(error):
                self._notice(
                    "Nothing was deleted. Eden Core is running older code. "
                    "Finish any active work, then run /corestop and /corestart before retrying /delete."
                )
                return
            self._notice(f"Could not delete {conversation_id}: {error}")
            return
        if self.current_conversation_id == conversation_id:
            self.current_conversation_id = None
        self._work.pop(conversation_id, None)
        self._pending_messages.pop(conversation_id, None)
        self._work_details.pop(conversation_id, None)
        self._conversation_notices.pop(conversation_id, None)
        self._deleted_activity[conversation_id] = str(deleted["title"])
        self._record_activity(conversation_id)
        self._notice(f"Deleted {conversation_id}. Use /restore before closing this CLI session.")

    def _restore_chat(self, requested_id: str) -> None:
        try:
            client_id = self._connect()
            if requested_id:
                conversation_id = requested_id
            else:
                restorable = self.client.call(
                    "conversation.restorable", client_id=client_id
                )
                if not restorable:
                    self._notice("No chats can be restored in this CLI session.")
                    return
                selected = select_list(
                    tuple(
                        TerminalListItem(
                            label=f"{item['id']}  {item['title']}",
                            description="Deleted in this CLI session",
                            action=str(item["id"]),
                        )
                        for item in reversed(restorable)
                    ),
                    title="Restore a chat",
                    surface=self._terminal,
                )
                if selected is None:
                    return
                conversation_id = selected
            self.client.call(
                "conversation.restore", conversation_id=conversation_id, client_id=client_id
            )
        except (CoreRpcError, ConnectionError) as error:
            if "Unknown Core method: conversation.restore" in str(error):
                self._notice(
                    "Eden Core is running older code. Run /corestop and /corestart "
                    "before retrying /restore."
                )
                return
            self._notice(f"Could not restore chat: {error}")
            return
        self.current_conversation_id = conversation_id
        self._deleted_activity.pop(conversation_id, None)
        self._record_activity(conversation_id)
        self._notice(f"Restored {conversation_id}.")

    def _compact_current(self) -> None:
        conversation_id = self.current_conversation_id
        if conversation_id is None:
            self._notice("There is no current conversation to compact.")
            return
        future = self._work.get(conversation_id)
        if future is not None and not future.done():
            self._notice("Wait for the current response before compacting this conversation.")
            return
        self._work_details[conversation_id] = (
            "Summarizing conversation context; the full transcript will be retained."
        )
        try:
            payload = self.client.call(
                "conversation.summarize", conversation_id=conversation_id
            )
        except (CoreRpcError, ConnectionError) as error:
            self._notice(f"Could not compact this conversation: {error}")
            return
        finally:
            self._work_details.pop(conversation_id, None)
        self._notice(
            f"Conversation context summarized through message {payload['through_sequence']}; "
            "the transcript was not deleted."
        )

    def _show_reports(self) -> None:
        try:
            reports = self.client.call("report.list", query={"limit": 100})
        except (CoreRpcError, ConnectionError) as error:
            self._notice(f"Could not load reports: {error}")
            return
        if not reports:
            show_escape_view("Reports\n\nNo reports.", surface=self._terminal)
            return
        selected = select_list(
            tuple(
                TerminalListItem(
                    label=f"{report['id']}  {report['title']}",
                    description=f"{report['state']} / {report['status']}",
                    action=str(report["id"]),
                )
                for report in reports
            ),
            title="Reports",
            surface=self._terminal,
        )
        if selected is None:
            return
        detail = self.client.call("report.show", report_id=selected)
        report = detail["report"]
        show_escape_view(
            "\n".join(
                (
                    f"{report['id']} — {report['title']}",
                    "",
                    f"State: {report['state']}",
                    f"Status: {report['status']}",
                    str(report.get("summary") or report["objective"]),
                )
            ),
            surface=self._terminal,
        )

    def _show_models(self) -> None:
        try:
            models = self.client.call("model.list")
        except (CoreRpcError, ConnectionError) as error:
            self._notice(f"Could not load models: {error}")
            return
        lines = ["Models", ""]
        lines.extend(
            f"{model['model_id']}  {'loaded' if model['loaded'] else 'installed'}"
            for model in models
        )
        if not models:
            lines.append("No local models installed.")
        show_escape_view("\n".join(lines), surface=self._terminal)

    def _show_health(self) -> None:
        try:
            health = self.client.call("health")
        except (CoreRpcError, ConnectionError) as error:
            self._notice(f"Could not load health: {error}")
            return
        provider = health["model_provider"]
        show_escape_view(
            "\n".join(
                (
                    "Eden Health",
                    "",
                    f"Core: {health['core']}",
                    f"Database: {health['database']}",
                    f"Model provider: {'available' if provider['available'] else 'unavailable'}",
                )
            ),
            surface=self._terminal,
        )

    def _close_report_command(self, argument: str) -> None:
        parts = [part.strip() for part in argument.split("|", 2)]
        heading = parts[0].split() if parts else []
        if len(parts) != 3 or len(heading) != 2 or not parts[1] or not parts[2]:
            self._notice(
                "Usage: /report close <id> <resolved|failed|canceled|archived> "
                "| <summary> | <outcome>"
            )
            return
        report_id, status = heading
        try:
            payload = self.client.call(
                "report.close", report_id=report_id, status=status.lower(),
                summary=parts[1], outcome=parts[2],
            )
        except (CoreRpcError, ConnectionError) as error:
            self._notice(f"Could not close report: {error}")
            return
        lines = [f"Closed report {report_id}.", "No transcripts were changed.", ""]
        for item in payload["retention_candidates"]:
            state = "Reviewable" if item["eligible"] else "Protected"
            lines.append(f"{state}: {item['conversation_id']} — {item['reason']}")
        if not payload["retention_candidates"]:
            lines.append("No linked conversations need retention review.")
        show_escape_view("\n".join(lines), surface=self._terminal)

    def _show_report_retention(self, report_id: str) -> None:
        if not report_id:
            self._notice("Usage: /report retention <id>")
            return
        try:
            candidates = self.client.call("report.retention_candidates", report_id=report_id)
        except (CoreRpcError, ConnectionError) as error:
            self._notice(f"Could not load report retention review: {error}")
            return
        lines = [f"Retention review for {report_id}", ""]
        for item in candidates:
            state = "Reviewable" if item["eligible"] else "Protected"
            lines.append(f"{state}: {item['conversation_id']} — {item['reason']}")
        if not candidates:
            lines.append("No conversation-retention candidates.")
        show_escape_view("\n".join(lines), surface=self._terminal)

    def _review_report_retention_command(self, argument: str) -> None:
        parts = argument.split()
        if len(parts) < 2 or parts[1].lower() != "confirmed":
            self._notice(
                "Usage: /report review-retention <id> confirmed [unique-evidence-chat-ids...] "
                "(review linked transcripts first)"
            )
            return
        report_id = parts[0]
        try:
            candidates = self.client.call(
                "report.review_retention", report_id=report_id,
                evidence_reviewed=True, unique_evidence_ids=parts[2:],
            )
        except (CoreRpcError, ConnectionError) as error:
            self._notice(f"Could not record retention review: {error}")
            return
        lines = [f"Evidence review recorded for {report_id}.", "No transcripts were changed.", ""]
        for item in candidates:
            state = "Reviewable" if item["eligible"] else "Protected"
            lines.append(f"{state}: {item['conversation_id']} — {item['reason']}")
        if not candidates:
            lines.append("No linked conversations need retention review.")
        show_escape_view("\n".join(lines), surface=self._terminal)

    def _report_command(self, argument: str) -> None:
        conversation_id = self.current_conversation_id
        if conversation_id is None:
            self._notice("Open a conversation before linking a report.")
            return
        if argument == "unlink" or argument.startswith("unlink "):
            links = self.client.call(
                "conversation.links", conversation_id=conversation_id
            )
            requested = argument.removeprefix("unlink").strip().upper()
            report_id = requested or next(
                (str(link["report_id"]) for link in links if link["role"] == "primary"),
                "",
            )
            if not report_id:
                self._notice("This conversation has no primary report link.")
                return
            self.client.call(
                "conversation.unlink_report",
                conversation_id=conversation_id,
                report_id=report_id,
            )
            self._notice(f"Unlinked report {report_id}.")
            return
        report_id = argument.upper()
        if not report_id:
            self._notice("Usage: /report <report-id> or /report unlink")
            return
        try:
            self.client.call("report.show", report_id=report_id)
        except (CoreRpcError, ConnectionError) as error:
            self._notice(f"Could not open report {report_id}: {error}")
            return
        if conversation_id.startswith("TMP-"):
            decision = select_button(
                (
                    TerminalButton("Cancel", "cancel"),
                    TerminalButton("Save & Link", "save-link"),
                    TerminalButton("Summary Only", "summary-only"),
                ),
                content=(
                    f"Save & Link to {report_id} retains this temporary chat's full transcript. "
                    "Choose Summary Only to extract material "
                    "report knowledge while keeping the transcript temporary."
                ),
                surface=self._terminal,
            )
            if decision == "summary-only":
                try:
                    result = self.client.call("conversation.contribute_temporary",
                                              conversation_id=conversation_id,
                                              report_id=report_id, client_id=self._connect())
                except (CoreRpcError, ConnectionError) as error:
                    self._notice(f"Could not contribute report knowledge: {error}")
                else:
                    self._notice("Material report knowledge saved; the chat remains temporary."
                                 if result["material"] else "No material report information found; the chat remains temporary.")
                return
            if decision != "save-link":
                self._notice("Report link canceled; this chat remains temporary.")
                return
            self._save_current()
            conversation_id = self.current_conversation_id
            if conversation_id is None or conversation_id.startswith("TMP-"):
                return
        try:
            self.client.call(
                "conversation.link_report",
                conversation_id=conversation_id,
                report_id=report_id,
                role="primary",
                contribution_summary=None,
            )
        except (CoreRpcError, ConnectionError) as error:
            self._notice(f"Could not link report {report_id}: {error}")
            return
        self._notice(f"Linked this conversation to report {report_id}.")

    def _connect(self) -> str:
        if self.client_id is None:
            result = self.client.call("client.connect")
            self.client_id = str(result["id"])
            self._heartbeat_stop.clear()
            self._heartbeat_thread = Thread(
                target=self._heartbeat,
                name="eden-cli-heartbeat",
                daemon=True,
            )
            self._heartbeat_thread.start()
        return self.client_id

    def _heartbeat(self) -> None:
        while not self._heartbeat_stop.wait(5):
            client_id = self.client_id
            if client_id is None:
                return
            try:
                self.client.call("client.heartbeat", client_id=client_id)
            except (CoreRpcError, ConnectionError):
                return

    def _send_message(
        self,
        message: str,
        *,
        diagnostic_component: str | None = None,
    ) -> None:
        client_id = self._connect()
        if self.current_conversation_id is None:
            aggregate = self.client.call(
                "conversation.create_temporary",
                client_id=client_id,
                title=_title(message),
            )
            self.current_conversation_id = str(aggregate["conversation"]["id"])
            self.pending_new_chat = False
        existing = self._work.get(self.current_conversation_id)
        if existing is not None and not existing.done():
            self._notice("This conversation is already working. Use /new for another thread.")
            return
        conversation_id = self.current_conversation_id
        self._record_activity(conversation_id)
        self._pending_messages[conversation_id] = message
        self._work_details[conversation_id] = (
            f"Collecting read-only {diagnostic_component} evidence."
            if diagnostic_component
            else "Classifying the request and preparing conversation context."
        )
        future = self._workers.submit(
            self.client.call,
            "conversation.send",
            conversation_id=conversation_id,
            message=message,
            diagnostic_component=diagnostic_component,
        )
        self._work[conversation_id] = future
        future.add_done_callback(
            lambda completed, current_id=conversation_id: self._show_result(current_id, completed)
        )

    def _show_result(self, conversation_id: str, future: Future[Any]) -> None:
        original_id = conversation_id
        conversation_id = self._conversation_aliases.get(conversation_id, conversation_id)
        try:
            result = future.result()
            conversation_id = str(result.get("conversation_id", conversation_id))
            if result.get("summary_warning"):
                self._add_conversation_notice(conversation_id, str(result["summary_warning"]))
            if result.get("report_contribution_warning"):
                self._add_conversation_notice(conversation_id, str(result["report_contribution_warning"]))
        except (CoreRpcError, ConnectionError) as error:
            self._add_conversation_notice(conversation_id, f"Eden could not respond: {error}")
        except Exception as error:  # noqa: BLE001 - background callback boundary
            self._add_conversation_notice(
                conversation_id,
                f"Work ended unexpectedly: {type(error).__name__}",
            )
        finally:
            self._pending_messages.pop(original_id, None)
            self._work_details.pop(original_id, None)
            self._pending_messages.pop(conversation_id, None)
            self._work_details.pop(conversation_id, None)
            self._stop_requests.discard(conversation_id)
            self._refresh_visible_feed()

    def _ctrl_c(self) -> None:
        conversation_id = self.current_conversation_id
        future = self._work.get(conversation_id) if conversation_id else None
        if future is not None and not future.done():
            self._request_stop()
        else:
            self._notice("No active work in this conversation.")

    def _request_stop(self) -> None:
        conversation_id = self.current_conversation_id
        future = self._work.get(conversation_id) if conversation_id else None
        if conversation_id is None or future is None or future.done():
            self._notice("There is no active work in this conversation.")
            return
        hard = conversation_id in self._stop_requests
        result = self.client.call("conversation.stop", conversation_id=conversation_id, hard=hard)
        if hard:
            future.cancel()
            self._notice(
                "Hard stop requested. No new steps will begin; uncertain work will require recovery."
            )
        else:
            self._stop_requests.add(conversation_id)
            self._notice(
                "Stop requested at the next safe boundary. Press Ctrl+C or run /stop again "
                "to request a hard stop."
            )
        if result["affected_task_ids"]:
            self._notice("Affected tasks: " + ", ".join(result["affected_task_ids"]))

    def _conversation_activity(self) -> list[ConversationPreview]:
        if self.client_id is None:
            return []
        try:
            temporary = self.client.call("conversation.client_temporary", client_id=self.client_id)
        except (CoreRpcError, ConnectionError):
            temporary = []
        temporary_by_id = {
            str(item["conversation"]["id"]): item for item in temporary
        }
        conversations: list[ConversationPreview] = []
        ordered_ids = list(dict.fromkeys([*self._activity_history, *self._work]))
        for conversation_id in ordered_ids:
            deleted_title = self._deleted_activity.get(conversation_id)
            if deleted_title is not None:
                conversations.append(
                    ConversationPreview(
                        id=conversation_id, title=deleted_title, activity="deleted"
                    )
                )
                continue
            future = self._work.get(conversation_id)
            item = temporary_by_id.get(conversation_id)
            if item is not None:
                working = bool(item["working"]) or (future is not None and not future.done())
                title = str(item["conversation"]["title"])
            else:
                if conversation_id.startswith("TMP-"):
                    continue
                try:
                    aggregate = self.client.call(
                        "conversation.get",
                        conversation_id=conversation_id,
                        client_id=self.client_id,
                    )
                except (CoreRpcError, ConnectionError):
                    continue
                if aggregate["conversation"].get("transcript_state") == "deleted":
                    conversations.append(
                        ConversationPreview(
                            id=conversation_id,
                            title=str(aggregate["conversation"]["title"]),
                            activity="deleted",
                        )
                    )
                    continue
                title = str(aggregate["conversation"]["title"])
                working = future is not None and not future.done()
            conversations.append(
                ConversationPreview(
                    id=conversation_id,
                    title=title,
                    activity="working" if working else "complete",
                    detail=self._work_detail(conversation_id) if working else None,
                )
            )
        return conversations

    def _record_activity(self, conversation_id: str) -> None:
        if conversation_id in self._activity_history:
            self._activity_history.remove(conversation_id)
        self._activity_history.append(conversation_id)

    def _show_home_activity(
        self,
        activity: list[ConversationPreview] | None = None,
        *,
        redraw: bool = True,
    ) -> None:
        items = activity if activity is not None else self._conversation_activity()
        visible = list(reversed(items[-self.settings.cli.home_preview_limit :]))
        lines: list[str] = []
        for item in visible:
            signal = (
                self._spinner() if item.activity == "working"
                else "×" if item.activity == "deleted" else "✓"
            )
            state = item.detail or (
                "Working…" if item.activity == "working"
                else "Deleted" if item.activity == "deleted" else "Complete"
            )
            lines.append(f"{signal} {item.id}  {item.title} — {state}")
        if len(items) > len(visible):
            lines.append(f"See all {len(items)} conversations")
        self._terminal.set_activity(lines, title="Activity", align="top", redraw=redraw)

    def _show_thread_feed(self, conversation_id: str, *, redraw: bool = True) -> None:
        self._terminal.set_activity(
            self._thread_feed_lines(conversation_id),
            title=None,
            identity=conversation_id,
            redraw=redraw,
        )

    def _conversation_state(self, conversation_id: str) -> str:
        if conversation_id.startswith("TMP-"):
            return "TEMPORARY — not saved"
        try:
            aggregate = self.client.call("conversation.get", conversation_id=conversation_id,
                                         client_id=self.client_id)
            state = str(aggregate["conversation"]["transcript_state"]).capitalize()
            links = self.client.call("conversation.links", conversation_id=conversation_id)
            primary = next((link for link in links if link["role"] == "primary"), None)
            label = f"SAVED — {state}"
            if primary is not None:
                label += f" — REPORT {primary['report_id']}"
                updated = primary.get("contribution_updated_at")
                if updated:
                    label += f" — Contribution reviewed {updated}"
            return label
        except (CoreRpcError, ConnectionError):
            return "Saved conversation — connection unavailable"

    def _thread_feed_lines(self, conversation_id: str) -> list[str]:
        lines: list[str] = []
        try:
            aggregate = self.client.call(
                "conversation.get",
                conversation_id=conversation_id,
                client_id=self.client_id,
            )
        except (CoreRpcError, ConnectionError) as error:
            pending = self._pending_messages.get(conversation_id)
            future = self._work.get(conversation_id)
            if pending is not None and future is not None and not future.done():
                return [
                    "You",
                    *(f"  {part}" for part in pending.splitlines()),
                    "",
                    "Eden",
                    f"  {self._spinner()} {self._work_detail(conversation_id)}",
                ]
            return ["System", f"  Could not load this conversation: {error}"]

        try:
            warnings = self.client.call(
                "conversation.warnings",
                conversation_id=conversation_id,
                client_id=self.client_id,
            )
            for warning in warnings:
                warning_id = str(warning["id"])
                if warning_id not in self._seen_work_warnings:
                    self._seen_work_warnings.add(warning_id)
                    self._add_conversation_notice(conversation_id, str(warning["message"]))
        except (CoreRpcError, ConnectionError):
            pass

        messages = list(aggregate["messages"])
        future = self._work.get(conversation_id)
        pending = self._pending_messages.get(conversation_id)
        if pending is not None and future is not None and not future.done() and not any(
            message["role"] == "user" and message["content"] == pending for message in messages[-1:]
        ):
            last_sequence = int(messages[-1].get("sequence", len(messages))) if messages else 0
            messages.append({"role": "user", "content": pending, "sequence": last_sequence + 1})

        events = [
            (int(message.get("sequence", index)), 0, index,
             "You" if message["role"] == "user" else "Eden", str(message["content"]))
            for index, message in enumerate(messages, start=1)
        ]
        last_sequence = events[-1][0] if events else 0
        for index, notice in enumerate(list(self._conversation_notices.get(conversation_id, []))):
            if notice.after_sequence is None:
                notice.after_sequence = last_sequence
            events.append((notice.after_sequence, 1, index, "System", notice.text))
        for _, _, _, speaker, content in sorted(events):
            if lines:
                lines.append("")
            lines.append(speaker)
            lines.extend(f"  {part}" for part in content.splitlines())

        if future is not None and not future.done():
            if lines:
                lines.append("")
            lines.extend(
                ["Eden", f"  {self._spinner()} {self._work_detail(conversation_id, detailed=True)}"]
            )

        return lines

    def _work_detail(self, conversation_id: str, *, detailed: bool = False) -> str:
        detail = self._work_details.get(
            conversation_id, "Finalizing the local response."
        )
        try:
            status = self.client.call(
                "conversation.work_status", conversation_id=conversation_id
            )
            if status is not None:
                if detailed:
                    return render_work_status(status, details=self._technical_details)
                detail = str(status["detail"])
        except (CoreRpcError, ConnectionError):
            pass
        return detail

    @staticmethod
    def _spinner() -> str:
        return ("◐", "◓", "◑", "◒")[int(time.monotonic() * 5) % 4]

    def _add_conversation_notice(self, conversation_id: str, message: str) -> None:
        self._conversation_notices.setdefault(conversation_id, []).append(ConversationNotice(message))

    def _refresh_visible_feed(self) -> None:
        conversation_id = self.current_conversation_id
        if conversation_id is None:
            self._show_home_activity()
        else:
            self._show_thread_feed(conversation_id)

    def _exit(self) -> bool:
        if self.client_id is None:
            return True
        try:
            assessment = self.client.call("client.assess_close", client_id=self.client_id)
        except (CoreRpcError, ConnectionError):
            return True
        active = list(assessment["active_temporary_ids"])
        meaningful = list(assessment["meaningful_temporary_ids"])
        if active or meaningful:
            choice = select_button(
                (
                    TerminalButton("Discard & Exit", "discard"),
                    TerminalButton("Save & Exit", "save"),
                    TerminalButton("Back", "cancel"),
                ),
                content=(
                    "Temporary conversations will not survive this CLI session.\n"
                    "Choose how to handle them. Esc also returns."
                ),
                surface=self._terminal,
            )
            if choice in {None, "cancel"}:
                return False
            if choice == "save":
                for conversation_id in [*active, *meaningful]:
                    self.client.call("conversation.persist", conversation_id=conversation_id)
            elif choice == "discard":
                self.client.call(
                    "conversation.discard_client_temporary",
                    client_id=self.client_id,
                    include_working=True,
                )
        self.client.call("client.disconnect", client_id=self.client_id)
        self._heartbeat_stop.set()
        if self._heartbeat_thread is not None:
            self._heartbeat_thread.join(timeout=1)
        self._workers.shutdown(wait=False, cancel_futures=True)
        return True

    def _animate_work(self) -> None:
        while not self._redraw_stop.wait(0.2):
            if any(not future.done() for future in self._work.values()):
                self._refresh_visible_feed()

    def _notice(self, message: str) -> None:
        if self.current_conversation_id is None:
            self._home_notices.append(message)
            del self._home_notices[:-20]
        else:
            self._add_conversation_notice(self.current_conversation_id, message)
        self._refresh_visible_feed()


def _title(message: str) -> str:
    compact = " ".join(message.split())
    if len(compact) <= 80:
        return compact
    return compact[:77].rstrip() + "..."


def client_opened_at() -> str:
    return datetime.now(UTC).isoformat()
