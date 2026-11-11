"""Small lifecycle hint for clients when Core's RPC endpoint is unreachable."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4


def record_presence(directory: Path, *, state: str) -> None:
    """Core alone writes this hint; durable recovery authority remains in SQLite."""
    target = directory / ".core-state.json"
    temporary = target.with_name(f".core-state-{uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps({"schema": 1, "state": state}), encoding="utf-8")
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


def known_stopped(directory: Path) -> bool:
    try:
        hint = json.loads((directory / ".core-state.json").read_text(encoding="utf-8"))
        return isinstance(hint, dict) and hint.get("schema") == 1 and hint.get("state") == "stopped"
    except FileNotFoundError:
        # A new installation has no runtime yet. Existing keys identify older or
        # interrupted runtimes whose lifecycle cannot be confirmed.
        return not (directory / ".core-auth").exists() and not (directory / "eden.db").exists()
    except (OSError, ValueError):
        return False
