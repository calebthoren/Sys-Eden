"""Shared plain-language presentation of Core's durable progress snapshots."""

from __future__ import annotations

from typing import Any


def phase_label(phase: str) -> str:
    return phase.replace("_", " ").strip().capitalize()


def render_work_status(status: dict[str, Any], *, details: bool = False) -> str:
    task = status.get("task") or {}
    progress = task.get("progress") or {}
    phase = phase_label(progress.get("current_phase") or status.get("phase", "Working"))
    pieces = [f"{phase}: {status.get('detail', progress.get('current_operation', 'Working.'))}"]
    elapsed = status.get("elapsed_seconds")
    if elapsed is not None:
        pieces.append(f"Elapsed {float(elapsed):.0f}s")
    completed = progress.get("completed_major_steps") or []
    if completed:
        pieces.append("Completed: " + ", ".join(phase_label(item) for item in completed))
    state = task.get("state")
    if state in {"paused", "waiting_user", "waiting_condition", "recovery_required"}:
        pieces.append(phase_label(state))
    if progress.get("waiting_reason"):
        pieces.append("Waiting: " + str(progress["waiting_reason"]))
    if progress.get("throttled"):
        pieces.append("Throttled")
    if progress.get("eta_status") == "range":
        minimum, maximum = float(progress["eta_min_seconds"]), float(progress["eta_max_seconds"])
        operation_elapsed = float(status.get("operation_elapsed_seconds", 0))
        if operation_elapsed >= maximum:
            pieces.append("ETA unavailable (this operation exceeded the previous range)")
        else:
            pieces.append(f"Current-step ETA about {max(0, minimum - operation_elapsed):.0f}–"
                          f"{maximum - operation_elapsed:.0f}s")
    elif progress.get("eta_status") == "estimating":
        pieces.append("ETA estimating")
    else:
        pieces.append("ETA unavailable")
    if details:
        operation = progress.get("technical_operation") or status.get("technical_operation") or {}
        for key, label in (("provider", "Provider"), ("model_id", "Model"), ("tool", "Tool"),
                           ("sanitized_command", "Command")):
            if operation.get(key):
                pieces.append(f"{label}: {operation[key]}")
        if progress.get("eta_basis"):
            pieces.append(str(progress["eta_basis"]))
    return " | ".join(pieces)
