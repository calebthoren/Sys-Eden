# Sys Eden — Development Roadmap

> **Document role:** Canonical implementation roadmap  
> **Status:** Roadmap v1.2 — storage budgets and minimal VM target incorporated  
> **Depends on:** `vision.md`, `architecture.md`, `system_rules.md`, `reports.md`  
> **Planning horizon:** September 2026 through approximately January 2027  
> **Goal:** Produce a genuinely useful Windows MVP, not a complete final product

---

# 1. Purpose

## Implementation checkpoint — 2026-09-19

Phase 0 and Milestone 1 have passed their functional acceptance checks:
configuration and independent storage budgets, structured logging, SQLite/WAL and
transactional sessions, packaged Alembic baseline, in-process async events,
fake-provider health, and CLI bootstrap. Validation: 15 tests, Ruff, Pyright,
`uv sync`, CLI help/health, package build, and isolated packaged bootstrap.
Milestone 2, read-only Windows inspection, has passed its acceptance criteria.
The `eden inspect` surface now covers system, CPU, RAM, GPU, storage, network,
processes, services, startup items, drivers, installed software, recent events,
recent crashes, and boot evidence. Collectors return typed domain models with
separate concise human, curated `--details`, and structured `--json` output.
Unavailable or unsupported values remain explicit, partial-source failures are
preserved as warnings, and derived findings are labeled as observations rather
than diagnoses.

The Windows adapter provides bounded, allowlisted generic CIM and Event Log read
interfaces and a side-effect-free uninstall-registry reader. Event and boot
queries use provider scoping where Windows reuses numeric event IDs. Crash
collection excludes unrelated Windows Error Reporting records and does not assign
generic WER parameters a meaning outside known report schemas. All inspection
runs in the current user's context, performs no mutation or external IP lookup,
and does not grant a model administrator execution. Validation covers 46 tests,
Ruff, Pyright, live collector smoke tests, and a structured all-component
snapshot.

A focused post-acceptance inspection capability audit completed on 2026-09-19.
It replaced the 32-bit video-controller memory field with DXGI plus a fixed
installed-vendor inventory fallback, added direct service dependencies,
filesystem delete-notification configuration, sampled adapter throughput and
error counters, and location-independent Wi-Fi quality. Storage reliability and
BitLocker providers were denied to the current user and remain behind typed
interfaces for the planned System Service. Location-sensitive SSID access remains
subject to Windows location consent. The audit implementation is validated by 57
tests, Ruff, Pyright, and live normal-user inspection smoke checks.

The Milestone 3 implementation, structured reports and knowledge history, has
passed its functional acceptance criteria and is ready for the project commit.
Reports are validated AI-native domain objects
stored transactionally in SQLite through a dedicated repository. The aggregate
preserves lifecycle state/status, priority and activity, purpose/component tags,
observations, hypotheses, evidence references, five-dimensional confidence
history, verification results, one primary chain, and typed report
relationships. Lifecycle validation rejects inconsistent closure and prevents a
report from becoming Resolved without passing verification. Updates use
optimistic revisions so stale writers cannot silently overwrite newer history.

Alembic revision `0002` owns the normalized report tables. Fresh databases and
revision `0001` databases upgrade to the current schema after a verified,
revision-specific SQLite backup; unknown future revisions remain untouched.
Metadata-first repository search supports text, lifecycle, priority, tag, and
chain filters. `eden report list`, `eden report show`, and `eden report export`
expose concise listings, generated human views, compact AI retrieval capsules,
and portable canonical JSON. Exports refuse to overwrite an existing file.

Validation covers 64 tests, Ruff, Pyright, CLI help/report-command smoke checks,
and a package build. Milestone 4, local model integration, is next after this
changeset is committed. The repository retains the initial `src/sys_eden/`
package spelling.


This roadmap turns the Sys Eden architecture into an implementation sequence.

It intentionally avoids planning every future feature in detail.

The project should move milestone by milestone, keeping the system runnable and testable as early as possible.

The core MVP must prove:

