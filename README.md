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
uv run eden inspect gpu
uv run eden inspect storage
uv run eden inspect network
uv run eden inspect processes
uv run eden inspect services
uv run eden inspect startup
uv run eden inspect drivers
uv run eden inspect software
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

System, CPU, RAM, GPU, storage, and network use the shared typed
model/collector/formatter architecture. GPU fields that standard Windows CIM
cannot attribute reliably (modern dedicated VRAM, utilization, temperature,
clocks, and power) remain unavailable. Storage exposes standard health and
operational status; SMART temperature/error counters, TRIM, and encryption state
remain unavailable until a reliable read provider is added.
Network inspection uses local adapter/configuration/route data and performs no
external public-IP lookup. Standard CIM does not reliably expose Wi-Fi SSID and
signal or live per-adapter throughput on every system, so those fields may be
unavailable.
Process inspection ranks the 20 most resource-relevant processes by normalized
CPU and private memory in normal output; `--details` expands to 100 and adds
available paths, command lines, parent/start/thread/handle information, and I/O.
Protected fields and process owners may be unavailable. Service inspection keeps
normal rows compact while `--details` adds paths, accounts, descriptions, PIDs,
startup behavior, service types, and exit codes. Dependency relationships are
reserved in the schema but unavailable from the current generic reader.
Startup inspection reports registered startup commands but leaves enablement,
publisher/signature, and impact unavailable where Win32 does not expose them.
Driver inventory correlates signed-driver records with Plug and Play device
status; the human view shows 50 records while `--json` contains the full result.
Installed software is read from machine/user uninstall registry keys without
using `Win32_Product`; the human view shows 100 records while `--json` contains
the full result. Registry install dates are preserved as calendar dates.
The remaining collectors and broader generic readers are unfinished Milestone 2 work.
