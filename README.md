# Sys Eden

Local-first Windows system companion. Milestones 1 through 4 provide a runnable
Core, broad read-only Windows inspection, durable structured reports, and local
structured diagnostic reasoning through a replaceable model provider. Milestone
5 has passed functional and owner visual acceptance: durable tasks, restart
recovery, conversation persistence, storage attribution, unified chat/diagnostics,
and the separate Core/CLI connection are implemented. Final validation passes
239 tests, Ruff, Pyright, and all eight packaged live checks. Publication and
milestone signoff are tracked in GitHub #11/#1. Milestone 6 objective issues are
ready under [overview #12](https://github.com/calebthoren/Sys-Eden/issues/12), with
implementation not started. Use the
[Milestone 5 test handoff](docs/Sys_Eden_milestone_5_acceptance_v1.0.md) to run an
isolated frozen candidate while development continues. Progress is tracked in
[GitHub overview #1](https://github.com/calebthoren/Sys-Eden/issues/1); the
[issue workflow](docs/Sys_Eden_issue_tracking_v1.0.md) explains status and closure.

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

Milestone 5 Core and client lifecycle commands:

```powershell
uv run eden core status
uv run eden core start
uv run eden task list
uv run eden chat list
uv run eden storage status --details
uv run eden core stop
```

Core runs as a separate normal-user process and owns SQLite access for the new
Milestone 5 task, conversation, and storage paths. On Windows, CLI clients use
an authenticated user-scoped named pipe. Closing a CLI does not stop Core.
When `eden` is opened in a TTY with Core running, typing in the bottom composer
sends a chat message and enters a dedicated conversation thread. That screen
shows the conversation ID once and keeps its transcript separate; returning home
leaves ongoing work visible as a working/completed Activity entry. Typing `/`
opens a five-row prefix-filtered command palette with arrow navigation. Up/down
otherwise moves within wrapped text; Down at the composer's bottom edge reaches
the button row below it and Up returns to the composer. Left/right
selects buttons on that row. `Esc` returns from subviews and leaves a conversation
context only when the draft is empty; it never clears typed text. The dependency-free interactive
client owns an alternate terminal screen with a boxed status section and dark,
borderless composer with a high-contrast typing cursor, then restores the original shell when it exits. Eden has
one CLI style.

Conversation headers use rounded corners and dark gray characters on black.
The characters use a lighter gray to balance their appearance against the
composer fill. Navigation buttons use that same character color. The transcript
fills the rows between that header and the composer, and each mouse-wheel event
scrolls two wrapped lines. Short conversations start directly below the header,
with unused space below the messages. System confirmations such as save/pin notices appear
at their point in the conversation and scroll away with it.

Bootstrap configuration uses validated defaults and `EDEN_` environment overrides,
including `EDEN_DATA_DIRECTORY` and `EDEN_STORAGE__MODELS_BUDGET_GB`.
Storage budgets are independent; automatic rebalancing defaults to disabled.
Budget enforcement belongs to subsequent storage work. Configuration loading does
not create directories. Development runtime data belongs in ignored `data/`.
Do not put credentials in configuration or application log messages.

`uv run eden health` initializes the development SQLite database through packaged
Alembic migrations and returns JSON health for Core, configuration, database, and
the configured model provider. Failed checks return exit code 1. Health logs
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

Structured report retrieval commands:

```powershell
uv run eden report list
uv run eden report list --status resolved --component gpu
uv run eden report show <id>
uv run eden report show <id> --capsule
uv run eden report show <id> --json
uv run eden report export <id>
uv run eden report export <id> --output report.json
```

Reports are validated structured domain objects persisted transactionally in
SQLite. They retain lifecycle state/status, tags, observations, hypotheses,
evidence references, confidence history, verification, one primary chain, and
typed relationships. Resolved reports require passing verification. Repository
updates use optimistic revisions, and metadata-first search can filter without
loading complete report aggregates. Human views, compact AI capsules, and JSON
exports are generated from the same canonical data. Export-to-file refuses to
overwrite an existing path.

Local model commands:

```powershell
uv run eden model health
uv run eden model list
uv run eden model list --json
uv run eden chat "Does this system summary show anything concerning?"
uv run eden chat "Assess this GPU state" --component gpu
uv run eden chat "Assess this saved snapshot" --snapshot snapshot.json --json
```

The default provider is Ollama on the loopback-only endpoint
`http://127.0.0.1:11434`; the reference development model is `qwen3.5:9b`.
Override settings with `EDEN_MODEL__...` variables such as
`EDEN_MODEL__DEFAULT_MODEL`, `EDEN_MODEL__ROUTING_PREFERENCE`, and
`EDEN_MODEL__REQUEST_TIMEOUT_SECONDS`. `EDEN_MODEL__PROVIDER=fake` selects the
deterministic development provider.

`eden chat` collects one read-only live inspection component by default, or reads
a supplied JSON snapshot. It builds bounded, origin-labeled context, selects an
installed local model, requires a validated `DiagnosticAssessment`, and displays
the result without executing any recommendation. Cloud-managed Ollama models and
non-loopback endpoints are blocked. Model errors use stable structured codes and
do not disable inspection, reports, or database health.
