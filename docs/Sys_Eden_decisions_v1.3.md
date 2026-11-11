# Sys Eden — Decision Log

> **Document role:** Durable record of important architecture and product decisions  
> **Status:** Decision Log v1.3  
> **Purpose:** Preserve why important choices were made so future developers and agents do not repeatedly reopen settled questions without new evidence

---

# 1. How to Use This File

This document records decisions with long-term implementation consequences.

Use it for choices such as:

- database engine,
- privilege architecture,
- report storage,
- startup behavior,
- model abstraction,
- test environment,
- major UI direction.

Do not add entries for tiny implementation details.

Decision states:

- **Accepted** — current project direction.
- **Provisional** — current implementation choice, replaceable if testing gives a better answer.
- **Deferred** — intentionally not decided yet.
- **Superseded** — replaced by a later decision.
- **Rejected** — evaluated and not selected.

When changing an Accepted decision:

1. document the new evidence/problem,
2. add a new decision,
3. mark the old decision Superseded,
4. update canonical docs.

---

# DEC-001 — Windows First

**Status:** Accepted

**Decision:** Sys Eden targets Windows 11 first.

**Why:**

- project goal is deep Windows maintenance,
- Windows APIs are platform-specific,
- current development hardware is Windows,
- multi-platform work would dilute the MVP.

**Consequence:** Core abstractions should remain portable where practical, but Windows quality takes priority now.

---

# DEC-002 — Python 3.13 Core

**Status:** Accepted

**Decision:** Initial Core uses Python 3.13.

**Why:**

- strong AI/tooling ecosystem,
- fast development,
- mature Windows integration libraries,
- good testing support,
- user already has Python experience.

---

# DEC-003 — `uv` Project Management

**Status:** Accepted

**Decision:** Use `uv`, `pyproject.toml`, and `uv.lock`.

**Why:**

- reproducible environments,
- fast dependency management,
- simple tooling,
- avoids duplicated requirements workflows.

---

# DEC-004 — SQLite 3 Primary Database

**Status:** Accepted

**Decision:** Use SQLite 3 for local structured persistence.

**Why:**

- single-user local application,
- no database server,
- portable,
- simple backup,
- mature and reliable,
- sufficient concurrency for MVP.

**Implementation:** SQLAlchemy 2.x + Alembic.

**Future:** PostgreSQL may be considered if multi-device/server architecture genuinely requires it.

---

# DEC-005 — SQLite WAL + Foreign Keys

**Status:** Accepted

**Decision:** Enable WAL and foreign-key enforcement.

**Why:**

- readers can continue during writes,
- background monitoring and interactive reads can coexist better,
- linked objects should not silently become orphaned.

---

# DEC-006 — Core and Privileged Service Are Separate

**Status:** Accepted

**Decision:** The intelligent Eden Core normally runs as the logged-in user. A separate Windows System Service holds machine-level privilege.

**Why:**

- limits privileged attack surface,
- model does not inherit Administrator/SYSTEM authority,
- allows boot observation before Core,
- avoids permanently elevating the AI.

**Rule:** The service is authority, not intelligence.

---

# DEC-007 — Windows Service Starts Early

**Status:** Accepted

**Decision:** Always-On mode starts a lightweight Eden System Service automatically during Windows boot.

**Why:**

- boot quirks are diagnostically important,
- telemetry should not begin only after the AI/UI loads.

**Constraint:** Service must remain lightweight and must not load the LLM during boot.

---

# DEC-008 — Three Startup Modes

**Status:** Accepted

**Decision:** Support:

- Always-On,
- Boot Monitor Only,
- Manual.

**Default:** Always-On.

---

# DEC-009 — Broad Read, Controlled Write

**Status:** Accepted

**Decision:** Eden receives broad structured inspection capability while mutation passes through policy/approval/execution controls.

**Why:** Avoid limiting diagnosis without giving the model unrestricted authority.

---

# DEC-010 — Typed Tools Are Preferred, Not Exclusive

**Status:** Accepted

**Decision:** Common mutations use typed capabilities. Dynamic PowerShell remains a controlled escape hatch.

