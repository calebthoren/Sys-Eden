# Sys Eden

Local-first Windows system companion. Milestone 2 read-only inspection is complete;
Milestone 3 structured reports and knowledge history is next in roadmap order.

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
uv run eden inspect events
uv run eden inspect crashes
uv run eden inspect boot
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
model/collector/formatter architecture. GPU capacity uses DXGI rather than the
32-bit `Win32_VideoController.AdapterRAM` field, with installed NVIDIA driver
inventory as a capacity fallback/override and an explicit source label. GPU
utilization, temperature, clocks, VRAM use, and power remain unavailable pending
a later cross-vendor telemetry design.

Storage exposes standard health and operational status plus detailed filesystem
delete-notification configuration. The latter is not proof of per-device TRIM
support. Storage reliability counters and BitLocker state are unavailable to the
normal-user providers on the development machine; typed provider boundaries are
reserved for the planned System Service.

Network inspection uses local adapter/configuration/route data and performs no
external public-IP lookup. A short sample of Windows adapter counters produces
derived receive/send throughput, while details include direct cumulative
error/discard counters and the sample duration. The location-independent Native
Wi-Fi quality API supplies signal and link rates when supported. SSID remains
unavailable when Windows location consent is disabled; Eden does not change that
privacy setting.
Process inspection ranks the 20 most resource-relevant processes by normalized
CPU and private memory in normal output; `--details` expands to 100 and adds
available paths, command lines, parent/start/thread/handle information, and I/O.
Protected fields and process owners may be unavailable. Service inspection keeps
normal rows compact while `--details` adds paths, accounts, descriptions, PIDs,
startup behavior, service types, exit codes, dependencies, and dependent
services.
Startup inspection reports registered startup commands but leaves enablement,
publisher/signature, and impact unavailable where Win32 does not expose them.
Driver inventory correlates signed-driver records with Plug and Play device
status; the human view shows 50 records while `--json` contains the full result.
Installed software is read from machine/user uninstall registry keys without
using `Win32_Product`; the human view shows 100 records while `--json` contains
the full result. Registry install dates are preserved as calendar dates.
Event inspection is bounded to recent critical, error, and warning records from
the System and Application logs. Crash inspection groups recent application,
hang, crash-class Windows Error Reporting, and LiveKernel records without
assigning meanings to provider-specific fields that Windows does not define for
that report type. Boot inspection uses provider-scoped event IDs so unrelated
events with the same numeric ID are not treated as boot evidence. Detailed event
output remains structured and does not expose raw XML.

The Milestone 2 snapshot is built through typed specialized collectors plus
bounded generic CIM and Event Log readers and a side-effect-free registry
inventory reader. It runs as the current user and performs no mutation or
administrator-level AI execution. Values that need a more reliable provider,
extra permission, or vendor telemetry remain explicitly unavailable.
See the [read-only inspection capability audit](docs/Sys_Eden_inspection_capability_audit_v1.0.md)
for provider, permission, live-result, and deferral decisions.