```text
User concern
    ↓
Evidence
    ↓
Diagnosis / research
    ↓
Confidence
    ↓
Plan
    ↓
Approval
    ↓
Execution
    ↓
Verification
    ↓
Report / memory
    ↓
Monitoring
```

If that loop works reliably on real Windows problems, Sys Eden has become a real product rather than a design exercise.

---

# 2. Development Principles

## 2.1 Build vertically

Prefer complete small workflows over many disconnected subsystems.

Good:

> inspect one Windows issue → plan → approve → execute → verify → report

Poor:

> build twenty collectors, ten agents, and a UI before one problem can be solved end-to-end

## 2.2 Keep the repository runnable

Every milestone should leave the project in a working state.

## 2.3 Use tests before broad authority

Do not widen mutation capability faster than the test infrastructure can validate it.

## 2.4 Use the VM before risky host testing

Destructive integration testing belongs in VMware whenever possible.

## 2.5 Docs support implementation

Canonical docs should change when architecture or behavior changes.

Do not write speculative documentation merely to delay implementation.

---

# 3. Four-Month Target

The current focused development window is approximately:

**September 2026 → January 2027**

The target is not feature completeness.

The target is a useful MVP with:

- local reasoning,
- Windows inspection,
- structured tasks,
- risk-aware planning,
- controlled execution,
- verification,
- structured reports,
- memory/history,
- boot observation,
- targeted monitoring,
- and repeatable testing.

---

# 4. Phase 0 — Repository Preparation

## Goal

Create a clean development environment and source layout.

## Deliverables

- `pyproject.toml`
- `uv.lock`
- Python 3.13 environment
- `src/syseden/`
- `tests/`
- `migrations/`
- `data/` ignored by Git
- Ruff
- Pyright
- pytest
- basic configuration loader
- basic structured logging
- initial GitHub workflow if useful

## Acceptance

```powershell
uv sync
uv run pytest
uv run ruff check .
uv run pyright
```

all complete successfully.

---

# 5. Milestone 1 — Executable Core Skeleton

## Goal

Create the smallest runnable Eden application.

## Implement

- application bootstrap,
- configuration,
- SQLite engine,
- SQLAlchemy session/repository pattern,
- Alembic baseline migration,
- event bus,
- basic health service,
- CLI with Typer,
- fake model provider.

## Commands

```text
eden --help
eden health
```

## `eden health`

Should report at least:

- Core status,
- database status,
- configuration status,
- model-provider status,
- data directory.

## Acceptance

The application launches cleanly from a fresh checkout and all tests pass.

The initial configuration can represent independent budgets for models,
reports/database, logs/cache, telemetry, and free-space reserve without
hard-coding them into business logic.

---

# 6. Milestone 2 — Read-Only Windows Inspection

## Goal

Let Eden safely understand the local machine.

## Initial collectors

- OS/build,
- uptime,
- CPU,
- RAM,
- GPU,
- storage,
- network adapters,
- processes,
- services,
- startup items,
- drivers,
- installed software,
- Event Viewer basics,
- recent crashes.

## Interfaces

Implement both:

- specialized collectors,
- generic read interfaces.

## CLI

```text
eden inspect
eden inspect cpu
eden inspect gpu
eden inspect services
eden inspect events
```

## Acceptance

Eden can produce a structured system snapshot without mutation or administrator-level AI execution.

---

# 7. Milestone 3 — Structured Reports and Knowledge History

## Goal

Create durable AI-native report storage before Eden begins making meaningful changes.

## Implement

- Report domain model,
- SQLite report persistence,
- observations,
- hypotheses,
- evidence references,
- confidence history,
- report status/state,
- tags,
- relationships,
- chains,
- compact AI retrieval capsule,
- JSON export,
- generated human summary,
- search/filter CLI.

## CLI

```text
eden report list
eden report show <id>
eden report export <id>
```

## Acceptance

A synthetic troubleshooting task can create a report, close it, retrieve it later, and expose both a compact AI capsule and a generated human-readable view.

---

# 8. Milestone 4 — Local Model Integration

## Goal