**Why:**

- typed tools improve safety/testability,
- Windows is too large to predict every needed operation.

---

# DEC-011 — Named Pipes for Core/Service IPC

**Status:** Accepted

**Decision:** Production Windows Core ↔ Service IPC targets Windows Named Pipes.

**Why:**

- local-only,
- Windows-native,
- ACL support,
- no unnecessary TCP listener.

---

# DEC-012 — Minimum Required Privilege

**Status:** Accepted

**Decision:** Execute actions in user context unless elevation is actually required.

**Why:** The presence of a privileged broker should not cause everything to run privileged.

---

# DEC-013 — Structured AI-Native Reports

**Status:** Accepted

**Decision:** Canonical reports are structured domain objects persisted in SQLite.

**Supersedes:** Earlier concept of Markdown reports as canonical storage.

**Why:**

- more compact AI retrieval,
- easier structured search,
- simpler relationships,
- avoids duplicate prose,
- one canonical source of truth.

**Views:**

- AI retrieval capsule,
- JSON export,
- generated human summary,
- optional Markdown/PDF views.

---

# DEC-014 — Reports Remain Portable

**Status:** Accepted

**Decision:** AI-native storage must not become a proprietary opaque blob.

**Requirement:** Provide documented structured export, initially JSON.

---

# DEC-015 — Explicit Knowledge Graph

**Status:** Accepted

**Decision:** Store typed knowledge nodes and edges explicitly rather than relying only on tags or Markdown links.

**Why:** Deterministic traversal and history.

---

# DEC-016 — Task State Is Durable

**Status:** Accepted

**Decision:** Task execution state is persisted independently of model conversation context.

**Why:** Tasks must survive Core/model/UI and eventually machine restarts.

---

# DEC-017 — Plan, Approval, and Automation Permission Are Separate

**Status:** Accepted

**Decision:** These are distinct durable concepts.

**Why:**

- approval binds to a specific plan/version,
- one-time approval is not standing authority,
- automation permission must be explicitly reusable.

---

# DEC-018 — Plans Are the Main Approval Unit

**Status:** Accepted

**Decision:** Approve meaningful plans rather than every harmless command.

**Why:** Preserves informed user control without making Eden unusably repetitive.

---

# DEC-019 — Fresh Risk Check Applies to Automation

**Status:** Accepted

**Decision:** Standing automation permission never bypasses a current risk check.

---

# DEC-020 — Local Model Provider Abstraction

**Status:** Accepted

**Decision:** Core depends on `ModelProvider`, not one local runner.

**Why:** Models/runtimes will change.

---

# DEC-021 — Ollama as Initial Provider Candidate

**Status:** Accepted

**Decision:** Ollama is the first real local runtime adapter.

**Why:** Simple local model management/API.

**Not a requirement:** Eden must remain runner-independent.

**Implementation result (2026-09-22):** Milestone 4 validated the adapter against
the loopback Ollama API with model discovery, health, structured generation, and a
real local diagnostic pass. Core still depends only on `ModelProvider`. The exact
long-term model remains configurable and is not established by this decision.

---

# DEC-022 — Model Files Outside Git

**Status:** Accepted

**Decision:** Local model convention is `C:\AI\models`, configurable.

**Why:** Large reusable binaries do not belong in repository source control.

---

# DEC-023 — CLI First

**Status:** Accepted

**Decision:** First interface is Typer CLI.

**Why:**

- fastest Core debugging,
- automation-friendly,
- no frontend complexity,
- ideal for early VS Code development.

---

# DEC-024 — FastAPI + React/TypeScript/Vite Later

**Status:** Provisional

**Decision:** Likely local UI stack after Core works.

**Not constitutional:** May change if a better implementation is discovered.

---

# DEC-025 — Future Eden Control Center

**Status:** Accepted as product direction; Post-MVP

**Decision:** A mature interface should evolve toward an Eden System Monitor / Control Center.

**Concept:** Combine current-state and historical capabilities inspired by:

- Task Manager,
- Resource Monitor,
- Event Viewer,
- Device Manager,
- Services,
- Reliability Monitor,
- startup tools,
- performance tools,

