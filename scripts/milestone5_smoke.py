"""Check a packaged candidate using separate data and real local inference."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from milestone5_candidate import ROOT, candidate_environment, validate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate")
    args = parser.parse_args()
    candidate_id, directory = validate(args.candidate)
    profile = directory / f"verification-{uuid4().hex[:8]}"
    environment = candidate_environment(directory)
    environment["EDEN_DATA_DIRECTORY"] = str(profile)
    checks: list[dict[str, Any]] = []

    def cli(*arguments: str, expected_exit: int = 0) -> dict[str, Any]:
        result = subprocess.run(
            [sys.executable, "-c", "from sys_eden.cli import app; app()", *arguments],
            cwd=ROOT, env=environment, capture_output=True, text=True,
            encoding="utf-8", timeout=240, check=False,
        )
        payload = json.loads(result.stdout)
        if result.returncode != expected_exit:
            error = payload.get("error") or {}
            raise ValueError(
                f"{arguments[0]}: expected exit {expected_exit}, got {result.returncode}; "
                f"code={error.get('code', 'unknown')}"
            )
        if payload.get("eden_json") != 1:
            raise ValueError("CLI response did not use the versioned JSON envelope")
        return payload

    def passed(name: str, started: float) -> None:
        checks.append({"check": name, "passed": True,
                       "seconds": round(time.monotonic() - started, 2)})
        print(f"PASS: {name}", flush=True)

    succeeded = False
    try:
        started = time.monotonic()
        status = cli("core", "status", "--json")
        assert status["data"]["state"] == "stopped"
        passed("Client status does not start Core", started)

        started = time.monotonic()
        assert cli("core", "start", "--json")["data"]["state"] == "running"
        assert cli("core", "start", "--json")["data"]["state"] == "running"
        passed("Packaged Core starts through named pipe and start is idempotent", started)

        started = time.monotonic()
        assert cli("model", "health", "--json")["data"]["available"]
        models = cli("model", "list", "--json")["data"]
        assert any(m["model_id"] == "qwen3.5:9b" and m["local"] for m in models)
        passed("Existing local model is available without downloading another model", started)

        started = time.monotonic()
        inspected = cli("inspect", "cpu", "--only", "cpu", "--json")
        assert len(inspected["data"]) == 1 and inspected["data"][0]["success"]
        passed("Real read-only CPU inspection and JSON output", started)

        started = time.monotonic()
        answer = cli("chat", "For a generated test, explain what a computer fan does in one sentence. "
                     "This is a general question; no machine inspection is requested.",
                     "--save", "--json")["data"]
        assert answer["operation"] == "chat" and answer["response"].strip()
        conversation_id = answer["conversation_id"]
        before = cli("chat", "show", conversation_id, "--json")["data"]
        assert len(before["messages"]) == 2
        assert cli("task", "list", "--json")["data"] == []
        passed("Real local conversational inference saves a chat without creating a task", started)

        started = time.monotonic()
        cli("core", "stop", "--json")
        cli("core", "start", "--json")
        after = cli("chat", "show", conversation_id, "--json")["data"]
        assert after["messages"] == before["messages"]
        resumed = cli("chat", "Now explain its purpose in three words.",
                      "--conversation", conversation_id, "--json")["data"]
        assert resumed["conversation_id"] == conversation_id and resumed["response"].strip()
        passed("Saved conversation survives separate Core process restart and resumes", started)

        started = time.monotonic()
        diagnosis = cli("chat", "Inspect only the CPU and explain any limitations of the evidence.",
                        "--only", "cpu", "--json")["data"]
        assert diagnosis["operation"] == "diagnosis" and diagnosis["diagnostic_component"] == "cpu"
        tasks = cli("task", "list", "--json")["data"]
        assert any(task["id"] == diagnosis["task_id"] for task in tasks)
        passed("Real CPU evidence produces a local diagnosis and linked durable task", started)

        started = time.monotonic()
        assert cli("storage", "status", "--details", "--json")["data"]
        error = cli("inspect", "invalid-component", "--json", expected_exit=1)
        assert error["status"] == "error" and error["error"]["code"] == "request.invalid"
        passed("Storage attribution and invalid-command JSON remain usable", started)
        succeeded = True
    except (AssertionError, ValueError, OSError, subprocess.TimeoutExpired) as error:
        # Do not publish raw model answers, inspection output, or private paths.
        checks.append({"check": "smoke run", "passed": False,
                       "failure_type": type(error).__name__})
        print(f"FAIL: {type(error).__name__}; review the failing step locally.", file=sys.stderr)
    finally:
        try:
            cli("core", "stop", "--json")
        except (ValueError, OSError, subprocess.TimeoutExpired):
            print("Verification Core stop could not be confirmed.", file=sys.stderr)
            succeeded = False
        profile.mkdir(parents=True, exist_ok=True)
        result = {"candidate_id": candidate_id, "generated_at": datetime.now(UTC).isoformat(),
                  "success": succeeded, "checks": checks,
                  "scope": "Separate generated profile; live local model and CPU evidence. "
                           "No raw model answers or inspection payloads included."}
        (profile / "smoke-result.json").write_text(
            json.dumps(result, indent=2) + "\n", encoding="utf-8"
        )
        print(f"Sanitized evidence: {profile.relative_to(ROOT) / 'smoke-result.json'}")
    return 0 if succeeded else 1


if __name__ == "__main__":
    raise SystemExit(main())
