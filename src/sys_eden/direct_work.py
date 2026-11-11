"""Keep a direct CLI request alive, stoppable and observable without opening a UI."""

from __future__ import annotations

import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from typing import Any

from sys_eden.progress_views import render_work_status


def follow_conversation(
    rpc: Callable[..., Any], *, client_id: str, conversation_id: str,
    message: str, diagnostic_component: str | None, details: bool,
    emit: Callable[[str], None], poll_seconds: float = 0.5,
) -> Any:
    """Poll read-only state; a second Ctrl+C requests hard stop of this request only."""
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="eden-direct-request")
    future = executor.submit(
        rpc, "conversation.send", conversation_id=conversation_id, message=message,
        diagnostic_component=diagnostic_component,
    )
    last_state: tuple[object, ...] | None = None
    seen_warnings: set[str] = set()
    last_heartbeat = time.monotonic()
    last_display = last_heartbeat
    stop_count = 0
    try:
        while True:
            try:
                return future.result(timeout=poll_seconds)
            except TimeoutError:
                now = time.monotonic()
                if now - last_heartbeat >= 3:
                    rpc("client.heartbeat", client_id=client_id)
                    last_heartbeat = now
                status = rpc("conversation.work_status", conversation_id=conversation_id)
                warnings = rpc("conversation.warnings", conversation_id=conversation_id,
                               client_id=client_id)
                for warning in warnings:
                    identity = str(warning["id"])
                    if identity not in seen_warnings:
                        emit("!!! WARNING - ENTERING A NON-STOPPABLE SEGMENT !!!\n"
                             + str(warning["message"]))
                        seen_warnings.add(identity)
                if status is not None:
                    task = status.get("task") or {}
                    progress = task.get("progress") or {}
                    state = (status.get("phase"), task.get("state"), task.get("control_request"),
                             progress.get("eta_status"))
                    if state != last_state or now - last_display >= 5:
                        emit(render_work_status(status, details=details))
                        last_state, last_display = state, now
            except KeyboardInterrupt:
                stop_count += 1
                rpc("conversation.stop", conversation_id=conversation_id, hard=stop_count >= 2)
                emit("Hard stop requested." if stop_count >= 2 else
                     "Safe stop requested. Press Ctrl+C again to request a hard stop.")
    finally:
        # On a connection failure, lease expiry handles abandoned temporary work.
        executor.shutdown(wait=False, cancel_futures=True)