with:

- AI reasoning,
- historical telemetry,
- reports,
- watchlist,
- timelines,
- contextual actions.

**Constraint:** Do not delay Core MVP to build it.

---

# DEC-026 — High-Frequency Telemetry Separate from Core DB Rows

**Status:** Accepted

**Decision:** High-rate numeric traces use file-based datasets rather than one SQLite row per sample.

**Likely format:** Parquet when needed.

**SQLite stores:** dataset metadata and summaries.

---

# DEC-027 — Resource-Aware Monitoring

**Status:** Accepted

**Decision:** Monitoring intensity adapts to user workload/resource mode.

**Why:** Eden should not distort the workload it is diagnosing.

---

# DEC-028 — VMware Workstation Pro Test Lab

**Status:** Accepted for current development host

**Context:** Development host is Windows 11 Home.

**Decision:** Use VMware Workstation Pro for destructive Windows testing.

**Baseline:** resettable guest snapshot such as `EDEN-CLEAN`.

---

# DEC-029 — VM Results Do Not Prove Hardware Behavior

**Status:** Accepted

**Decision:** VM testing cannot establish real GPU thermal, BIOS, PSU, physical disk, or other machine-specific hardware behavior.

---

# DEC-030 — Windows 11 Enterprise Evaluation Is Suitable for Disposable VM Testing

**Status:** Provisional

**Decision:** May use an evaluation guest where licensing/testing requirements permit.

**Alternative:** another properly licensed Windows test guest.

---

# DEC-031 — Local-First Research Boundary

**Status:** Accepted

**Decision:** Public research queries may leave the PC; private local evidence does not automatically leave.

**Requirement:** sanitize/minimize external queries.

---

# DEC-032 — Cloud Inference Is Opt-In

**Status:** Accepted

**Decision:** Any future cloud inference path must disclose what data leaves, expected benefit, and local alternative.

---

# DEC-033 — Remote Control Is Post-MVP

**Status:** Accepted

**Candidate shape:** temporary Remote Gateway with QR pairing, encrypted connection, and authenticated real-time channel.

**Exact protocol:** Deferred.

**First target:** same trusted LAN.

---

# DEC-034 — Voice Is Post-MVP

**Status:** Accepted

**Decision:** Voice remains another interface to Core and does not bypass Policy Engine.

---

# DEC-035 — No Kernel Driver for MVP

**Status:** Accepted

**Why:**

- unnecessary for core value,
- security/privilege risk,
- driver-signing complexity,
- crash risk,
- testing burden.

---

# DEC-036 — No Broad Autonomous BIOS Flashing for MVP

**Status:** Accepted

**Why:** Hardware-specific exceptional risk and difficult automated recovery.

---

# DEC-037 — `asyncio` Core

**Status:** Accepted

**Decision:** Use Python `asyncio` for Core I/O concurrency.

**Use workers for:** CPU-heavy operations.

---

# DEC-038 — Pydantic Structured Boundaries

**Status:** Accepted

**Decision:** Use validated structured models for plans, tool requests, confidence, verification, etc.

**Why:** Software behavior should not depend on ambiguous free text.

---

# DEC-039 — Reports Are AI-First, Human Views On Demand

**Status:** Accepted

**Decision:** The user does not need the raw canonical report format to be pleasant to read.

**Requirement:** Eden can generate concise and detailed human views when requested.

---

# DEC-040 — Repository Documentation Is Project Memory

**Status:** Accepted

**Decision:** Canonical project truth lives in repository documentation and code, not in any specific ChatGPT conversation.

---

# DEC-041 — Coding Agents Read `AGENTS.md`

**Status:** Accepted

**Decision:** Root `AGENTS.md` acts as the entry point for repository-based coding agents.

---

# DEC-042 — Four-Month Window Prioritizes MVP

**Status:** Accepted

**Decision:** Current development window should produce a useful vertical MVP instead of finishing every future feature.

---

# Deferred Decisions

The following are intentionally open:

