# Sys Eden — Development Roadmap

> **Document role:** Canonical implementation roadmap  
> **Status:** Roadmap v1.2 — storage budgets and minimal VM target incorporated  
> **Depends on:** `vision.md`, `architecture.md`, `system_rules.md`, `reports.md`, `conversations.md`
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
passed its functional acceptance criteria and is committed.
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

Validation covered 64 tests, Ruff, Pyright, CLI help/report-command smoke checks,
and a package build. The repository retains the initial `src/sys_eden/` package
spelling.

Milestone 4, local model integration, passed its functional acceptance criteria
on 2026-09-22. Core now depends on an asynchronous `ModelProvider` contract for
health, discovery, and generation. Deterministic fake and real local Ollama
providers implement the same typed boundary. The Ollama adapter uses a
loopback-only endpoint, disables proxy inheritance and redirects, applies bounded
timeouts, exposes installed/loaded model metadata, refuses cloud-managed model
entries, and maps failures to structured model error codes.

The basic router filters installed models by locality, capabilities, estimated
context fit, configured model preference, and speed/strength preference. The
context builder creates bounded, origin-labeled sections and treats user/system/
report content as untrusted data rather than authority. Diagnostic inference is
validated against a Pydantic `DiagnosticAssessment` containing observations,
hypotheses, unknowns, next checks, five-dimensional confidence, and a human
explanation. `eden model health`, `eden model list`, and `eden chat` expose the
vertical slice without mutation authority.

The real acceptance run used Ollama 0.34.3 and local `qwen3.5:9b` (Q4_K_M,
approximately 6.6 GB) under the configured 12 GB model budget. Eden collected a
read-only system snapshot, routed it locally, rejected an initial malformed
thinking-mode response, then passed after the adapter explicitly disabled
separate thinking for schema-bound output. The validated assessment used 1,368
prompt tokens and 772 completion tokens and completed in about 11 seconds with
the model loaded. Validation covers 73 tests, Ruff, Pyright, model/CLI smoke
checks, the real structured diagnostic run, and a package build.

Milestone 5 is complete with functional and owner visual acceptance. Durable task state/recovery, Core/client
separation, unified chat-to-diagnostics routing, temporary/saved conversations,
report contributions/retention review, storage attribution, and the interactive
CLI are implemented and committed. Final validation passes 239 tests, Ruff,
Pyright, and all eight live packaged checks on approved candidate
`896c70ed7b94cc99`. The source distribution/wheel build succeeds. See
`Sys_Eden_milestone_5_acceptance_v1.0.md` for all 35 acceptance items mapped to
GitHub issues and the evidence. The verified source and issue templates are
published on GitHub; final signoff is recorded in #11/#1. Milestone 6 is next;
its objective issues are Not started.


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

Move from chat responses to persistent work and finalize the coherent MVP CLI
design that will carry the project until the local web UI milestone.

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
- `recovery_required`,
- durable progress events with start time, current phase, completed major steps,
  waiting/throttled state, and current operation,
- monotonic elapsed-time tracking,
- evidence-based ETA ranges and updates when estimation is supportable,
- an explicit `estimating`/unavailable state instead of false-precision countdowns,
- sanitized technical-operation details suitable for later execution traces,
- a prominent pre-step warning for safe-boundary-only/non-stoppable segments,
- one reusable progress representation for CLI now and local UI streaming later,
- a finalized MVP CLI design system covering layout, status language, colors,
  tables, spinners/progress indicators, warnings, errors, and detail disclosure,
- readable no-color/non-interactive behavior and stable JSON output for scripts,
- a stable versioned JSON envelope with structured errors, associations, and
  explicit synthetic provenance,
- one consistent CLI presentation with no simple/stylized mode toggle,
- a concise English default view with optional expandable/following technical
  details for the current provider, tool, or command,
- an interactive CLI home/client screen when `eden` is launched in a terminal,
- a full-terminal application using the alternate screen, with home
  actions navigable by arrows and Enter and the original shell restored on exit,
- a persistent interactive prompt where ordinary text starts or continues an
  Eden conversation and `/commands` expose discoverable navigation/actions,
- a dedicated transcript screen per conversation, with the conversation ID in
  its header and Home retaining only working/completed activity summaries,
