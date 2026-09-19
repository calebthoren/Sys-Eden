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

**Status:** Provisional

**Decision:** Ollama is the likely first real local runtime adapter.

**Why:** Simple local model management/API.

**Not a requirement:** Eden must remain runner-independent.

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