Connect the Core to a real local model without tying architecture to one runtime.

## Implement

- `ModelProvider` protocol,
- `FakeModelProvider`,
- first real provider adapter,
- likely Ollama,
- model health,
- model metadata,
- basic model router,
- structured Pydantic outputs,
- context builder.

## CLI

```text
eden model list
eden model health
eden chat
```

## Acceptance

Eden can:

1. inspect a supplied system snapshot,
2. reason about it through a local model,
3. return a structured diagnostic assessment,
4. explain the result conversationally.

No system mutation yet.

---

# 9. Milestone 5 — Durable Task Engine

## Goal

Move from chat responses to persistent work.

## Implement

- Task domain model,
- task state machine,
- task event history,
- durable checkpoints,
- task restart detection,
- pause,
- resume,
- cancel,
- waiting-user,
- waiting-condition,
- `recovery_required`.

## CLI

```text
eden task list
eden task show <id>
eden task pause <id>
eden task resume <id>
eden task cancel <id>
```

## Acceptance

Kill Core during a synthetic task, restart Eden, and recover the task state without relying on the old model conversation.

---

# 10. Milestone 6 — Planning, Risk, and Approval

## Goal

Implement the authority boundary before broad mutation.

## Implement

- Plan domain model,
- plan versioning,
- Confidence model,
- Capability metadata,
- basic Policy Engine,
- risk dimensions/classes,
- Approval records,
- plan-scoped approval,
- denied-plan handling,
- automation-permission storage,
- user-controlled involvement modes.

## Acceptance

A synthetic proposed mutation cannot execute unless Policy Engine determines the required approval exists.

Changing the material plan invalidates the old approval.

---

# 11. Milestone 7 — Windows System Service

## Goal

Create early boot observation and the privileged broker.

## Implement

- Windows service bootstrap,
- service install/uninstall scripts,
- startup modes,
- boot-session records,
- privileged broker,
- local IPC abstraction,
- Named Pipe transport,
- service authentication/validation,
- service health,
- lazy Core/model startup.

## CLI

```text
eden service status
eden service install
eden service start
eden service stop
```

## Acceptance

Reboot Windows and verify:

- service starts automatically in Always-On mode,
- a boot session is recorded,
- Core can retrieve the boot observation,
- service remains independent of the model runtime.

---

# 12. Milestone 8 — Controlled Mutation

## Goal

Allow Eden to safely change harmless targets.

## Initial mutation targets

Only use:

- Eden-owned test directory,
- Eden-owned registry test key,
- test fixture,
- disposable VM target.

## Implement

- typed action interface,
- execution-context selection,
- user-context executor,
- privileged service executor,
- structured execution results,
- action audit,
- preconditions,
- postconditions,
- bounded retry.

## Acceptance

Eden can:

1. generate a plan,
2. request approval,
3. perform an approved harmless mutation,
4. verify it,
5. record the execution.

No broad destructive host mutation yet.

---

# 13. Milestone 9 — Dynamic PowerShell Escape Hatch

## Goal

Preserve Eden's ability to handle Windows cases outside the typed tool catalog.

## Implement

- PowerShell adapter,
- Windows PowerShell detection,
- PowerShell 7 detection,
- script metadata,
- AST/static inspection where practical,
- Policy Engine integration,
- privileged execution through broker,
- output/error capture,
- timeout/cancel,
- verification requirement.

## Acceptance

In a safe test fixture, Eden can identify a missing capability, generate a PowerShell solution, obtain approval, execute it, and verify the result.

---

# 14. Milestone 10 — Full End-to-End Diagnostic Loop

## Goal

Create the first real Sys Eden experience.

A **minimal research capability** MAY be introduced before or during this
milestone when the selected end-to-end scenario needs current external
information. This does not require the complete mature Research subsystem yet.

Milestone 15 later hardens research into its full provider/sanitization/source
management architecture. In other words:

```text
Milestone 10: enough research to prove the vertical loop when needed
Milestone 15: mature reusable Research Layer
```

## Goal Detail