- a prefix-filtered slash-command palette showing at most five commands at once
  with arrow navigation through additional matches,
- conversation identities and a repository for resumable chat transcripts,
- visible temporary, saved, and report-linked conversation states,
- privacy-first temporary chat as the default for unclassified conversation,
- client-owned temporary chats retained across thread/home navigation until
  that CLI client closes, with exit warning and disconnect-lease cleanup,
- persistent chats that can be listed, resumed, exported, and deleted without
  requiring a report,
- separate report-to-conversation links so reports can reference full chat
  history without embedding raw transcripts,
- bounded recent-message context and rolling conversation summaries for
  resumption after Core restart,
- report contribution summaries only when a conversation adds material
  information, with report views separating core information, supporting
  information, and linked artifacts,
- Full, Compact, and Deleted transcript storage states with visible status,
- manual conversation compact/pin operations and a closed-report retention
  checkpoint that preserves unique evidence before recommending cleanup,
- initial read-only storage attribution through `eden storage status` with an
  optional `--details` view, including reports, conversations, memory,
  attachments, indexes, database overhead, and estimated reclaimable space,
- home/menu navigation for chat, inspection, tasks, reports, models, health,
  settings, help, and exit without requiring the user to memorize subcommands,
- explicit separation between the CLI lifecycle and Eden's runtime lifecycle:
  in the default Always-On mode, the background Service and Core start
  automatically according to the startup architecture, while `eden` only opens
  a client session and attaches to the already-running Core,
- a fast client-open path that does not automatically perform broad inspection,
  load a model, mutate the machine, or start/stop Eden's background runtime,
- a clear unavailable/reconnecting state when the CLI cannot reach Core, without
  silently treating opening the client as permission to boot or restart Eden,
- a complete direct terminal command surface for every Eden operation, including
  chat and inspection, so forms such as `eden chat "..."` and
  `eden inspect gpu` perform one requested action and return without opening the
  interactive home,
- idempotent graceful Core lifecycle controls through `/corestart`, `/corestop`,
  `eden core start`, and `eden core stop`, clearly distinct from `/exit`, which
  closes only the current CLI client,
- two-stage current-conversation stop behavior: safe stop first, then hard stop
  on a repeated `/stop` or Ctrl+C,
- TTY-aware behavior so redirected input/output and automation retain the direct
  command interface rather than receiving an interactive menu,
- shared application services underneath both the interactive shell and direct
  commands so the menu does not become a second authority or behavior path.

## CLI

```text
eden
eden chat "Why is my PC running slowly?"
eden chat "Help me plan a future PC build" --save
eden chat "Continue the GPU investigation" --report RPT-0184
eden chat "One more detail" --conversation CHT-0042
eden chat list
eden chat show CHT-0042
eden chat export CHT-0042
eden chat delete CHT-0042
eden chat compact CHT-0042
eden chat pin CHT-0042
eden report close RPT-0184 --status failed --summary "..." --outcome "..."
eden report retention RPT-0184
eden report review-retention RPT-0184 --confirm-evidence-reviewed
eden storage status
eden storage status --details
eden storage reports --details
eden storage conversations --details
eden storage attachments --details
eden storage recommendations
eden inspect gpu
eden task list
eden task show <id>
eden task pause <id>
eden task resume <id>
eden task cancel <id>
eden task reconcile <id> --outcome failed --reason "Reviewed the checkpoint"
eden task show <id> --details
eden settings show
eden core start
eden core stop
```

The interactive home should make the major destinations visible and accept
slash commands such as:

```text
/chat
/new
/save
/compact
/chats
/resume CHT-0042
/report RPT-0184
/report unlink
/report close RPT-0184 failed | <summary> | <outcome>
/report retention RPT-0184
/report review-retention RPT-0184 confirmed [unique-evidence-chat-ids...]
/inspect
/tasks
/task reconcile <id> failed | <review reason>
/reports
/models
/health
/settings
/help
/corestart
/corestop
/stop
/exit
```

Ordinary non-command text at the prompt is treated as a message to Eden. Exact
screen layout and keyboard shortcuts are implementation details, but every menu
item and slash command must call the same Core/application services used by the
equivalent direct CLI command.