- exact local model,
- quantization,
- exact risk formula,
- exact confidence formula,
- final desktop wrapper,
- final remote protocol,
- final production data path,
- exact telemetry sensor stack,
- exact telemetry retention,
- exact vector/semantic index,
- Skill serialization format,
- final service-account hardening,
- external research provider,
- exact approval-token format.

Do not block early implementation on these unless a milestone actually requires the choice.

---

# DEC-043 — Five-Dimension Confidence Model

**Status:** Accepted

**Decision:** Meaningful diagnostic/repair work uses five distinct confidence
dimensions:

- Diagnostic Confidence,
- Research Confidence,
- Execution Confidence,
- Safety Confidence,
- Overall Confidence.

**Why:**

- diagnosis quality is different from ability to execute,
- research quality is different from system safety,
- a single score can hide a critical weakness.

**Constraint:** Overall Confidence must not average away a dangerously weak
individual dimension.

**Deferred:** exact mathematical scoring/calibration formula.

---

# DEC-044 — Precise Direct Instruction May Satisfy Narrow Approval

**Status:** Accepted

**Decision:** A current explicit user instruction may itself serve as approval
for a narrow mutation when the target/action/consequences are already clear
enough for informed shared understanding.

**Example:** `Restart the Print Spooler service.`

**Constraint:** Vague or consequential goals do not become blanket execution
authority. Eden must still diagnose and obtain approval for the meaningful plan
unless a standing automation permission applies.

**Why:** This preserves user sovereignty without forcing redundant confirmation
dialogs for already-specific low/ordinary-risk instructions.



---

# DEC-045 — Configurable Per-Category Storage Budgets

**Status:** Accepted

**Decision:** Sys Eden uses user-configurable per-category storage budgets rather
than one large fixed allocation.

Recommended default targets:

- application + dependencies: **2–4 GB**,
- local model storage: **5–12 GB**,
- reports + memory + SQLite: **1–2 GB**,
- logs + cache: **1–2 GB**,
- telemetry working space: **2–5 GB**,
- host free-space reserve: **3–5 GB**.

A concrete initial configuration may use the upper end of those targets
(4/12/2/2/5 GB) for a maximum normal Eden footprint of about **25 GB**,
excluding the free-space reserve and the developer VM.

**User control:** Each budget may be increased or decreased independently.

**Semantics:**

- model/log/cache/telemetry budgets can be actively managed,
- reports/database use a soft durability-oriented limit,
- application/dependency size is a footprint target rather than a promise that
  required files can always fit an arbitrarily small quota,
- the safety reserve is protected free disk space, not Eden-owned capacity.

**Default:** large cross-category borrowing is not automatic. Eden may offer or
request rebalancing; automatic rebalancing requires explicit user configuration.

**Why:** Eden should manage the PC without becoming a major source of
uncontrolled storage growth.

---

# DEC-046 — Minimal Single-VM Test Footprint

**Status:** Accepted

**Decision:** The destructive Windows test lab should use one minimal,
thin-provisioned disposable Windows VM and one clean baseline snapshot.

Preferred initial target:

**30–50 GB actual host disk use**, aiming not to exceed roughly **50 GB** during
normal development.

The guest should not permanently duplicate:

- AI model files,
- long-term reports/history,
- large telemetry archives,
- many scenario-specific snapshots.

Test conditions should normally be recreated with fault-injection scripts after
restoring `EDEN-CLEAN`.

The VM may use a fake/test model provider or a host model endpoint when that is
simple and useful, but the project should **not** add SSH/WinRM/custom guest
control merely to save a small amount of disk space.

**Why:** Keep destructive testing practical on a consumer PC without turning VM
storage optimization into a second project.

---

# DEC-047 — Roadmap Owns Implementation Sequencing

**Status:** Accepted

**Decision:** `roadmap.md` is the canonical authority for chronological
implementation order and milestone acceptance criteria.

`architecture.md` defines runtime structure, boundaries, dependencies, and
technical constraints, but it should not maintain a competing milestone
schedule.

**Conflict rule:** If Architecture contains an implementation-order statement
that conflicts with the current Roadmap, follow the Roadmap unless an explicit
Accepted decision intentionally changes the sequence.

