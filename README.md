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
uv run eden inspect os
uv run eden inspect cpu
uv run eden inspect ram
```

These return timestamped JSON results using a fixed Windows PowerShell CIM reader
in the current user's context. Requests are passed as JSON, with a 20-second
timeout and cancellation cleanup. Nothing is sent to a model or external service.
RAM inspection reports each module's manufacturer, model, part number (often the
most useful Windows/SMBIOS model identifier), physical slot, bank, capacity, current
and configured speed, form factor, and SMBIOS memory type. Firmware may leave
some identity fields blank or return generic values.
The initial generic CIM interface supports the three reviewed provider classes;
the remaining collectors and generic readers are unfinished Milestone 2 work.