Create the first real Sys Eden experience.

## Scenario

User:

> Something on my PC is not working correctly.

Eden should:

1. inspect,
2. clarify,
3. retrieve history,
4. research if needed,
5. diagnose,
6. display confidence,
7. create plan,
8. assess risk,
9. get approval,
10. execute,
11. verify,
12. write report,
13. create monitoring if appropriate.

## Acceptance

The user should not need to perform the technical diagnosis for Eden.

This milestone is the first major MVP success gate.

---

# 15. Milestone 11 — Monitoring and Watchlist

## Goal

Give Eden useful memory across time.

## Implement

- watchlist records,
- monitoring tasks,
- lightweight periodic collectors,
- condition-bound monitoring,
- significant-event summaries,
- notification tiers,
- post-fix monitoring,
- boot trend monitoring.

## Acceptance

A resolved issue can automatically enter a defined monitoring period and later close based on evidence.

At or before this point, expose basic storage accounting so Eden can report
usage by category and honor user-configured budgets before telemetry begins
growing materially.

---

# 16. Milestone 12 — Targeted Performance Telemetry

## Goal

Prove one high-value performance workflow.

Recommended first target:

**gaming performance**

Possible telemetry:

- CPU/GPU usage,
- temperatures,
- RAM/VRAM,
- disk activity,
- FPS/frame time if practical,
- process activity,
- event markers.

## Storage

- SQLite metadata,
- file-based high-frequency traces,
- Parquet when justified,
- default telemetry working budget of roughly 2–5 GB,
- user-configurable telemetry budget,
- automatic summarization/pruning of low-value raw traces before unbounded growth.

## Acceptance

Eden can compare good/bad sessions and use collected evidence in diagnosis without overwhelming model context.

---

# 17. Milestone 13 — VMware Destructive Test Lab

## Goal

Safely test real Windows mutation and recovery.

## Environment

- VMware Workstation Pro,
- one thin-provisioned Windows test guest,
- one clean snapshot such as `EDEN-CLEAN`,
- target approximately 30–50 GB actual host disk use,
- no permanent duplicate AI model library in the guest,
- no persistent large telemetry/report archive in the guest.

Use scripted fault injection instead of maintaining many scenario snapshots.

Do not add SSH/WinRM/custom guest-agent architecture solely to reduce disk usage;
keep the test environment simple unless later scenarios independently require
remote-control infrastructure.

## Build

- host-side VM reset script,
- build/install/copy automation,
- fault injection,
- scenario runner,
- independent verification,
- report/result collection on the host,
- automatic reset.

## Initial scenarios

- disabled service,
- startup misconfiguration,
- registry test failure,
- broken DNS/network configuration,
- failed software state,
- application crash,
- test permission issue.

## Acceptance

A failed Eden repair cannot permanently damage the test environment; host snapshot restore always returns the VM to baseline.

---

# 18. Milestone 14 — Broaden Safe Windows Capability

After VM testing is reliable, gradually add:

- service management,
- startup management,
- package installation/removal,
- selected registry mutation,
- network diagnostics/repair,
- file cleanup,
- driver inspection/update workflows.

Each capability requires:

- metadata,
- risk classification,
- policy integration,
- tests,
- verification,
- report integration.

---

# 19. Milestone 15 — Research Layer

Research may begin earlier if implementation requires it, but the mature subsystem should include:

- provider abstraction,
- query sanitizer,
- source metadata,
- conflict representation,
- research confidence,
- local/public evidence labeling,
- private-data boundary.

## Acceptance

Eden can research a current technical problem without automatically leaking private local evidence.

---

# 20. Milestone 16 — Memory Refinement

Implement persistent:

- user preferences,
- system facts,
- behavioral observations,
- automation permissions,
- provenance,
- freshness,
- confidence,
- stale-memory handling.

## Acceptance

Eden uses relevant historical preference/context but current explicit instructions still win.

---

# 21. Milestone 17 — Skills Foundation

Only after the normal task loop is stable.

Implement:

- Skill metadata,
- versioning,
- required capabilities,
- inputs,
- risk profile,
- steps,
- verification,
- testability.

