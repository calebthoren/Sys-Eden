"""Freeze a built wheel for isolated manual testing while development continues."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = ROOT / "data" / "milestone5-candidates"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare() -> str:
    wheels = sorted((ROOT / "dist").glob("sys_eden-*.whl"), key=lambda p: p.stat().st_mtime)
    if not wheels:
        raise ValueError("Build a wheel first: uv build --offline")
    wheel = wheels[-1]
    wheel_hash = digest(wheel)
    candidate_id = wheel_hash[:16]
    directory = CANDIDATES / candidate_id
    manifest_path = directory / "candidate.json"
    if not manifest_path.exists():
        app_directory = directory / "app"
        app_directory.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(wheel) as archive:
            for member in archive.infolist():
                target = (app_directory / member.filename).resolve()
                if not target.is_relative_to(app_directory.resolve()):
                    raise ValueError("Wheel contains a path outside the candidate directory")
            archive.extractall(app_directory)
        files = {
            path.relative_to(app_directory).as_posix(): digest(path)
            for path in sorted(app_directory.rglob("*")) if path.is_file()
        }
        if "sys_eden/ascii-tree-small.txt" not in files:
            raise ValueError("Built wheel is missing the CLI tree asset")
        manifest = {
            "candidate_id": candidate_id,
            "created_at": datetime.now(UTC).isoformat(),
            "wheel": wheel.name,
            "wheel_sha256": wheel_hash,
            "files": files,
        }
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    validate(candidate_id)
    (CANDIDATES / "current.txt").write_text(candidate_id + "\n", encoding="ascii")
    return candidate_id


def validate(candidate_id: str | None = None) -> tuple[str, Path]:
    if candidate_id is None:
        pointer = CANDIDATES / "current.txt"
        if not pointer.exists():
            raise ValueError("Prepare a test candidate first")
        candidate_id = pointer.read_text(encoding="ascii").strip()
    if len(candidate_id) != 16 or any(c not in "0123456789abcdef" for c in candidate_id):
        raise ValueError("Candidate ID must be the 16-character ID printed by prepare")
    directory = CANDIDATES / candidate_id
    manifest = json.loads((directory / "candidate.json").read_text(encoding="utf-8"))
    if manifest["candidate_id"] != candidate_id:
        raise ValueError("Candidate manifest does not match the requested candidate")
    app_directory = directory / "app"
    for relative, expected in manifest["files"].items():
        path = (app_directory / relative).resolve()
        if not path.is_relative_to(app_directory.resolve()) or digest(path) != expected:
            raise ValueError("Candidate files changed; prepare a new build before testing")
    return candidate_id, directory


def candidate_environment(directory: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment["EDEN_DATA_DIRECTORY"] = str(directory / "runtime")
    environment["EDEN_MODEL__PROVIDER"] = "ollama"
    environment["EDEN_MODEL__DEFAULT_MODEL"] = "qwen3.5:9b"
    environment["PYTHONPATH"] = str(directory / "app") + (
        os.pathsep + environment["PYTHONPATH"] if environment.get("PYTHONPATH") else ""
    )
    environment["PYTHONUTF8"] = "1"
    return environment


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", help="Pin the ID printed by prepare")
    parser.add_argument("action", choices=("prepare", "open", "start", "stop", "status", "command"))
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    try:
        if args.action == "prepare":
            candidate_id = prepare()
            print(f"Prepared Milestone 5 test candidate: {candidate_id}")
            print("Open the test client (choose Start Core explicitly):")
            print(
                ".\\.venv\\Scripts\\python.exe scripts/milestone5_candidate.py "
                f"--candidate {candidate_id} open"
            )
            return 0
        candidate_id, directory = validate(args.candidate)
        cli_arguments = (
            [] if args.action == "open" else args.arguments if args.action == "command"
            else ["core", args.action]
        )
        if args.action == "command" and not cli_arguments:
            parser.error("command requires an Eden command, such as storage status --details")
        if args.action != "command" and args.arguments:
            parser.error("only command accepts additional Eden arguments")
        # stderr keeps command --json stdout parseable.
        print(f"Milestone 5 candidate {candidate_id}; isolated test data.", file=sys.stderr)
        result = subprocess.run(
            [sys.executable, "-c", "from sys_eden.cli import app; app()", *cli_arguments],
            cwd=ROOT,
            env=candidate_environment(directory),
            check=False,
        )
        return result.returncode
    except (OSError, ValueError, KeyError) as error:
        print(f"Candidate unavailable: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