**Version rule:** Version numbers are compared within the same canonical
document lineage. A newer Architecture version does not automatically outrank a
Roadmap on a sequencing question simply because its version number is larger.

**Why:**

- prevents duplicated milestone lists from drifting,
- preserves clear responsibility between canonical documents,
- lets Architecture describe final runtime dependency order without implying
  that components must be coded in that same chronological order,
- gives coding agents a deterministic way to resolve sequencing conflicts.

**Immediate consequence:** The older Architecture sequence that placed the boot
service third is superseded. Roadmap v1.2 remains the build order, with the
Windows System Service at Milestone 7 after structured reports, local model
integration, durable tasks, and planning/risk/approval foundations.

---

# DEC-048 — Direct CLI Parity and Explicit Core Lifecycle

**Status:** Accepted

**Problem:** The interactive CLI must not become the only way to invoke Eden
operations, and closing the CLI must not be confused with stopping the
automatically running Eden background runtime.

**Decision:** Every Eden operation available through the interactive menu/slash
surface has a direct `eden <command>` equivalent that runs without opening the
interactive home. This explicitly includes forms such as `eden chat "..."` and
`eden inspect gpu`, as well as health, task, report, model, settings, and
lifecycle commands. Installed users invoke `eden` directly; `uv run` is a
development-repository launcher rather than part of the product CLI contract.
Navigation-only client actions may remain interactive-only.

`/exit` disconnects the current client. `/corestart` and `/corestop` invoke the
same Core lifecycle operations as `eden core start` and `eden core stop`. The
commands are idempotent, so requesting an existing state returns an
informational result. These controls affect the user-context Core, not Windows
and not the future independently owned System Service.

After `/corestop`, the interactive CLI remains open and visibly changes to the
Core-stopped home with Start Core, Help, Settings, and Exit; it has no chat bar.
Only `/exit` closes that client. The direct lifecycle form returns to its
invoking shell after the result is known.

Interactive Core stop shows a confirmation page with Cancel initially selected.
It explains that the CLI remains open on the stopped page, while active work
may finish or pause and unsaved temporary chats and session-only restore copies
will be lost. Cancel or Esc makes no Core lifecycle request.

Graceful shutdown checkpoints active durable work and records an intentional
stop. Automatic crash recovery must not immediately reverse it. Eden may start
again through an explicit lifecycle action or the next configured automatic
startup event.

**Alternatives rejected:**

- menu-only operational commands, because they make quick and scripted use
  unnecessarily enter the interactive client,
- treating `/exit` as runtime shutdown, because a client lifecycle must not own
  the background runtime lifecycle,
- closing the interactive client as a side effect of `/corestop`, because the
  user asked to change Eden's runtime state rather than leave the interface,
- treating Core lifecycle as System Service lifecycle, because the components
  have separate authority and ownership.

**Implementation consequence:** Milestone 5 establishes the shared CLI command,
Core lifecycle, and durable-task checkpoint behavior. Milestone 7 connects it to
the real Core/System Service lifecycle and intentional-stop supervision state.

---

# DEC-049 — Conversations, Reports, and Memory Are Separate Retention Layers

**Status:** Accepted

**Problem:** Resumable chat history is useful, but treating every retained
conversation as a report would create meaningless reports, while treating saved
transcripts as general memory would allow private or irrelevant chat to leak
into unrelated context.

**Decision:** Sys Eden maintains three separate retention layers:

1. conversation transcripts for exact conversational history and resumption,
2. reports for structured knowledge about coherent efforts,
3. structured memory for intentionally retained facts, preferences,
   permissions, patterns, and concerns.

New unclassified chats are temporary by default and visibly labeled. A user may
make any ordinary chat persistent without creating a report. Report-related
conversations are stored as separately linked conversation artifacts; reports
contain only material contribution summaries and structured conclusions, not
raw transcript bodies.

Reports present core information, supporting information, and linked artifacts
as distinct retrieval tiers. A report may link multiple conversations, while a
conversation has one primary report context and may reference other reports.

