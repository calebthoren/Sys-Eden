"""Authenticated local RPC for the normal-user Eden Core process."""

from __future__ import annotations

import asyncio
import getpass
import hashlib
import os
import secrets
import subprocess
import sys
import time
from datetime import UTC, datetime
from multiprocessing.connection import Client
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from sys_eden.config import Settings
from sys_eden.conversation_models import LinkActor, ReportLinkRole
from sys_eden.conversation_work import ConversationStopped
from sys_eden.core import Core
from sys_eden.core_application import CoreApplication, CoreLifecycleState, CoreRuntimeStatus
from sys_eden.core_client import CoreUnavailable
from sys_eden.core_presence import known_stopped
from sys_eden.report_models import ReportSearch, ReportStatus
from sys_eden.task_models import RuntimeStopReason, TaskEventType, TechnicalOperation


class RpcRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(default_factory=lambda: f"REQ-{uuid4().hex[:12].upper()}")
    method: str = Field(pattern=r"^[a-z][a-z0-9_.-]*$", max_length=100)
    params: dict[str, Any] = Field(default_factory=dict)


class RpcError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    retryable: bool = False


class RpcResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    ok: bool
    result: Any | None = None
    error: RpcError | None = None


class CoreRpcError(RuntimeError):
    def __init__(self, error: RpcError):
        super().__init__(error.message)
        self.code = error.code
        self.retryable = error.retryable


class ByteConnection(Protocol):
    def send_bytes(self, buf: bytes, offset: int = 0, size: int | None = None) -> None: ...

    def recv_bytes(self, maxlength: int | None = None) -> bytes: ...

    def close(self) -> None: ...

    def poll(self, timeout: float | None = 0.0) -> bool: ...


def rpc_endpoint(settings: Settings) -> tuple[str, str]:
    identity = f"{getpass.getuser()}|{settings.data_directory.resolve()}"
    suffix = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    if os.name == "nt":
        return rf"\\.\pipe\sys-eden-{suffix}", "AF_PIPE"
    return str(settings.data_directory.resolve() / f".core-{suffix}.sock"), "AF_UNIX"


def core_auth_path(settings: Settings) -> Path:
    return settings.data_directory.resolve() / ".core-auth"


def ensure_core_authkey(settings: Settings) -> bytes:
    path = core_auth_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        return bytes.fromhex(path.read_text(encoding="ascii").strip())
    except FileNotFoundError:
        key = secrets.token_bytes(32)
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            return bytes.fromhex(path.read_text(encoding="ascii").strip())
        with os.fdopen(descriptor, "w", encoding="ascii") as stream:
            stream.write(key.hex())
        return key
    except (OSError, ValueError) as error:
        raise CoreUnavailable("The local Core authentication key is unavailable.") from error


def read_core_authkey(settings: Settings) -> bytes:
    try:
        value = core_auth_path(settings).read_text(encoding="ascii").strip()
        key = bytes.fromhex(value)
    except (OSError, ValueError) as error:
        raise CoreUnavailable("The local Core authentication key is unavailable.") from error
    if len(key) != 32:
        raise CoreUnavailable("The local Core authentication key is invalid.")
    return key