Every Eden operation exposed by the interactive client must also have a direct
terminal form. A direct command performs that operation and returns; it must not
open the interactive home first. The installed product command is `eden`; using
`uv run` is a development-repository launcher, not part of the user-facing CLI
syntax. Navigation-only client actions such as `/exit` do not need a meaningless
direct equivalent.

`/corestop` and `eden core stop` use the same graceful Core-stop application
service. Active tasks are checkpointed at safe boundaries for recovery on
Core's next start. The client stays open on a Core-stopped home without a chat
bar. `/corestart` and `eden core start` use the same start operation. Repeating
either operation in its current state returns an informational message.

In the default Always-On mode, Eden's background runtime starts automatically
with the configured Windows boot/login lifecycle. Running `eden` opens the
interactive client; it is not the command that boots Eden. Startup-mode changes
and runtime lifecycle operations remain explicit administrative/service actions.

## Acceptance

1. Kill Core during a synthetic task, restart Eden, and recover the task state
   without relying on the old model conversation.
2. During a live task, the default CLI explains in plain English what Eden is
   doing, the current phase, completed steps, elapsed time, and waiting state.
3. When evidence supports an estimate, the CLI shows a responsible ETA or range
   and updates it; otherwise it clearly says that an estimate is unavailable or
   still being established.
4. The user can reveal sanitized technical details for the current operation,
   including the applicable provider/tool/command, without exposing secrets.
5. Health, inspection, model, chat, report, and task commands use one consistent
   MVP visual language while retaining stable `--json` output and usable
   redirected/no-color output.
6. The progress/event model is UI-independent so Milestone 18 can stream and
   render the same task state rather than creating a second tracking system.
7. Running `eden` in an interactive terminal attaches to the already-running
   Core, presents a clear home/client screen, allows immediate chat, and exposes
   the main non-chat destinations without requiring command memorization.
8. Slash-command and menu navigation can enter and return from inspection,
   tasks, reports, models, health, and settings without losing the active session
   or starting unintended work.
9. Direct commands, redirected output, `--json`, help output, and automation
   remain usable without launching the interactive shell.
10. Opening the interactive client does not start or stop Eden's background
    runtime and performs no broad inspection, model inference, privileged action,
    or system mutation until the user selects or requests it.
11. If Core is unavailable, the CLI reports that connection state clearly and
    offers appropriate retry or guidance without implying that closing the CLI
    shuts Eden down.
12. Every Eden operation available through the interactive client, including
    chat and inspection, has a direct `eden <command>` path that executes
    without launching the interactive home and uses the same application
    service as the interactive path.
13. `/exit` disconnects only the current CLI client and leaves Eden running.
    Starting Core does not open a second visible terminal window; Core runs as
    a separate background process until explicitly stopped.
14. `/corestart` and `/corestop` are idempotent, never mean Windows or System
    Service lifecycle, and leave the interactive client open. When Core is
    running, interactive stop requires a confirmation page with Cancel selected
    first and a warning about temporary/session-only data and active work;
    Cancel or Esc leaves Core running.
15. A simulated graceful Core stop checkpoints active work and records an
    intentional stop so restart recovery can distinguish it from a crash; the
    real Service lifecycle integration is completed in Milestone 7.
16. After `/corestop`, the interactive CLI has no chat input and shows Start
    Core and More; More contains Help, Settings, and Exit. This does not behave
    like `/exit`.
17. A temporary chat is visibly marked and leaves no resumable transcript after
    its temporary lifetime ends.
18. A saved chat can be resumed after Core restart, exported, and deleted
    without creating a report or loading its entire transcript into model
    context.
19. A report can link multiple conversation artifacts while its normal human
    and AI views contain only material summaries rather than raw chat history.
20. Linking a temporary chat discloses the persistence change; Eden never
    silently saves it or silently moves it to a different report.
21. Storage status shows the shared category budget and, with `--details`,
    attributes report, Full/Compact conversation, memory, attachment, index,
    database-overhead, protected, and reclaimable usage without changing data.
22. Closing a report produces reviewable conversation-compaction candidates but
    does not itself delete or compact a transcript. Closing requires an explicit
    structured summary and outcome; resolved reports still require passing
    verification. Candidates remain protected until unique transcript evidence
    is explicitly reviewed, and those without a material contribution summary
    remain protected rather than being assumed safe to compact.