Eden may suggest that a conversation belongs to a different report but may not
silently relink it. Linking a temporary conversation discloses the persistence
effect and allows the user to retain only a report contribution if the full
transcript should remain temporary.

Likely memory intent in ordinary language produces a concrete confirmation
prompt. Explicit `/memory <content>` or its direct CLI equivalent is itself
authorization to create the validated memory. This does not persist a temporary
transcript. Cross-conversation use of raw saved chat requires an explicit user
request or visible relevance confirmation; structured report capsules and
approved memory remain the normal cross-context retrieval sources.

**Storage decision:** MVP conversation metadata and messages use normalized
SQLite records through repository interfaces. Report links reference the
conversation entity. Transcript files are generated export views, not a second
writable canonical store.

**Alternatives rejected:**

- reports as raw chat containers, because reports must remain compact and
  retrieval-oriented,
- report-only conversation persistence, because useful resumable chats do not
  always represent a formal system effort,
- all saved transcripts as automatic memory, because persistence does not imply
  permission for unrelated cross-chat reuse,
- silent memory extraction, because users need to know what Eden will remember.

**Implementation sequence:** Milestone 5 implements conversation persistence,
resumption, report links, summaries, and CLI state. Milestone 16 implements
structured-memory proposals, explicit memory commands, provenance, and
controlled cross-conversation retrieval. Milestone 18 adds the full local UI
for browsing and managing these objects.

---

# DEC-050 — Transcript Compaction Precedes Durable Report Deletion

**Status:** Accepted

**Decision:** Persistent conversations have visible Full, Compact, or Deleted
storage states. Full-to-Compact conversion removes raw history and therefore is
a retention action, not merely model-context summarization. Eden may perform it
automatically only under a user-enabled retention policy; otherwise it proposes
the candidate and asks.

Closing a report creates a retention checkpoint but does not itself compact or
delete linked transcripts. Eden first confirms that the structured report
preserves crucial initial information, conclusions, actions, verification,
outcome, unresolved concerns, and any unique evidence. Conversations connected
to active/open work or explicitly pinned by the user remain protected.

Under storage pressure, Eden removes regenerable and duplicated material first,
then large low-value attachments, then proposes compaction of old unlinked chats
and eligible closed-report transcripts. Structured reports and retrieval
capsules normally outlive raw conversations. Destructive pruning of high-value
reports remains an explicit user decision.

**Accounting requirement:** The shared reports/memory/database budget remains a
single configurable quota boundary, but storage status must attribute its
contents to structured reports, Full/Compact conversations, memory, attachments,
indexes/summaries, database overhead, protected data, and estimated reclaimable
space. `eden storage status --details` and category-specific detail commands are
read-only; recommendations do not perform cleanup.

**Why:** This preserves useful system knowledge while making chat storage
bounded, understandable, and controllable without breaking the promise that a
persistent conversation retains its full history until an explicit policy says
otherwise.

---

# DEC-051 — Conversation-Centered CLI Work and Client-Owned Temporary State

**Status:** Accepted

**Problem:** Separate chat and diagnosis modes, explicit follow modes, and
thread-scoped temporary lifetimes make the user choose internal orchestration
concepts and make background work difficult to understand.

**Decision:** `chat` is the single conversational entry point. Core decides
whether a request needs an answer, clarification, read-only inspection,
diagnosis, or durable task. A requested inspection area is the starting scope;
Core may expand read-only inspection when evidence gives a purpose-limited
reason and it explains that expansion. Explicit exclusions and `--only` are
hard boundaries.

Every interactive operation occurs in a conversation and shows live progress
by default. Leaving the thread does not stop the work, so no `--follow` or
`--detach` mode is needed. The home screen lists up to five actively working
conversations and up to five monitoring tasks, with a See all action. Monitoring
alone does not make a conversation active.

Temporary chats are owned by one CLI client and live until that client closes.
They may remain active while the user navigates elsewhere. Meaningful or active
temporary chats warn on normal exit. For an unexpected terminal close, Core
uses disconnect leases and scoped cleanup; closing a CLI never stops Core.
The Conversations view includes both saved conversations and temporary chats
owned by the current CLI. When an exit warning is required, Discard & Exit is
the initial selection; saving remains an explicit alternative.