class CoreRpcDispatcher:
    """Map protocol methods to Core-owned application services."""

    def __init__(self, application: CoreApplication):
        self.application = application
        self.stop_requested = False

    def dispatch(self, request: RpcRequest) -> RpcResponse:
        try:
            result = self._dispatch(request.method, request.params)
            return RpcResponse(request_id=request.request_id, ok=True, result=result)
        except ConversationStopped as error:
            return RpcResponse(
                request_id=request.request_id,
                ok=False,
                error=RpcError(code="work.stopped", message=str(error)),
            )
        except (KeyError, ValueError) as error:
            return RpcResponse(
                request_id=request.request_id,
                ok=False,
                error=RpcError(code="request.invalid", message=str(error)),
            )
        except Exception as error:  # noqa: BLE001 - protocol boundary sanitizes failures
            return RpcResponse(
                request_id=request.request_id,
                ok=False,
                error=RpcError(
                    code="core.operation_failed",
                    message=f"Core operation failed: {type(error).__name__}",
                    retryable=False,
                ),
            )

    def _dispatch(self, method: str, params: dict[str, Any]) -> Any:
        if method == "core.status":
            return self.application.status.model_dump(mode="json")
        if method == "core.stop":
            status = self.application.stop(RuntimeStopReason.USER_REQUESTED)
            self.stop_requested = True
            return status.model_dump(mode="json")
        if method == "task.list":
            return [task.model_dump(mode="json") for task in self.application.tasks.list()]
        if method == "task.get":
            task_id = str(params["task_id"])
            task = self.application.tasks.get(task_id)
            task = task.model_copy(update={
                "active_elapsed_seconds": self.application.task_engine.current_elapsed(task_id)
            })
            return {
                "task": task.model_dump(mode="json"),
                "events": [
                    event.model_dump(mode="json")
                    for event in self.application.tasks.events(task_id)
                ],
                "checkpoints": [
                    checkpoint.model_dump(mode="json")
                    for checkpoint in self.application.tasks.checkpoints(task_id)
                ],
                "conversations": [
                    link.model_dump(mode="json")
                    for link in self.application.tasks.conversations_for_task(task_id)
                ],
            }
        if method == "task.pause":
            return self.application.task_engine.request_pause(str(params["task_id"])).model_dump(
                mode="json"
            )
        if method == "task.resume":
            task = self.application.tasks.get(str(params["task_id"]))
            if not task.synthetic and not any(
                self.application.active_conversation_task_id(link.conversation_id) == task.id
                for link in self.application.tasks.conversations_for_task(task.id)
            ):
                raise ValueError(
                    "No live runner remains for this task. Review its checkpoint and start "
                    "a fresh read-only investigation in its conversation."
                )
            return self.application.task_engine.resume(str(params["task_id"])).model_dump(
                mode="json"
            )
        if method == "task.cancel":
            return self.application.task_engine.request_cancel(str(params["task_id"])).model_dump(
                mode="json"
            )
        if method == "task.reconcile":
            return self.application.task_engine.reconcile_recovery(
                str(params["task_id"]),
                safe_to_resume=bool(params["safe_to_resume"]),
                message=str(params["message"]),
            ).model_dump(mode="json")
        if method == "storage.status":
            return self.application.storage_status.status().model_dump(mode="json")
        if method == "storage.recommendations":
            return [
                item.model_dump(mode="json")
                for item in self.application.storage_status.recommendations()
            ]
        if method == "storage.category":
            category = str(params["category"])
            status = self.application.storage_status.status().model_dump(mode="json")
            attribution = status["attribution"]
            mapping = {
                "reports": {"structured_reports": attribution["structured_reports"]},
                "conversations": {
                    "conversation_transcripts_full": attribution[
                        "conversation_transcripts_full"
                    ],
                    "conversation_records_compact": attribution[
                        "conversation_records_compact"
                    ],
                    "protected": attribution["protected"],
                    "estimated_reclaimable": attribution["estimated_reclaimable"],
                },
                "attachments": {"attachments": attribution["attachments"]},
            }
            if category not in mapping:
                raise ValueError("unsupported storage category")
            return {
                "category": category,
                "attribution": mapping[category],
                "counts": status["counts"],
                "largest_consumers": [
                    item
                    for item in status["largest_consumers"]
                    if category != "conversations" or item["category"] == "conversation"
                ],
                "estimated": status["estimated"],
                "changed_data": False,
            }
        if method == "health":
            return asyncio.run(Core(self.application.settings, self.application.provider).health()).model_dump(
                mode="json"
            )
        if method == "inspection.inspect":
            return [
                item.model_dump(mode="json")
                for item in asyncio.run(
                    self.application.inspection.inspect(
                        str(params.get("component", "system")),
                        details=bool(params.get("details", False)),
                    )
                )
            ]
        if method == "model.health":
            return asyncio.run(self.application.model_service.health()).model_dump(mode="json")
        if method == "model.list":
            return [
                item.model_dump(mode="json")
                for item in asyncio.run(self.application.model_service.list_models())
            ]
        if method == "report.list":
            query = ReportSearch.model_validate(params.get("query") or {})
            return [
                item.model_dump(mode="json")
                for item in self.application.report_service.search(query)
            ]
        if method == "report.show":
            return self.application.report_service.get(str(params["report_id"])).model_dump(
                mode="json"
            )
        if method == "report.export":
            return self.application.report_service.export_json(str(params["report_id"]))
        if method == "report.close":
            self.application.report_service.prepare_close(
                str(params["report_id"]), status=ReportStatus(str(params["status"])),
                summary=str(params["summary"]), outcome=str(params["outcome"]),
            )
            contribution_warnings: list[str] = []
            for link in self.application.conversations.links_for_report(str(params["report_id"])):
                _, warning = asyncio.run(self.application.chat.refresh_contributions(
                    link.conversation_id
                ))
                if warning is not None:
                    contribution_warnings.append(warning)
            report, candidates = self.application.close_report(
                str(params["report_id"]),
                status=ReportStatus(str(params["status"])),
                summary=str(params["summary"]),
                outcome=str(params["outcome"]),
            )
            return {
                "report": report.model_dump(mode="json"),
                "retention_candidates": [
                    candidate.model_dump(mode="json") for candidate in candidates
                ],
                "transcripts_changed": False,
                "contribution_warnings": contribution_warnings,
            }
        if method == "report.retention_candidates":
            report_id = str(params["report_id"])
            self.application.reports.get(report_id)
            return [
                candidate.model_dump(mode="json")
                for candidate in self.application.conversations.retention_candidates(report_id)
            ]
        if method == "report.review_retention":
            if params.get("evidence_reviewed") is not True:
                raise ValueError("explicit unique-evidence review confirmation is required")
            report_id = str(params["report_id"])
            unique_ids = {str(item) for item in params.get("unique_evidence_ids", [])}
            linked = {
                item.conversation_id
                for item in self.application.conversations.links_for_report(report_id)
            }
            if not unique_ids <= linked:
                raise ValueError("unique-evidence IDs must be linked to this report")
            return [
                candidate.model_dump(mode="json")
                for candidate in self.application.conversation_service.review_closed_report_retention(
                    report_id, unique_evidence_conversation_ids=unique_ids
                )
            ]
        if method == "client.connect":
            return self.application.client_sessions.connect().model_dump(mode="json")
        if method == "client.heartbeat":
            return self.application.client_sessions.heartbeat(str(params["client_id"])).model_dump(
                mode="json"
            )
        if method == "client.assess_close":
            return self.application.client_sessions.assess_close(
                str(params["client_id"])
            ).model_dump(mode="json")
        if method == "client.disconnect":
            return self.application.client_sessions.disconnect(str(params["client_id"])).model_dump(
                mode="json"
            )
        if method == "conversation.create_temporary":
            aggregate = self.application.conversation_service.create_temporary(
                title=str(params["title"]), owner_client_id=str(params["client_id"])
            )
            return aggregate.model_dump(mode="json")
        if method == "conversation.list":
            return [
                item.model_dump(mode="json")
                for item in self.application.conversations.list(limit=int(params.get("limit", 100)))
            ]
        if method == "conversation.client_temporary":
            client_id = str(params["client_id"])
            return [
                {
                    "conversation": aggregate.conversation.model_dump(mode="json"),
                    "working": self.application.conversation_service.temporary_is_working(
                        aggregate.conversation.id
                    ),
                }
                for aggregate in self.application.conversation_service.temporary_for_client(
                    client_id
                )
            ]
        if method == "conversation.work_status":
            conversation_id = str(params["conversation_id"])
            status = self.application.conversation_service.work_status(
                conversation_id
            )
            if status is None:
                return None
            payload = status.model_dump(mode="json")
            payload["technical_operation"] = self.application.conversation_operation(conversation_id)
            task_id = self.application.active_conversation_task_id(conversation_id)
            if task_id is not None:
                task = self.application.tasks.get(task_id)
                payload["task"] = task.model_dump(mode="json")
                payload["elapsed_seconds"] = self.application.task_engine.current_elapsed(task_id)
                if task.progress is not None:
                    payload["operation_elapsed_seconds"] = max(
                        0, payload["elapsed_seconds"] - (
                            task.progress.operation_started_elapsed_seconds
                            if task.progress.operation_started_elapsed_seconds is not None
                            else task.progress.active_elapsed_seconds
                        )
                    )
            return payload
        if method == "conversation.warnings":
            conversation_id = str(params["conversation_id"])
            self.application.conversation_service.get_current(
                conversation_id,
                owner_client_id=(
                    str(params["client_id"]) if params.get("client_id") is not None else None
                ),
            )
            warnings = []
            for task in self.application.tasks.tasks_for_conversation(conversation_id):
                warnings.extend(
                    event.model_dump(mode="json")
                    for event in self.application.tasks.events(task.id)
                    if event.event_type is TaskEventType.NON_STOPPABLE_SEGMENT_ANNOUNCED
                )
            return sorted(warnings, key=lambda item: str(item["occurred_at"]))[-20:]
        if method == "conversation.get":
            return self.application.conversation_service.get_current(
                str(params["conversation_id"]),
                owner_client_id=(
                    str(params["client_id"]) if params.get("client_id") is not None else None
                ),
            ).model_dump(mode="json")
        if method == "conversation.links":
            return [
                item.model_dump(mode="json")
                for item in self.application.conversations.links_for_conversation(
                    str(params["conversation_id"])
                )
            ]
        if method == "conversation.pin":
            aggregate = self.application.conversations.get(str(params["conversation_id"]))
            return self.application.conversations.set_pinned(
                aggregate.conversation.id,
                expected_revision=aggregate.conversation.revision,
                pinned=bool(params["pinned"]),
                updated_at=datetime.now(UTC),
            ).model_dump(mode="json")
        if method == "conversation.delete":
            aggregate = self.application.conversations.get(str(params["conversation_id"]))
            return self.application.conversations.delete_transcript(
                aggregate.conversation.id,
                expected_revision=aggregate.conversation.revision,
                updated_at=datetime.now(UTC),
            ).model_dump(mode="json")
        if method in {
            "conversation.delete_staged", "conversation.restore", "conversation.restorable"
        }:
            client_id = str(params["client_id"])
            self.application.client_sessions.require_connected(client_id)
            service = self.application.conversation_service
            if method == "conversation.restorable":
                return [
                    item.model_dump(mode="json")
                    for item in service.restorable_for_client(client_id)
                ]
            conversation_id = str(params["conversation_id"])
            if method == "conversation.delete_staged":
                return service.delete_for_client(
                    conversation_id, client_id=client_id
                ).conversation.model_dump(mode="json")
            return service.restore_for_client(
                conversation_id, client_id=client_id
            ).model_dump(mode="json")
        if method == "conversation.send":
            conversation_id = str(params["conversation_id"])
            work = self.application.begin_conversation_work(conversation_id)
            try:
                if conversation_id.startswith("TMP-"):
                    self.application.conversation_service.set_temporary_working(
                        conversation_id, working=True
                    )
                self.application.conversation_service.set_work_status(
                    conversation_id,
                    phase="starting",
                    detail="Preparing this conversation request.",
                )

                def report_progress(
                    phase: str, detail: str, operation: TechnicalOperation | None = None
                ) -> None:
                    work.record_progress(phase, detail, operation)
                    self.application.conversation_service.set_work_status(
                        conversation_id, phase=phase, detail=detail
                    )

                async def send_with_work() -> Any:
                    work.bind_current_task()
                    return await self.application.chat.send(
                        conversation_id,
                        str(params["message"]),
                        diagnostic_component=(
                            str(params["diagnostic_component"])
                            if params.get("diagnostic_component") is not None
                            else None
                        ),
                        progress=report_progress,
                        work=work,
                    )

                result = asyncio.run(send_with_work())
                work.complete(result.response)
            except asyncio.CancelledError as error:
                work.fail(error)
                raise ConversationStopped("Conversation hard-stopped.") from None
            except Exception as error:
                work.fail(error)
                raise
            finally:
                canonical_id = self.application.conversation_service.resolve_id(conversation_id)
                self.application.end_conversation_work(work)
                self.application.conversation_service.clear_work_status(canonical_id)
                if canonical_id.startswith("TMP-"):
                    try:
                        self.application.conversation_service.set_temporary_working(
                            conversation_id, working=False
                        )
                    except KeyError:
                        # The temporary chat may already have been discarded.
                        pass
                self.application.conversation_service.finish_promotion(conversation_id)
            payload = result.model_dump(mode="json")
            payload["conversation_id"] = canonical_id
            payload["report_id"] = self.application.conversation_service.context_for_current(
                canonical_id
            ).primary_report_id
            if work.task_id is not None:
                payload["task_id"] = work.task_id
            return payload
        if method == "conversation.stop":
            hard = bool(params.get("hard", False))
            return {
                "mode": "hard" if hard else "safe",
                "affected_task_ids": self.application.stop_conversation_work(
                    str(params["conversation_id"]), hard=hard
                ),
            }
        if method == "conversation.persist":
            return self.application.persist_conversation(
                str(params["conversation_id"])
            ).model_dump(mode="json")
        if method == "conversation.compact":
            if self.application.is_conversation_working(str(params["conversation_id"])):
                raise ValueError("Wait for current conversation work to finish before compacting it.")
            return asyncio.run(
                self.application.chat.compact_conversation(str(params["conversation_id"]))
            ).model_dump(mode="json")
        if method == "conversation.summarize":
            if self.application.is_conversation_working(str(params["conversation_id"])):
                raise ValueError("Wait for current conversation work to finish before summarizing it.")
            return asyncio.run(
                self.application.chat.summarize_conversation(str(params["conversation_id"]))
            ).model_dump(mode="json")
        if method == "conversation.export":
            return self.application.conversations.get(
                str(params["conversation_id"])
            ).model_dump(mode="json")
        if method == "conversation.link_report":
            link = self.application.conversation_service.link_saved_conversation(
                str(params["conversation_id"]),
                str(params["report_id"]),
                role=ReportLinkRole(str(params.get("role", "primary"))),
                contribution_summary=(
                    str(params["contribution_summary"])
                    if params.get("contribution_summary") is not None
                    else None
                ),
                linked_by=LinkActor.USER,
            )
            updated, warning = asyncio.run(self.application.chat.refresh_contributions(
                link.conversation_id
            ))
            refreshed = next(item for item in self.application.conversations.links_for_conversation(
                link.conversation_id
            ) if item.report_id == link.report_id)
            return refreshed.model_dump(mode="json") | {
                "contribution_updated": updated, "contribution_warning": warning,
            }
        if method == "conversation.contribute_temporary":
            conversation_id = str(params["conversation_id"])
            source = self.application.conversation_service.get_current(
                conversation_id, owner_client_id=str(params["client_id"])
            )
            if not conversation_id.startswith("TMP-"):
                raise ValueError("summary-only contribution requires a temporary conversation")
            report = self.application.reports.get(str(params["report_id"]))
            summary = asyncio.run(self.application.contributions.extract(source, report.objective))
            if summary is None:
                return {"material": False, "transcript_saved": False}
            contribution = self.application.conversation_service.contribute_temporary_without_saving(
                conversation_id, report.id, material_summary=summary
            )
            return {"material": True, "transcript_saved": False,
                    "contribution": contribution.model_dump(mode="json")}
        if method == "conversation.unlink_report":
            self.application.conversations.unlink_report(
                str(params["report_id"]), str(params["conversation_id"])
            )
            return {
                "conversation_id": str(params["conversation_id"]),
                "report_id": str(params["report_id"]),
                "unlinked": True,
            }
        if method == "conversation.discard_client_temporary":
            for aggregate in self.application.conversation_service.active_temporary_for_client(
                str(params["client_id"])
            ):
                if bool(params["include_working"]):
                    self.application.stop_conversation_work(aggregate.conversation.id, hard=False)
            return self.application.conversation_service.discard_client_temporary(
                str(params["client_id"]), include_working=bool(params["include_working"])
            )
        raise ValueError(f"Unknown Core method: {method}")