23. A temporary chat remains available while its owning CLI visits other
    threads, warns on normal exit when meaningful or active, and is safely
    stopped/discarded after an unexpected client disconnect without stopping
    Core or another client's work.
24. A safe-boundary-only segment emits a bold warning before it begins; a first
    stop signal requests safe stop and a repeated signal requests hard stop.
    Read-only diagnostic requests in a conversation use linked durable tasks;
    ordinary chat answers remain conversations without task-list clutter.
    The warning is informational and does not pause work or demand a reply;
    any required approval is handled separately. Until the planning milestone,
    the task-event path records and displays the imminent segment in chat.
25. Terminal tasks leave active views but retain a final summary and minimal
    durable audit record; completion alone does not create a report.
26. The running interactive home ends in a chat composer rather than a New Chat
    button. Typing sends a message directly; arrow keys and Enter reach the
    secondary Conversations and Monitoring actions. The stopped home has
    no composer; More is available only in its stopped-Core menu.
27. The interactive client uses the alternate screen as a full-terminal
    application and redraws it in place. Each thread contains only its own
    transcript and shows its conversation ID once in the header. User messages
    have a subtle gray outline while Eden's responses remain borderless. Home's Activity
    area is this terminal's history of opened and worked-on conversations,
    showing working/completed/deleted summaries rather than interleaved responses.
    Deleted chats remain marked in Activity but disappear from Conversations.
    The running home header uses the small ASCII tree as its right edge, with
    a vertically centered, shorter open status box whose rules stop two spaces
    before the art; compact layout is retained when the tree cannot fit.
    Confirmation and other full-screen messages wrap and page at terminal width.
    Long transcript lines wrap at word boundaries where possible,
    reflow to the current width on
    terminal resize without discarding source text; Page Up/Down scrolls through
    older wrapped rows. Each mouse-wheel event scrolls exactly two wrapped
    transcript rows, not button selection, while the title, buttons, and composer
    stay fixed. The transcript fills the rows immediately below its title/status
    header and above its composer, without reserved spacer rows. Short
    transcripts are top-aligned; unused rows follow their text.
    Once overflowing, the feed follows the latest messages unless scrolled up.
    System notices
    stay at their chronological position rather than after all later turns.
    The original shell screen is restored when the client exits;
    direct commands remain ordinary terminal output.
28. `Esc` is the default back action across interactive subviews, and returns
    from the chat composer only when its draft is empty. It never clears a draft.
    Backspace removes the character before the cursor; Delete removes the
    character at it. Ctrl+C and `/stop` continue to mean
    stop work rather than navigate back.
29. Non-interactive direct-command use remains fully functional and does not
    enter interactive navigation.
30. The CLI has one presentation; it has no simple/stylized toggle or persisted
    presentation preference.
31. The layout avoids a full-screen perimeter box, encloses the home status area
    with smooth box-drawing, gives conversation title/status headers rounded corners and dark gray
    characters on black, lightened to balance visually against the composer fill.
    Navigation buttons use the same character color on black. The borderless composer has a dark neutral
    background. Its message placeholder disappears once the user types;
    the composer positions a native block cursor so supporting terminals can
    render it as a hollow outline when focus is lost;
    `/help for commands` sits below the button row, and persistent Enter/Esc/
    Ctrl+C instruction text is not shown on the main screen.
32. Conversations and Monitoring sit below the composer; More is shown only in
    the stopped-Core menu. Down at the composer's bottom edge selects the
    button row and Up returns to the composer. Within a
    wrapped draft, left/right move the insertion point by character and up/down
    move between text rows; left/right changes buttons only on the button row,
    and typing focuses the composer.
33. Typing `/` opens up to five prefix-matching command choices above the
    composer. Further typing narrows the matches, and arrow navigation scrolls
    through additional commands before completion or submission.
34. Core automatically routes an ordinary conversational request into the
    read-only diagnostic path when local evidence is required. `/inspect
    [area]` performs the same in-thread operation with an explicit starting
    scope.
35. The Conversations subview includes current-client temporary chats as well
    as saved chats. When meaningful temporary work triggers the exit chooser,
    Discard & Exit is the initial selection.

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

## Work tracking