`/stop` or Ctrl+C first requests a safe stop of current-conversation work. A
second signal requests a hard stop. Before safe-boundary-only operations, Eden
emits an unmistakable bold warning without imposing a routine acknowledgment
prompt. The CLI has one presentation rather than simple/stylized modes.

Planned safe-boundary-only steps are disclosed during planning once plans are
available. Immediately before entering one, Core durably announces the warning
and the conversation displays it while work continues; it is not a second
approval prompt. A separate policy-required approval still applies to the
underlying action. An unannounced safe-boundary-only segment cannot be entered
through the task-progress path.

**JSON decision:** Machine output uses a stable versioned envelope containing
envelope version, payload type/version, status, request identity, UTC time,
conversation/task/report associations, explicit synthetic provenance, data,
warnings, and a structured error when applicable. Direct `--json` commands keep
stdout valid JSON and send human progress to stderr. `/help` is generated from
one registry and lists modifier compatibility.

**Terminal interaction decision:** Typer remains the direct command framework
and direct commands remain ordinary shell output. The interactive client owns
the terminal's alternate screen and presents a dependency-free full-terminal
application. It restores the prior shell screen only when the client
exits. Stopping Core changes the same open client to its stopped screen.

While Core is running, its home is conversation-first: a borderless dark
composer is available at the bottom and there is no separate New Chat button.
Conversations and Monitoring sit on the row below it; More is limited to the
stopped-Core menu. Down reaches the button row from the composer's bottom edge
and Up returns to the composer (placement updated by DEC-053);
within a wrapped draft, left/right move by character and up/down move between
text rows. Left/right selects buttons only on the button row. Typing focuses the
composer. Sending ordinary text from home creates a new
temporary conversation and enters its dedicated thread screen. Sending more
messages there continues that same context; `/home` or `Esc` returns to home
without stopping its work, and `/new` returns to an empty home composer.

A small dependency-free Windows key reader redraws the owned application screen
for state, draft input, selection, and progress. The layout avoids a full-screen
perimeter border and uses smooth box-drawing around the top status section. The
running home places the small ASCII tree on the far right and centers an open
status box at about two-thirds of the tree's height. Its horizontal rules stop
two cells before the tree silhouette; narrow or short terminals use the compact
status panel instead. Confirmation and other full-screen views word-wrap their
content and can page through overflow rather than clipping warning text. The
composer has a dark neutral background and no border. The composer arrow is
white while the terminal window has focus and light gray when it loses focus,
using terminal focus events rather than changing chat-row selection. Its
message placeholder
disappears while typing; `/help for commands` sits below the button row, while
Enter/Esc/Ctrl+C instruction text is omitted. A thread shows its conversation ID
once in the header and renders only that conversation's user/Eden transcript;
user messages receive a subtle gray outline while Eden responses stay unboxed;
responses do not repeat the ID. Home's Activity area is an overview rather than
a transcript: it is this terminal's activity history, including previously
saved chats opened here, with a visible working indicator and completion state.
Deleting a chat marks it Deleted in this terminal's history and removes it
from the Conversations browser; restoring it changes the entry back to Complete.
Interactive deletion is confirmed and reversible only during the owning CLI
session; direct one-shot deletion is permanent. Typing `/` opens an
in-place command palette above the composer with up to five matching commands;
the list filters as the user types and arrow navigation scrolls through further
matches. The mouse wheel scrolls only the conversation feed, never selects
buttons; the conversation title, button row, and composer remain fixed while
that feed scrolls. DEC-053 refines the conversation header, feed spacing,
notice ordering, and two-line wheel behavior after owner testing.
ID-bearing chat and monitoring commands show newest-first ID/title
suggestions in that same palette, selectable with arrows and Enter. `Esc` is the
default back action in subviews. In the composer it returns only when the draft
is empty; it never deletes draft text. Backspace removes the character before
the cursor, while Delete removes the character at the cursor.
Ctrl+C and `/stop` retain their separate safe-stop/hard-stop meaning.
Normal conversation messages are classified by Core. A request that needs
local evidence enters the read-only diagnostic path in the same thread;
`/inspect [area]` is an explicit starting-scope shortcut, not a separate chat
mode.
Non-interactive invocations never enter the application.

