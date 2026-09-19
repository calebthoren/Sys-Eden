# Sys Eden

Local-first Windows system companion, currently implementing Milestone 2 (inspection).

Read [AGENTS.md](AGENTS.md) and the versioned canonical documents in [docs](docs/).
The roadmap owns implementation order.

Development requires Python 3.13 and uv:

```powershell
uv sync
uv run pytest
uv run ruff check .
uv run pyright
uv run eden --help
```

Bootstrap configuration uses validated defaults and `EDEN_` environment overrides,
including `EDEN_DATA_DIRECTORY` and `EDEN_STORAGE__MODELS_BUDGET_GB`.
Storage budgets are independent; automatic rebalancing defaults to disabled.
Budget enforcement belongs to subsequent storage work. Configuration loading does
not create directories. Development runtime data belongs in ignored `data/`.
Do not put credentials in configuration or application log messages.

`uv run eden health` initializes the development SQLite database through packaged
Alembic migrations and returns JSON health for Core, configuration, database, and
the explicitly fake model provider. Failed checks return exit code 1. Health logs
are JSON on stderr. SQLite uses WAL, foreign keys, and a five-second busy timeout.
Existing unknown schema versions are rejected; a verified SQLite backup is retained
before baseline migration. Sessions commit on success and roll back on failure.
The in-process async event bus has bounded delivery and propagates handler failures.

Initial read-only inspection commands:

```powershell
uv run eden inspect
uv run eden inspect system
uv run eden inspect cpu
uv run eden inspect ram
uv run eden inspect ram --details
uv run eden inspect system --json
```

Default inspection output is a concise human view grouped into identity,
configuration, current state, health, and observations. `--details` collects and
shows a curated diagnostic/inventory view; it is not a raw WMI dump. `--json`
serializes the same typed Pydantic result, preserving unavailable values as `null`.
The old `os` spelling remains an alias for `system`.

The fixed Windows PowerShell CIM reader runs in the current user's context.
Requests are allowlisted, passed as JSON, and bounded by a 20-second timeout with
cancellation cleanup. Nothing is sent to a model or external service. RAM serial
numbers are queried only with `--details`, and known placeholder serials are shown
as unavailable. Firmware or drivers may leave other values blank or generic.

System, CPU, and RAM use the shared typed model/collector/formatter architecture.
The remaining collectors and broader generic readers are unfinished Milestone 2 work.