[Milestone 6 overview #12](https://github.com/calebthoren/Sys-Eden/issues/12)
groups these independently testable objectives, all initially Not started:

- #17 — Structured plans and versioning.
- #18 — Capability metadata and action scope.
- #19 — Risk assessment and five-dimensional confidence.
- #20 — Policy Engine and authorization gate.
- #21 — Scoped approval records and invalidation.
- #22 — Denied plans and interrupted approval flow.
- #23 — Explicit automation-permission storage.
- #24 — Plan review and user involvement controls.
- #25 — Authorization acceptance and failure tests.

Dependencies and observable acceptance checks are in each issue. This milestone
uses synthetic/fake execution to prove authority boundaries. The real privileged
service is Milestone 7, and controlled system writes are Milestone 8; creating
these issues does not implement either capability.

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
- lazy Core/model startup,
- coordinated but independently addressable Core and System Service lifecycle,
- intentional-stop state so service/process recovery does not immediately undo
  an explicit stop.

## CLI

```text
eden service status
eden service install
eden service start
eden service stop
eden core start
eden core stop
```

## Acceptance

Reboot Windows and verify:

- service starts automatically in Always-On mode,
- a boot session is recorded,
- Core can retrieve the boot observation,
- service remains independent of the model runtime,
- `eden core stop` checkpoints active work and stops Core without stopping the
  Service, while `eden service stop` addresses the Service explicitly,
- a client that issued `/corestop` remains open and accurately changes to the
  Core-stopped home.

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
- boot trend monitoring,
- complete Storage Manager accounting and pressure recommendations across all
  configured categories,
- user-configurable transcript compaction/retention policy enforcement,
- detailed largest-consumer and reclaimable-space reporting.

## Acceptance

A resolved issue can automatically enter a defined monitoring period and later close based on evidence.

At or before this point, expose basic storage accounting so Eden can report
usage by category and honor user-configured budgets before telemetry begins
growing materially. Milestone 5 supplies the initial reports/conversations
breakdown; this milestone completes cross-category accounting and policy-driven
recommendations.

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
- stale-memory handling,
- detection of likely user intent to create durable structured memory,
- a concrete confirmation prompt before inferred memory creation,
- explicit `/memory <content>` and `eden memory add "..."` commands whose use is
  itself authorization to store the validated memory,
- memory creation from temporary chats without persisting the transcript,
- user-visible memory review and forgetting,
- controlled cross-conversation retrieval that uses structured reports and
  memory by default and raw saved-chat content only when the user requests or
  confirms it.

## Acceptance

Eden uses relevant historical preference/context but current explicit
instructions still win. It never turns ordinary chat into structured memory
silently, and it can forget a memory independently from deleting a transcript.

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
- conversation browser with temporary/saved/report-linked indicators,
- persistence, resume, export, and deletion controls,
- report-linked transcript access,
- core/supporting/linked-artifact report views,
- memory proposal and management controls,
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

- task-scoped screen capture and local visual analysis (see section 27.1),
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

## 27.1 Deferred Screen Access

Local reading/inspection and controlled writing/execution are the foundational
priority. Complete and validate those capabilities through the existing roadmap
before scheduling screen access; it is not a current milestone requirement.
DEC-052 records the accepted direction, with implementation deferred.

Future scope:

- Task-related snapshots of a selected window, display, or region, with Off,
  Ask first, and Automatic permission modes. Automatic permits capture when
  needed for an active task within the configured scope. Proactive watching
  and continuous screen recording are excluded from the planned feature.
- Local image analysis through the replaceable model-provider interface.
  Evaluate the existing vision-capable model first; a second model is not a
  prerequisite. Any additional model must respect the configured storage budget.
- Sensitive screenshots, and screenshots whose sensitivity is uncertain, are
  processed transiently and not retained. Non-sensitive screenshots may be kept
  locally only while Eden expects to revisit them for the associated task.
- Delete retained screenshots automatically as soon as Eden no longer needs
  them. The feature's retention policy must also bound abandoned-task retention
  and recover cleanup after interruption/restart; exact limits remain deferred.
- Keep only necessary, non-sensitive findings in durable history. Report links
  do not extend screenshot lifetime. See reports section 30.1 and system rules
  section 63.1 for handling requirements.

Before implementation acceptance, test permission denial/revocation, sensitivity
uncertainty, retention cleanup, restart/failure paths, and local model performance.
Visual appearance alone cannot establish email authenticity or file safety.

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