**Task retention:** A terminal task keeps a compact final summary and minimal
durable audit identity. If related to a report, its summary is incorporated into
the report; completion does not automatically create a report. Terminal tasks
leave active views, and retention may later prune transient detail without
destroying restart/audit integrity.

---

# DEC-052 — Deferred Task-Scoped Screen Access and Temporary Image Evidence

**Status:** Accepted direction; implementation deferred

**Problem:** Visual evidence can help Eden interpret unusual on-screen behavior
and suspicious messages, but must not displace foundational local inspection
and controlled execution or create a lasting collection of private screenshots.

**Decision:** Follow the existing local read/write roadmap first. Screen access
is a future task-scoped capability with Off, Ask first, and Automatic modes.
Automatic allows relevant snapshots within a configured active-task scope;
proactive watching and continuous recording are excluded from the plan.

Capture belongs in the logged-in user's session, with permission enforced by
Eden outside model reasoning. Screen access grants no mouse/keyboard control,
attachment execution, system mutation, or external disclosure authority. Image
analysis remains local through the existing model-provider abstraction. Reuse
an adequate installed vision-capable model before considering another download;
model choice and storage budgets remain configurable.

Sensitive images and images of uncertain sensitivity are transient inputs, not
retained evidence. Non-sensitive screenshots may be kept locally when Eden
expects to revisit them for the task, then automatically deleted when no longer
needed. The feature's explicit retention policy also covers abandoned tasks and
cleanup after interruption/restart. Derived text must not preserve unnecessary
sensitive contents after image deletion. Reports may retain concise findings
and metadata without requiring the original image to survive.

**Alternatives considered:** Immediate deletion of every screenshot avoids
retention but prevents useful revisits. Permanent attachment storage accumulates
private data and unnecessary disk use. A required second model adds storage
without first establishing a need. Temporary, purpose-limited retention and
evaluation of the existing model best fit the user's requirements.

**Implementation sequence:** Roadmap section 27.1 controls scheduling. Detailed
capture APIs, permission defaults, sensitivity checks, cleanup limits, and
performance targets are deferred until this feature is scheduled. Sensitivity
detection must account for uncertainty rather than claim perfect classification.

---

# DEC-053 — Conversation Layout and Notice Ordering After Owner Testing

**Status:** Accepted

**Problem:** Owner testing found that save/pin confirmations stayed after later
turns and that the transcript left unused rows around the composer/header.
The owner also requested actions below the composer, a light gray chat header,
and one-line wheel scrolling. Other tested behavior appeared to work; that is
scoped feedback rather than individual signoff on every milestone check.

**Decision:** After subsequent owner refinement, render conversation title/status
in a rounded panel with dark gray border/text characters on black. The
character color is lightened to balance its appearance against the composer fill; the header is not
filled gray. Navigation buttons use that same lightened character color on
black. The transcript owns every available row between header and composer.
Short transcripts start directly below the header with unused rows below them;
overflow follows the latest messages unless the owner scrolls up.
Place actions immediately below the composer and help text below the actions;
Down at the composer's bottom edge reaches actions and
Up returns to editing. One wheel event moves two wrapped transcript rows;
Page Up/Down retains larger movements. Keep the home tree/status composition.

System notices are client-only events anchored after the message sequence
visible when they appear, including a queued user message. Later turns follow
the notices. Saving a temporary thread preserves those positions. Notices do
not become stored conversation messages or model instructions/context.

**Alternatives considered:** Clearing all notices after a timer would hide
useful confirmations; appending all notices at the end permanently obscures
turn order. Anchored notices preserve context and scroll naturally. Reserving
spacer rows or three-line wheel jumps wastes space and conflicts with the
owner's requested interaction.

This supersedes DEC-051's earlier action-row placement and refines its visual
presentation; its Core lifecycle, privacy, and authority decisions still apply.