Initial Skills should be hand-authored/tested.

Self-created Skills remain later.

---

# 22. Milestone 18 — Local Web UI

Only after Core behavior is trustworthy.

Likely stack:

- FastAPI,
- React,
- TypeScript,
- Vite.

Initial UI:

- chat,
- task progress,
- plan approval,
- reports,
- watchlist,
- basic health/system overview.

Do not attempt the complete Control Center yet.

---

# 23. End-of-Window MVP Target

By the end of the focused window, Sys Eden SHOULD be able to:

- start monitoring with Windows,
- inspect the PC broadly,
- use a local AI model,
- research public technical information safely,
- diagnose a scoped real issue,
- display meaningful confidence,
- create a structured plan,
- assess risk,
- obtain approval,
- execute a controlled repair,
- survive restart where applicable,
- verify success,
- preserve an AI-native report,
- retrieve relevant history later,
- monitor the result,
- and prove destructive workflows in a resettable Windows VM.

That is enough to call the project a meaningful MVP.

---

# 24. Post-MVP Priorities

Likely order after the Core is stable:

1. broader Windows capabilities,
2. better telemetry,
3. better model routing,
4. stronger knowledge graph,
5. improved automation,
6. richer local UI,
7. Eden System Monitor / Control Center,
8. remote-control sessions,
9. advanced Skills,
10. voice,
11. Linux platform adapters.

Exact order may change based on what proves most useful.

---

# 25. Eden System Monitor / Control Center

This is a serious long-term interface direction, but intentionally post-MVP.

It may combine:

- live process monitoring,
- hardware performance,
- startup/boot history,
- services,
- drivers,
- events,
- software,
- updates,
- historical telemetry,
- system-change timeline,
- reports,
- watchlist,
- contextual AI actions.

The Core architecture should naturally feed this interface later.

Do not build a parallel monitoring backend solely for the Control Center.

---

# 26. Remote Control

Remote control is post-MVP.

Initial likely target:

- same-LAN temporary gateway,
- QR pairing,
- encrypted connection,
- authenticated real-time task/approval channel,
- automatic expiration.

Do not delay Core development for remote access.

---

# 27. Features Explicitly Deferred

Do not treat these as blockers:

- polished final desktop UI,
- full Control Center,
- graph visualization,
- remote QR control,
- voice,
- automatic BIOS flashing,
- kernel driver,
- Linux,
- macOS,
- cloud sync,
- multi-user,
- advanced self-created Skills,
- sophisticated semantic/vector database,
- broad autonomous repair without approval history.

---

# 28. Milestone Completion Rule

A milestone is complete when:

1. the capability works,
2. tests pass,
3. failure behavior is tested,
4. relevant documentation reflects reality,
5. code is committed,
6. the next milestone can build on it without known foundational breakage.

A milestone does not require perfect UI polish.

---

# 29. Architecture Escalation Rule

If implementation exposes a genuine architecture conflict:

1. stop before building around the conflict,
2. identify alternatives,
3. make the smallest durable decision,
4. update `decisions.md`,
5. update canonical documentation if needed,
6. continue coding.

Do not return to broad speculative redesign.

---

# 30. First Coding Session

After the planning docs are frozen, the first coding session should:

1. initialize `uv`,
2. create `pyproject.toml`,
3. create minimal package layout,
4. configure Ruff/Pyright/pytest,
5. add config model,
6. initialize SQLite,
7. create the first Alembic migration,
8. implement `eden health`,
9. write tests,
10. commit.

Do not begin with the AI model, Windows service, or UI.

The first goal is a boring, reliable foundation.

---

# 31. Closing Principle

The roadmap is successful if every few milestones create something visibly more capable while preserving the project's core philosophy.

The project should move from:

```text
empty repository
```

to:

```text
working local system inspector
```

to:

```text
persistent AI diagnostic agent
```

to:

```text
controlled system operator
```

to:

```text
verified, history-aware Windows companion
```

without requiring a complete rewrite at each stage.