class LocalCoreClient:
    """Connect to or launch the separate normal-user Core process."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.address, self.family = rpc_endpoint(settings)

    async def status(self) -> CoreRuntimeStatus:
        try:
            payload = await asyncio.to_thread(self.call, "core.status")
        except CoreUnavailable:
            return CoreRuntimeStatus(state=(
                CoreLifecycleState.STOPPED if known_stopped(self.settings.data_directory)
                else CoreLifecycleState.UNAVAILABLE
            ))
        return CoreRuntimeStatus.model_validate(payload)

    async def start_core(self) -> CoreRuntimeStatus:
        current = await self.status()
        if current.state is CoreLifecycleState.RUNNING:
            return current
        ensure_core_authkey(self.settings)
        self._launch()
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            await asyncio.sleep(0.1)
            current = await self.status()
            if current.state is CoreLifecycleState.RUNNING:
                return current
        raise CoreUnavailable("Eden Core did not become available within 10 seconds.")

    async def stop_core(self) -> CoreRuntimeStatus:
        current = await self.status()
        if current.state is CoreLifecycleState.STOPPED:
            return current
        if current.state is CoreLifecycleState.UNAVAILABLE:
            raise CoreUnavailable("Core is unreachable; a graceful stop could not be confirmed.")
        payload = await asyncio.to_thread(self.call, "core.stop")
        return CoreRuntimeStatus.model_validate(payload)

    def call(self, method: str, **params: Any) -> Any:
        request = RpcRequest(method=method, params=params)
        try:
            authkey = read_core_authkey(self.settings)
            connection = Client(self.address, family=self.family, authkey=authkey)
        except (OSError, CoreUnavailable) as error:
            raise CoreUnavailable("Eden Core is stopped or unavailable.") from error
        try:
            _send(connection, request.model_dump_json().encode("utf-8"))
            if (method in {"core.status", "client.heartbeat", "conversation.work_status"}
                    and not connection.poll(3)):
                raise CoreUnavailable("Core did not answer the connection check within 3 seconds.")
            response = RpcResponse.model_validate_json(_receive(connection))
        except (OSError, EOFError, ValueError) as error:
            raise CoreUnavailable("The local Core connection ended unexpectedly.") from error
        finally:
            connection.close()
        if not response.ok:
            assert response.error is not None
            raise CoreRpcError(response.error)
        return response.result

    def _launch(self) -> None:
        executable = sys.executable
        options: dict[str, Any] = {
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "close_fds": True,
        }
        if os.name == "nt":
            # The windowed interpreter never creates a console. Keep the same
            # environment so editable installs and local dependencies still resolve.
            windowed = Path(executable).with_name("pythonw.exe")
            if windowed.is_file():
                executable = str(windowed)
            # CREATE_NO_WINDOW is ignored when paired with DETACHED_PROCESS.
            # A separate process does not require a visible console to outlive
            # the CLI that launched it.
            options["creationflags"] = subprocess.CREATE_NO_WINDOW
        else:
            options["start_new_session"] = True
        subprocess.Popen([executable, "-m", "sys_eden.core_host"], **options)


def _send(connection: ByteConnection, payload: bytes) -> None:
    if len(payload) > 8 * 1024 * 1024:
        raise ValueError("Core RPC message exceeds the 8 MiB limit")
    connection.send_bytes(payload)


def _receive(connection: ByteConnection) -> bytes:
    return connection.recv_bytes(8 * 1024 * 1024)


def stopped_status_json() -> dict[str, Any]:
    return CoreRuntimeStatus(state=CoreLifecycleState.STOPPED).model_dump(mode="json") | {
        "observed_at": datetime.now(UTC).isoformat()
    }
