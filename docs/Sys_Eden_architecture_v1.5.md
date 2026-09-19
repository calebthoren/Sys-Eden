# Sys Eden — Architecture

> **Document role:** Canonical implementation architecture for Sys Eden  
> **Status:** Architecture v1.5 — implementation-sequencing conflict resolved  
> **Depends on:** `vision.md`, `reports.md`  
> **Primary platform:** Windows 11  
> **Current development host:** Windows 11 Home  
> **Implementation language:** Python 3.13  
> **Development priority:** Build a trustworthy end-to-end MVP within the current four-month focused development window

---

# 1. Purpose

This document translates the Sys Eden vision into a practical software architecture.

`vision.md` defines **what Sys Eden is and why it exists**.

`reports.md` defines the durable report/history system.

This file defines **how the major runtime pieces fit together** so a developer or coding agent can begin implementation without depending on prior chat history.

This architecture intentionally makes several concrete MVP decisions while preserving replaceable interfaces around components likely to evolve.

The architecture MUST support the core Sys Eden loop:

```text
Observe
  ↓
Clarify
  ↓
Research / Diagnose
  ↓
Assess confidence
  ↓
Plan
  ↓
Risk + approval
  ↓
Execute
  ↓
Verify
  ↓
Report / Remember
  ↓
Monitor
```

The MVP does not need every long-term feature. It does need the architecture to support that loop without requiring a fundamental rewrite.

---

# 2. Architecture Principles

The architecture follows these principles.

## 2.1 Local-first

Private device data remains local by default.

The normal runtime must not require a cloud service to:

- inspect the computer,
- maintain reports,
- run the local model,
- execute Windows tools,
- retain memory,
- verify fixes,
- or monitor the machine.

Internet access is a separate research capability.

---

## 2.2 Broad visibility, controlled mutation

Eden should be able to inspect the computer broadly.

Eden should not have unrestricted, unmediated write access merely because it can inspect broadly.

The architecture therefore separates:

```text
READ / OBSERVE
     │
     ├── broad collectors
     ├── generic query interfaces
     └── system inspection

WRITE / CHANGE
     │
     ├── typed actions
     ├── policy checks
     ├── approval
     ├── privileged broker
     └── dynamic escape hatch when needed
```

This prevents the predefined tool catalog from becoming a ceiling on Eden's intelligence while still avoiding:

```text
LLM → unrestricted Administrator shell
```

---

## 2.3 The model does not directly own the operating system

The AI model reasons about data and proposes actions.

It does not receive raw OS credentials or direct unrestricted access to the machine.

All system interaction flows through Sys Eden-controlled adapters and policy boundaries.

---

## 2.4 Replaceable model runtime

Sys Eden MUST NOT depend permanently on a single model, runner, vendor, or inference protocol.

A model provider interface separates Eden from the initial local runtime.

---

## 2.5 Durable state

Long-running work must survive:

- application restarts,
- model restarts,
- UI restarts,
- and eventually machine restarts.

Important task state is persisted rather than existing only inside an LLM conversation.

---

## 2.6 AI-native durable knowledge with portable views

Important history should be optimized first for accurate machine retrieval and
reasoning, not for being stored as long prose.

Reports are canonical structured domain objects persisted locally in SQLite.
They expose compact AI retrieval capsules for model context.

Human-readable summaries, timelines, Markdown documents, and other views are
generated from the canonical structured report when needed.

Users must still retain practical ownership and portability through documented
structured export, such as JSON. The system must not hide knowledge inside an
opaque proprietary blob.

---

## 2.7 Privilege separation

The normal interactive agent should not run permanently as Administrator.

Privileged system operations are brokered through a narrow Windows service boundary.

---

## 2.8 Build the core loop before polish

The MVP prioritizes:

- inspection,
- reasoning,
- plans,
- approval,
- execution,
- verification,
- reports,
- memory,
- and targeted monitoring.

Advanced graph visualization, voice, polished remote access, and broad autonomous automation come later.

---

# 3. High-Level Runtime Architecture

The target architecture is:

```text
                      WINDOWS BOOT
                           │
                           ▼
                ┌─────────────────────┐
                │ Eden System Service │
                │                     │
                │ - boot observer     │
                │ - telemetry hooks   │
                │ - privileged broker │
                │ - local IPC server  │
                └─────────┬───────────┘
                          │
                 durable local state
                          │
                          ▼
                 ┌─────────────────┐
                 │   Eden Core     │
                 │  Orchestrator   │
                 └────────┬────────┘
                          │
        ┌─────────────────┼───────────────────┐
        │                 │                   │
        ▼                 ▼                   ▼
┌──────────────┐   ┌──────────────┐    ┌──────────────┐
│ Local Models │   │ Research     │    │ Knowledge    │
│ + Router     │   │ Providers    │    │ + Reports    │
└──────┬───────┘   └──────────────┘    └──────────────┘
       │
       ▼
 reasoning / plans
       │
       ▼
┌───────────────────────────────────────────────┐
│ Windows Capability + Policy Layer            │
│                                               │
│ Broad inspection     Typed actions            │
│ Generic queries      Dynamic PowerShell       │
│ File/registry/etc.   Risk / permission checks │
└───────────────────────┬───────────────────────┘
                        │
                        ▼
                Eden System Service
                        │
                        ▼
                    Windows
                        │
                        ▼
                  Verification
                        │
                        ▼
              Reports / Memory / Monitoring
```

---

# 4. Primary Runtime Components

The initial architecture contains the following major components.

## 4.1 Eden System Service

A lightweight Windows service that starts early during normal boot.

Responsibilities:

- capture early boot/session observations,
- expose privileged Windows operations through local IPC,
- provide system inspection capabilities that require service access,
- host lightweight background collectors,
- persist boot/session events before the interactive agent is running,
- enforce service-side request validation,
- execute approved privileged operations,
- survive interactive UI/model restarts.

The service MUST remain lightweight during startup.

It MUST NOT load the local LLM during Windows boot.

### 4.1.1 Service is authority, not intelligence

The System Service is intentionally **not an AI agent**.

It should not independently invent repairs, reinterpret user intent, or make
open-ended decisions. Those responsibilities belong to Core.

The service receives bounded structured requests and performs narrow duties:

```text
validate identity
→ validate request schema
→ verify authorization/policy proof
→ execute requested privileged capability
→ return structured result
```

This reduces the amount of complex AI-controlled code running with powerful
Windows privileges.


---

## 4.2 Eden Core / Orchestrator

The primary application logic.

Responsibilities:

- maintain conversations,
- manage tasks,
- build model context,
- route to models/subagents,
- request system evidence,
- coordinate research,
- create hypotheses,
- generate plans,
- call policy/approval logic,
- dispatch execution requests,
- coordinate verification,
- update reports,
- retrieve memory/history,
- react to monitoring events.

The user should conceptually interact with one Eden even if multiple internal agents are used.

---

## 4.3 Model Layer

Provides local inference through a replaceable model-provider abstraction.

Responsibilities:

- model discovery,
- inference requests,
- model routing,
- capability metadata,
- resource-awareness,
- context construction,
- structured outputs,
- model loading/unloading where supported.

The initial adapter MAY target Ollama for convenience, but Ollama is not an architectural dependency.

---

## 4.4 Windows Capability Layer

Provides broad access to Windows information and controlled access to Windows changes.

Contains:

- read-only collectors,
- generic inspection tools,
- typed mutating tools,
- dynamic script escape hatch,
- standardized tool result schemas.

---

## 4.5 Policy / Approval Layer

Sits between proposed action and execution.

Responsibilities:

- classify request type,
- determine whether action is read-only or mutating,
- estimate risk,
- determine required privileges,
- check automation permission,
- require user approval where appropriate,
- block malformed/unsupported capability requests,
- preserve approval scope.

Exact risk-tier thresholds belong in `system_rules.md`.

---

## 4.6 Verification Layer

Checks whether execution achieved the objective.

Verification SHOULD be able to run independently from the agent that proposed the repair.

---

## 4.7 Report / Knowledge Layer

Implements the durable system defined in `reports.md`.

Includes:

- report repository,
- AI retrieval capsules,
- generated human/JSON/Markdown views and exports,
- metadata index,
- report chains,
- knowledge nodes/edges,
- watchlist relationships,
- retrieval.

---

## 4.8 Memory Layer

Stores structured user/system memory separately from raw conversation logs.

Examples:

- user preferences,
- system history,
- automation permissions,
- repeated behavioral observations,
- ongoing concerns,
- component history.

---

## 4.9 Telemetry Layer

Captures targeted, resource-aware system observations.

Contains:

- boot observations,
- periodic lightweight health metrics,
- high-frequency targeted traces,
- event ingestion,
- telemetry retention/summarization.

---

## 4.10 Research Layer

Queries public external information while keeping local private context under Eden's control.

Public research and cloud AI inference are separate concepts.

---

## 4.11 User Interface Layer

Initial:

- CLI.

Later:

- local web UI,
- desktop shell,
- remote companion,
- voice.

The core system should not depend on one UI implementation.

---

# 5. Process Boundaries

The MVP should begin with three logical process categories.

## 5.1 System service process

Runs as a Windows service.

Potential responsibilities:

- boot/session observer,
- privileged broker,
- lightweight telemetry,
- IPC server.

---

## 5.2 Interactive core process

Runs in the logged-in user's context.

Contains:

- orchestrator,
- task engine,
- model routing,
- report/memory coordination,
- CLI/API.

The normal Core process SHOULD NOT run permanently elevated.

---

## 5.3 Model runtime process

A separate local model runtime.

Examples:

- Ollama,
- llama.cpp server,
- another OpenAI-compatible local server.

The model process is replaceable.

Eden communicates with it through a provider abstraction.

---

# 6. Startup Architecture

Immediate boot observation is a first-class requirement.

## 6.1 Default mode

The recommended default is:

**Always-On**

Behavior:

1. Windows boots.
2. Eden System Service starts automatically.
3. Lightweight collectors begin.
4. Boot/session markers are recorded.
5. User logs in.
6. Eden Core starts automatically.
7. UI becomes available.
8. Model loads lazily when reasoning is needed.

This provides early observation without making the LLM compete with Windows during the critical startup period.

---

## 6.2 Startup modes

The system should support at least three user-selectable modes.

### Always-On

- System Service: Automatic.
- Core/UI: auto-start after user login.
- Local model: lazy/on-demand.
- Monitoring: enabled according to configuration.

This is the intended default.

### Boot Monitor Only

- System Service: Automatic.
- Core/UI: manual.
- Local model: manual/on-demand.
- Boot/system observations continue quietly.

Useful for users who want diagnostics without an always-running assistant.

### Manual

- System Service: demand/manual start.
- Core/UI: manual.
- Model: manual/on-demand.
- No normal continuous monitoring while Eden is off.

When privileged execution is requested, the service may be started through the normal Windows/UAC process.

---

# 7. Boot-Time Observation

A normal Windows service cannot observe events that occur before Windows itself and all early kernel components.

The architecture therefore distinguishes boot visibility levels.

## 7.1 MVP boot visibility

Use:

- Windows Event Log history,
- boot timestamps,
- service startup timestamps,
- process/startup observations available after service start,
- driver/update history,
- startup timing,
- previous shutdown/crash events,
- system uptime/session markers.

This captures most practical boot problems.

---

## 7.2 Advanced boot visibility

A future optional feature may configure ETW AutoLogger sessions for selected boot diagnostics.

This should be used selectively because aggressive boot tracing can itself influence boot performance.

The MVP does NOT require:

- custom kernel drivers,
- kernel-mode monitoring,
- custom boot loaders.

---

# 8. Boot Sessions

Every boot SHOULD receive a durable `boot_session` record.

Conceptual fields:

```text
id
boot_timestamp
service_start_timestamp
user_login_timestamp
core_start_timestamp
shutdown_type_previous
unexpected_shutdown
os_build
driver_change_since_previous_boot
update_change_since_previous_boot
summary
```

Boot sessions let Eden compare:

- normal vs abnormal startup,
- before/after driver changes,
- update regressions,
- boot duration trends,
- startup service delays.

---

# 9. Windows Access Model

The Windows access architecture is intentionally layered.

```text
                  Eden Core
                     │
        ┌────────────┴─────────────┐
        │                          │
        ▼                          ▼
  Inspection APIs            Mutation APIs
        │                          │
 broad parameterized         typed first
 read access                 dynamic fallback
        │                          │
        └────────────┬─────────────┘
                     ▼
               Policy Engine
                     │
                     ▼
             Service / Executor
```

---

# 10. Read / Inspection Access

Eden should be able to inspect broadly without requiring a bespoke function for every possible question.

The inspection system should include both specialized and generic tools.

---

## 10.1 Specialized read tools

Examples:

```text
get_system_summary()
get_cpu_info()
get_gpu_info()
get_memory_info()
get_storage_info()
get_network_info()
get_driver_inventory()
get_installed_software()
get_startup_items()
get_services()
get_recent_crashes()
get_boot_history()
```

These are convenient and safe for common workflows.

---

## 10.2 Generic read tools

To prevent the specialized tool catalog from limiting Eden, provide parameterized generic readers.

Examples:

```text
query_cim(...)
query_event_log(...)
read_registry(...)
enumerate_registry(...)
list_files(...)
read_text_file(...)
get_file_metadata(...)
query_processes(...)
query_services(...)
query_scheduled_tasks(...)
query_performance_counters(...)
```

These remain structured tools but can inspect large parts of Windows.

---

## 10.3 File access

Eden may need broad filesystem visibility.

File access SHOULD support:

- metadata-only queries,
- directory listing,
- hashes,
- file size/type,
- selected content reads,
- search.

The system SHOULD avoid feeding full file contents to the LLM unless the task needs them.

The fact that the broker can read a file does not mean the model automatically receives that file.

---

# 11. Controlled Mutation

Changes to the machine should prefer explicit typed capabilities.

Examples:

```text
stop_service(...)
start_service(...)
restart_service(...)
set_startup_item(...)
disable_startup_item(...)
set_registry_value(...)
move_file(...)
delete_file(...)
install_package(...)
uninstall_package(...)
set_power_plan(...)
create_restore_point(...)
```

Typed actions provide:

- predictable inputs,
- known side effects,
- easier risk classification,
- easier tests,
- clearer verification,
- safer auditing.

---

# 12. Dynamic PowerShell Escape Hatch

Typed tools MUST NOT become a hard capability ceiling.

When Eden needs an action or investigation not covered by existing tools, it may construct a dynamic PowerShell request.

Flow:

```text
Eden identifies missing capability
        ↓
Generate proposed script/command
        ↓
Attach objective + expected effects
        ↓
Parse/analyze
        ↓
Policy classification
        ↓
Approval if needed
        ↓
Execute in isolated process
        ↓
Capture stdout/stderr/exit code
        ↓
Verify
        ↓
Record execution
```

The dynamic escape hatch is essential for unusual troubleshooting.

---

# 13. PowerShell Execution Rules

The executor should support both:

- built-in Windows PowerShell where necessary for maximum Windows compatibility,
- PowerShell 7 when installed and appropriate.

A shell adapter should detect available versions.

Each execution MUST capture:

- execution ID,
- script text or script hash,
- start/end time,
- shell version,
- working directory,
- privilege level,
- timeout,
- stdout,
- stderr,
- exit code,
- whether the process was terminated,
- related task/report.

The MVP should launch discrete PowerShell processes rather than maintain an unrestricted permanent interactive Administrator shell.

---

# 14. Script Analysis

Static analysis cannot prove a script safe.

It is still useful as one input.

Possible checks:

- PowerShell AST parsing,
- command names,
- registry writes,
- filesystem writes,
- service modifications,
- scheduled-task creation,
- downloads,
- process termination,
- privilege-related commands,
- destructive flags,
- reboot/shutdown calls.

Risk is determined from:

- declared intent,
- parsed behavior,
- affected resources,
- required privilege,
- reversibility,
- user permission,
- system context.

Detailed policy belongs in `system_rules.md`.

---

# 15. Privileged Broker

The model and normal Core process should not permanently run as Administrator.

Privileged work is executed through the Eden System Service.

## 15.1 Service responsibilities

The broker:

- accepts validated local requests,
- verifies request identity,
- re-checks capability schema,
- applies service-side allow/deny rules,
- executes the request,
- returns structured results,
- records execution metadata.

---

## 15.2 Service account

The final Windows service identity must provide enough permission for required system tasks while minimizing unnecessary exposure.

For early MVP development, an elevated service context may be used.

Before production packaging, service permissions SHOULD be reviewed and reduced where practical.

The model runtime itself MUST NOT inherit service privileges.

## 15.3 How administrative authority is acquired

Administrator privilege is established during Sys Eden installation or service
configuration, not by allowing the model to elevate itself dynamically.

Typical installation flow:

1. The user launches the trusted Sys Eden installer/setup.
2. Windows presents its normal UAC elevation prompt.
3. With user consent, setup installs/registers the Eden System Service.
4. The service is configured under an appropriate Windows service identity with
   the machine-level privileges it requires.
5. Core continues to run in the user's normal interactive context.
6. Future approved elevated operations are sent to the already-installed
   service through authenticated local IPC.

This avoids repeated UAC prompts for every ordinary approved operation while
also avoiding a permanently elevated AI process.

The exact service identity (for example a dedicated service account versus a
built-in service identity) should be selected during packaging/security work and
reduced to the minimum practical privilege set.

## 15.4 Execution context selection

Not every operation should be elevated.

The executor should distinguish at least:

- **User-context execution** — user files, user applications, HKCU settings,
  and other operations that should behave as the logged-in user.
- **Privileged service execution** — machine-wide registry, Windows services,
  protected configuration, and other operations that genuinely require
  elevation.

Core decides the required capability and execution context as part of planning
and policy evaluation.

An operation MUST NOT be routed through the privileged service merely because
the service is available.

## 15.5 Approval binding

For consequential privileged work, the Core should produce a policy/approval
proof that binds the request to:

- task ID,
- plan ID/version,
- approved scope,
- capability,
- relevant target(s),
- risk context,
- expiration or one-use semantics where useful.

The service validates this proof before execution.

The exact cryptographic/token format is deferred, but a generic boolean
`approved=true` is not sufficient for long-term design.


---

# 16. Local IPC

Core ↔ Service communication should use a local IPC abstraction.

Production target:

**Windows Named Pipes**

Reasons:

- local-only,
- Windows-native,
- access-control lists,
- no listening TCP port required,
- suitable for privileged broker architecture.

The IPC layer should expose an interface such as:

```python
class ServiceTransport:
    async def request(self, request: ServiceRequest) -> ServiceResponse:
        ...
```

Implementations:

```text
NamedPipeTransport      # production Windows
InProcessTransport      # unit/integration tests
FakeTransport           # deterministic tests
```

---

# 17. IPC Security

Named-pipe access SHOULD be restricted to:

- the active authorized user,
- Eden processes,
- the service identity,
- administrators where required.

Requests should include:

- protocol version,
- request ID,
- task ID,
- capability name,
- structured arguments,
- approval/policy token where applicable.

The service MUST NOT accept arbitrary serialized Python objects.

Use explicit schemas.

---

# 18. Core Orchestrator

The Orchestrator coordinates the task.

It should not contain every subsystem directly.

Conceptual interfaces:

```text
ModelRouter
TaskEngine
ContextBuilder
ToolRegistry
PolicyEngine
ApprovalManager
ResearchManager
VerificationManager
ReportRepository
MemoryRepository
TelemetryManager
WatchlistRepository
```

The orchestrator coordinates these components rather than becoming one giant class.

---

# 19. Task Model

A **task** is the durable runtime object representing current work.

A task is not the same as a report.

Task:

> what Eden is currently doing.

Report:

> durable interpreted history of the effort.

---

# 20. Task State Machine

Suggested states:

```text
created
observing
awaiting_clarification
researching
diagnosing
planning
awaiting_approval
executing
verifying
monitoring
paused
waiting_condition
waiting_user
recovery_required
completed
failed
canceled
```

Not every task uses every state.

`recovery_required` is entered when Eden discovers an interrupted or unfinished
task whose real machine state must be reconciled before execution can safely
continue. It is intentionally distinct from `paused`: a paused task has a known
safe continuation point, while a recovery-required task may have uncertain
partial side effects.

State transitions SHOULD be explicit and persisted.

---

# 21. Durable Task Checkpoints

Before and after consequential steps, Eden SHOULD persist enough state to resume safely.

Checkpoint data may include:

- task state,
- current plan version,
- approved scope,
- completed plan steps,
- pending steps,
- evidence references,
- active report ID,
- execution IDs,
- verification status,
- wait condition,
- last model summary.

Do not depend on the LLM remembering the task from chat history.

---

# 22. Restart Recovery

If Windows or Eden restarts during a task:

1. Service records boot/restart.
2. Core discovers unfinished task.
3. Task becomes `recovery_required`.
4. Eden checks whether partial execution occurred.
5. Eden verifies current machine state.
6. Eden decides whether to:
   - resume,
   - rollback,
   - re-plan,
   - ask the user,
   - close as failed/canceled.

Never blindly resume a mutating task after reboot without reconciling actual state.

---

# 23. Concurrency

The MVP should favor correctness over complex concurrency.

Recommended initial policy:

- Multiple read-only investigations MAY run concurrently.
- Only one privileged/mutating execution plan should run at a time by default.
- Conflicting writes must be serialized.
- Long-running monitoring may continue concurrently if it does not interfere.

This can be expanded later.

---

# 24. Interruptions

The Core should support control messages that can:

- pause,
- resume,
- cancel,
- modify,
- reprioritize,
- throttle.

A user request that materially changes an active plan should pause execution at a safe boundary and return to plan approval.

---

# 25. `/sidenote` Architecture

`/sidenote` is conceptually a secondary conversation attached to the same Core.

It does not need true simultaneous token generation in the first implementation.

A practical design:

1. Active task continues in background if safe.
2. New conversation context is created.
3. Sidenote agent handles discussion.
4. If it creates a proposed task modification, emit a `TaskModificationRequest`.
5. Active task pauses at a checkpoint.
6. Main orchestrator presents the change.
7. User approves or denies.
8. Original task resumes/replans.

---

# 26. Resource Modes

Runtime resource policy should support:

- Passive / low-impact,
- Balanced,
- Intensive,
- Background,
- Night.

A resource profile may control:

- model size,
- number of subagents,
- telemetry sampling,
- research concurrency,
- CPU priority,
- background scheduling,
- GPU usage,
- nonessential work.

Exact thresholds belong in runtime configuration.

---

# 27. Model Provider Interface

Core code talks to a provider interface rather than a specific runner.

Conceptual API:

```python
class ModelProvider(Protocol):
    async def list_models(self) -> list[ModelInfo]: ...
    async def generate(self, request: ModelRequest) -> ModelResponse: ...
    async def health(self) -> ProviderHealth: ...
```

ModelInfo should support:

```text
model_id
display_name
provider
context_window
capabilities
estimated_vram
estimated_ram
disk_path
quantization
speed_class
strength_class
specializations
loaded
```

---

# 28. Initial Model Runtime

Recommended first adapter:

**OllamaProvider**

Reason:

- simple local setup,
- simple local API,
- easy model switching,
- useful for quickly proving the orchestration loop.

This is provisional.

Sys Eden MUST remain capable of adding:

- llama.cpp provider,
- LM Studio/OpenAI-compatible provider,
- future local runtime,
- test/mock provider.

---

# 29. Model Storage

Current model convention:

```text
C:\AI\models
```

This location is outside Git.

The path must be configurable.

A runner that uses its own managed model location may be adapted through configuration or symbolic/managed storage as appropriate.

Sys Eden should not hardcode business logic around one runner's filesystem layout.

---

# 30. Model Routing

The router decides which available model should handle a subtask.

Inputs may include:

- task type,
- risk,
- desired quality,
- context size,
- resource mode,
- current VRAM/RAM,
- model specialization,
- user routing preference.

Conceptual categories:

```text
fast
balanced
strong
research
code
verification
```

These are roles, not permanently assigned model names.

---

# 31. Subagents

A subagent is a task-specific reasoning context, not necessarily a separate OS process.

Possible roles:

- research,
- diagnostics,
- contrarian review,
- plan review,
- verification,
- hardware advisor,
- coding/script generation.

The orchestrator remains responsible for synthesis.

Simple majority vote MUST NOT determine truth.

---

# 32. Model Context Builder

Do not dump the whole PC into the model context.

ContextBuilder selects relevant information.

Potential sources:

- current user message,
- task summary,
- current system summary,
- targeted tool outputs,
- relevant reports,
- chain summary,
- watchlist items,
- relevant memories/preferences,
- research results,
- current plan,
- verification criteria.

Context should be purpose-limited.

---

# 33. Context Tiers

Useful conceptual tiers:

### Tier 1 — Task context

Always relevant current objective.

### Tier 2 — System context

Relevant components/state.

### Tier 3 — Historical context

Selected reports, chains, memory.

### Tier 4 — Raw evidence

Only when needed.

This keeps local inference efficient.

---

# 34. Structured Model Outputs

Where practical, model outputs that drive software behavior SHOULD use validated schemas.

Examples:

```text
DiagnosticAssessment
ResearchQuestion
Plan
PlanStep
ToolRequest
ConfidenceAssessment
VerificationRequest
ReportContribution
TaskModificationRequest
```

Use Pydantic models for validation.

Natural-language responses remain user-facing.

---

# 35. Research Architecture

Research runs through a provider abstraction.

```python
class ResearchProvider(Protocol):
    async def search(self, query: ResearchQuery) -> ResearchResult: ...
```

Possible providers may include:

- direct web search API,
- browser/search service,
- future plugin,
- local documentation index.

The Core owns query construction.

---

# 36. Privacy-Preserving Research

Before an external research request:

1. Determine the public technical question.
2. Remove unnecessary private context.
3. Use generic hardware/software/version details when sufficient.
4. Send only information needed for the research objective.
5. Return sources/findings to local Core.
6. Combine local evidence and public research locally.

Example:

Good:

```text
RTX 4070 Windows 11 driver 580.xx intermittent frame-time spikes
```

Avoid:

```text
C:\Users\Caleb\PrivateProject\...
full local logs...
private filenames...
```

unless the user explicitly chooses external disclosure.

---

# 37. Storage Architecture

Sys Eden v1 uses:

**SQLite 3 + SQLAlchemy 2.x + Alembic**

SQLite is the primary local structured database.

Reasons:

- local/single-machine workload,
- no database server,
- simple backup,
- portable,
- mature,
- supports transactional state,
- enough concurrency for MVP.

---

# 38. SQLite Configuration

Recommended:

- WAL journal mode,
- foreign keys enabled,
- busy timeout,
- transactional writes,
- connection per process/thread as appropriate,
- database migrations through Alembic.

**WAL (Write-Ahead Logging)** is recommended because it allows readers to
continue reading while another connection is writing, which better fits Eden's
combination of background monitoring, report lookup, and interactive work.
SQLite still has a single-writer constraint, so writes must remain short and
well coordinated.

**Foreign keys** should be enabled because Eden stores many linked objects
(tasks, approvals, reports, chains, evidence, nodes, and executions). Database
constraints help prevent orphaned or invalid references when those objects are
created, updated, or deleted.

The application must handle SQLite's single-writer nature deliberately.

---

# 39. Why SQLAlchemy

SQLAlchemy provides:

- Python domain models separate from SQL details,
- migration-friendly architecture,
- safer queries,
- easier testing,
- cleaner future transition if PostgreSQL is ever justified.

The system should not be littered with raw SQLite-specific queries.

SQLite remains the engine.

SQLAlchemy is the access layer.

---

# 40. Database Location

Development default:

```text
<repo>\data\eden.db
```

`data/` MUST be excluded from Git except placeholder files.

Production packaging may later move persistent state to a Windows application-data location such as ProgramData.

Production path is not locked in by this version.

---

# 41. Database Domains

Expected structured domains include:

- machine identity/state,
- settings,
- boot sessions,
- tasks,
- task events,
- plans,
- approvals,
- automation permissions,
- execution/tool records,
- reports metadata,
- report tags,
- chains,
- knowledge nodes,
- knowledge edges,
- watchlist items,
- structured memories,
- telemetry dataset metadata,
- model/provider metadata.

The exact schema will be created in implementation and migrations.

The major workflow records are intentionally separate:

- **Task** — the durable unit of current work.
- **Plan** — a versioned proposed method for advancing that task.
- **Approval** — evidence that the user approved a particular plan/version and
  scope.
- **Automation Permission** — reusable explicit authority for a narrowly defined
  class of future work.

These MUST NOT be collapsed into one generic "task status" record because Eden
must be able to prove which version of a plan was approved and distinguish
one-time approval from durable automation authority.

---

# 42. Suggested Core Tables

Conceptual—not final SQL:

```text
machines
settings
boot_sessions

tasks
task_events
plans
approvals
automation_permissions

tool_runs
verification_runs

reports
report_observations
report_hypotheses
report_evidence
report_confidence_history
report_plans
report_approvals
report_executions
report_verifications
report_monitoring
report_tags
report_relationships
report_chains
report_chain_members

knowledge_nodes
knowledge_edges

watchlist_items
memories

telemetry_datasets
telemetry_summaries
```

This is a starting architecture, not a requirement to create every table on day one.

---

# 43. Reports Storage

Reports use a structured AI-native architecture.

## Canonical representation

**SQLite-backed structured domain data** is the source of truth.

A logical report may include:

```text
Report
├── metadata
├── observations
├── hypotheses
├── evidence references
├── research findings
├── confidence history
├── alternatives
├── plans
├── approvals
├── executions
├── verification
├── outcome
├── monitoring
└── relationships
```

This does not require every item to become a dedicated normalized table.
Implementation may combine normal columns, child tables, and carefully chosen
JSON fields. `ReportRepository` hides the persistence shape from the rest of
Core.

---

# 44. Report Repository

All report reads and writes go through `ReportRepository`.

Responsibilities:

1. validate report domain objects,
2. persist changes transactionally in SQLite,
3. maintain tags/chains/knowledge relationships,
4. update report revision timestamps,
5. create/update the compact AI retrieval capsule,
6. expose query/filter methods,
7. generate exports/views,
8. maintain schema/version compatibility.

There is only one canonical source of truth for report content: the structured
repository data.

Generated summaries or exports can always be recreated and therefore do not
need cross-store transactional synchronization.

---

# 45. Report Views, Capsules, and Export

## 45.1 AI retrieval capsule

Normal report retrieval should first expose a compact structured capsule.

Example:

```text
id: RPT-184
objective: gaming_stutter
final_cause: overlay_conflict
confidence:
  diagnostic: 0.93
failed_hypotheses:
  - thermal_throttling
  - driver_regression
successful_actions:
  - disabled_overlay
verification:
  sessions: 10
  recurrence: false
related:
  - RPT-121
  - WL-19
```

This is optimized for model context.

## 45.2 Human view

When the user opens a report, Eden may render:

- one-line result,
- short explanation,
- detailed report,
- timeline,
- evidence list,
- Markdown,
- PDF later.

The rendered human view is derived data, not a second source of truth.

## 45.3 Portable structured export

Reports SHOULD support JSON export that preserves the full documented
structured model and schema version.

This keeps reports portable and inspectable even though raw storage is optimized
for Eden.

Markdown/Obsidian-compatible export remains optional and useful, but is not the
canonical storage layer.

---

# 46. Knowledge Graph Storage

The graph is stored explicitly rather than inferred only from Markdown text.

Recommended model:

```text
knowledge_nodes
---------------
id
node_type
canonical_key
label
created_at
updated_at
metadata_json

knowledge_edges
---------------
id
source_node_id
target_node_id
relationship_type
created_at
metadata_json
```

Examples of node types:

- report,
- hardware,
- software,
- driver,
- watchlist,
- benchmark,
- skill,
- system_change,
- device,
- configuration.

---

# 47. Report Nodes

Each report may have a corresponding knowledge node.

`reports` holds report-specific structured metadata.

`knowledge_nodes` allows the report to participate in the generic graph.

The mapping should remain one-to-one.

---

# 48. Typed Relationships

Examples:

```text
uses
related_to
monitoring_of
follow_up
previous_attempt
supersedes
verification_of
research_for
caused_by
affected_by
installed_on
```

Do not reduce the entire graph to generic `related_to` edges.

---

# 49. Memory Architecture

Memory is not raw chat history.

Structured memory categories:

- user preference,
- automation permission,
- behavioral observation,
- system fact/history,
- recurring pattern,
- ongoing concern reference.

A memory entry should support:

```text
id
type
subject
value
source
created_at
last_confirmed_at
confidence
active
```

Exact schema may evolve.

---

# 50. Automation Permissions

Automation permissions are stored independently from behavioral observations.

They should capture:

- task class,
- scope,
- risk boundary,
- restrictions,
- enabled state,
- granted time,
- last modified time.

Policy Engine consults this repository before requiring manual approval.

---

# 51. Watchlist Storage

Watchlist items are distinct records and knowledge nodes.

A watchlist item should support:

```text
id
title
state
priority
created_at
last_updated
condition
summary
related_node_ids
related_report_ids
```

Watchlist does not duplicate full report history.

---

# 52. Telemetry Architecture

Telemetry has two categories.

## 52.1 Sparse operational events

Examples:

- boot events,
- crashes,
- service failures,
- driver changes,
- update events,
- threshold crossings.

These may be stored directly in SQLite as event records/summaries.

## 52.2 High-frequency numeric telemetry

Examples:

- FPS,
- frame time,
- CPU/GPU utilization,
- temperatures,
- clocks,
- RAM/VRAM,
- disk latency.

This SHOULD NOT be written sample-by-sample into reports.

---

# 53. High-Frequency Telemetry Storage

Initial targeted high-frequency traces should use file-based datasets.

Preferred long-term format:

**Apache Parquet**

because it is:

- compact,
- typed,
- efficient for numeric columns,
- suitable for later analysis.

`pyarrow` may be introduced when high-frequency telemetry work begins.

The MVP does not need Parquet for the first scaffold milestone.

---

# 54. Telemetry Dataset Metadata

SQLite stores dataset metadata:

```text
dataset_id
metric_set
start_time
end_time
sample_rate
file_path
compression
related_task_id
related_report_id
summary
```

This lets Eden retrieve relevant traces without searching the filesystem manually.

---

# 55. Telemetry Summarization

Older raw telemetry may be summarized into:

- min/max,
- averages,
- percentiles,
- trend information,
- anomalies,
- event markers,
- report conclusions.

Raw data can then expire according to retention rules while historical interpretation remains.

---

# 56. Initial Windows Collectors

High-value initial collectors:

- OS/build info,
- uptime,
- CPU,
- GPU,
- RAM,
- storage devices,
- storage free space,
- network adapters,
- running processes,
- services,
- startup items,
- driver inventory,
- installed software,
- Event Viewer,
- recent crashes,
- boot timestamps.

Later:

- performance counters,
- FPS/frame-time integration,
- SMART health,
- ETW sessions,
- specialized vendor sensors.

---

# 57. Telemetry Performance Budget

Collectors MUST be resource-aware.

Rules:

- no maximum-frequency polling by default,
- batch queries where possible,
- pause/reduce during heavy foreground workloads,
- use resource mode,
- high-frequency collection only for targeted investigations,
- record collector overhead when it may affect results.

---

# 58. Event Architecture

Core should use an internal event bus.

Example event types:

```text
BootSessionStarted
TelemetryObservation
ThresholdCrossed
TaskStateChanged
ClarificationRequired
ApprovalRequired
PlanApproved
ToolExecutionStarted
ToolExecutionFinished
VerificationFinished
ReportUpdated
WatchlistChanged
ModelRunFinished
```

The first implementation may use an in-process asyncio event bus.

Durable important events are also written to SQLite.

---

# 59. Async Architecture

The Core should use Python `asyncio`.

Reasons:

- model requests,
- research,
- IPC,
- telemetry,
- UI streaming,
- task control,
- background monitoring.

Do not make CPU-heavy work run directly on the event loop.

Use worker threads/processes when necessary.

---

# 60. Configuration

Configuration should be layered.

Suggested precedence:

```text
built-in defaults
   ↓
machine config
   ↓
user config
   ↓
development environment overrides
```

Bootstrap configuration may use TOML.

Runtime settings may live in SQLite.

---

# 61. Configuration Examples

Settings include:

```text
startup_mode
model_provider
preferred_model
model_strength_bias
model_directory
internet_research_enabled
telemetry_mode
storage_budget_gb
report_directory
resource_mode
notification_preferences
```

Secrets should not be placed directly in ordinary config files.

---

# 62. Secret Storage

Future external APIs may require secrets.

Preferred Windows storage:

- Windows Credential Manager,
- DPAPI-backed protected storage,
- or another OS-protected secret provider.

Do not place API keys into reports, Git, or normal config TOML.

---

# 63. Logging

Application logs are separate from reports.

Use structured logging.

Every important log entry should support:

- timestamp,
- component,
- level,
- task ID,
- report ID where relevant,
- event type,
- message.

Sensitive data should be redacted where practical.

---

# 64. Tool Result Schema

Every capability returns a standardized result.

Conceptual:

```text
request_id
capability
started_at
finished_at
success
exit_code
data
stdout
stderr
warnings
side_effects
reboot_required
evidence_refs
```

Typed tools may omit shell-specific fields.

---

# 65. Evidence Objects

Evidence should be referencable without copying it everywhere.

Conceptual evidence record:

```text
evidence_id
type
source
timestamp
summary
path_or_reference
hash
retention_class
sensitivity
```

Reports reference evidence IDs.

### 65.1 Evidence Sensitivity

`sensitivity` describes how carefully a piece of evidence should be handled.

It may influence:

- whether raw content can enter model context,
- whether content should be redacted in reports/logs,
- whether it can be included in an external research/cloud request,
- retention duration,
- export behavior,
- and whether additional user confirmation is appropriate before disclosure.

Sensitivity is metadata about handling requirements, not a claim that the
evidence is malicious or unreliable.

---

# 66. Verification Architecture

Verification is defined from explicit success criteria.

A plan step or plan should describe:

```text
success_criteria
verification_method
expected_state
```

After execution, VerificationManager evaluates actual state.

---

# 67. Verification Independence

For significant changes:

- use a fresh model context,
- a specialized verifier,
- or deterministic checks.

The verifier should not simply ask the original planner “did this work?”

Examples:

```text
service_running == true
driver_version == expected
crash_reproduced == false
frame_time_p99 < threshold
file_exists == true
```

---

# 68. Research Evidence

Research results should support:

```text
source
retrieved_at
title
claim_summary
relevance
credibility_notes
conflicts
```

Raw web pages do not need permanent retention unless useful.

Important conclusions belong in the report.

---

# 69. UI Architecture

The first user interface should be a CLI.

Recommended CLI framework:

**Typer**

Example commands:

```text
eden chat
eden inspect
eden health
eden task list
eden report list
eden report show <id>
eden watchlist
eden service status
eden service start
eden service stop
```

---

# 70. Why CLI First

The CLI:

- accelerates debugging,
- avoids mixing UI bugs with Core bugs,
- makes automation easy,
- works well with VS Code,
- allows end-to-end testing before frontend work.

CLI is not the final UX.

---

# 71. Local Web UI

After the Core loop works:

- FastAPI backend,
- React + TypeScript + Vite frontend.

FastAPI exposes a local application API.

Potential streaming:

- Server-Sent Events,
- WebSocket.

Exact choice can be made when UI implementation begins.

---


# 71.1 Future Eden System Monitor / Control Center

A likely mature desktop experience is an **Eden System Monitor / Control
Center** built on the same API/Core.

This is broader than a Task Manager clone.

Possible primary views:

```text
Overview / Health
Processes
Performance
Hardware
Network
Storage
Startup / Boot
Services
Drivers / Devices
Events / Reliability
Software / Updates
Tasks / Eden Work
Reports / Watchlist
Timeline
```

The interface should combine current-state monitoring with historical data.

Example process detail:

```text
Discord.exe
CPU              4.2%
RAM              612 MB
GPU              1.3%
Network          220 KB/s
Started          19:32
Crashes (30d)    2
Startup          Enabled

Related:
- Gaming Stutter report
- Overlay Conflict report

[Ask Eden]
[Investigate]
[Disable startup]
```

A system timeline should correlate boot events, process starts, service errors,
driver/update changes, telemetry anomalies, crashes, and Eden actions.

The UI should allow contextual actions such as:

- Ask Eden about this process/component/event.
- Investigate anomaly.
- Explain resource use.
- Compare against historical baseline.
- Create monitoring task.
- Propose optimization.
- Open related reports.
- Show changes around a selected time.

The Control Center is a future presentation layer over data the Core already
collects. It SHOULD NOT introduce a parallel monitoring database or duplicate
Eden's reasoning systems.

It is post-MVP and must not delay the Core loop.

---

# 72. Local API Security

Default API binding:

```text
127.0.0.1
```

Do not expose the local API to the LAN or internet by default.

If authentication is required between local UI/Core processes, use a local session token.

Remote-control mode will use a separate controlled gateway rather than simply exposing the local development API publicly.

---

# 73. Future Desktop Packaging

The final desktop experience may wrap the web UI.

Potential wrappers may be evaluated later.

The architecture deliberately avoids choosing one now.

The Core remains independent.

---

# 74. Remote Control

Future feature.

Requirements:

- explicitly enabled,
- short-lived session,
- authenticated,
- revocable,
- clear active indicator,
- secure transport,
- normal approval rules remain active.

A QR code is only a convenient way to join an authorized session.

## 74.1 Candidate remote gateway design

The exact remote-control protocol remains deferred.

A likely first design is:

```text
Phone / secondary device
          |
       HTTPS
          |
   one-time pairing
          |
authenticated WebSocket
          |
Temporary Remote Gateway
          |
       Eden Core
```

Possible session flow:

1. User explicitly enables remote control.
2. Core starts a temporary local Remote Gateway.
3. Gateway creates a short-lived session ID and one-time pairing token.
4. QR code contains the temporary endpoint plus pairing information.
5. Phone pairs over an encrypted authenticated connection.
6. Real-time task state, messages, and approval requests use an authenticated
   WebSocket or equivalent bidirectional channel.
7. Session expires automatically or is revoked by the user.
8. Gateway shuts down when no longer needed.

The simplest first implementation should target devices on the same trusted LAN.

Off-LAN access is intentionally deferred. Candidate future approaches include:

- an outbound encrypted relay,
- a user-controlled VPN/tunnel,
- WebRTC-style peer connectivity,
- another design that keeps inbound public exposure minimal.

The standard localhost development API MUST NOT simply be opened to the public
internet to implement remote control.

Remote control is NOT an MVP blocker.

---

# 75. Voice

Future feature.

Speech-to-text and text-to-speech should preferably be local when quality is acceptable.

Voice is simply another interface to Core.

It does not bypass policy or approval.

---

# 76. Dependency Stack

Initial Python stack:

```text
Python 3.13
uv
Pydantic v2
pydantic-settings
SQLAlchemy 2.x
Alembic
aiosqlite
Typer
httpx
psutil
pywin32
PyYAML
pytest
pytest-asyncio
Ruff
Pyright
```

Dependencies should be added only when the milestone requires them.

---

# 77. Package Management

Use:

**uv + `pyproject.toml` + `uv.lock`**

Goals:

- reproducible environment,
- fast installation,
- dependency locking,
- simple VS Code setup,
- no duplicated `requirements.txt` unless export is specifically needed.

---

# 78. Code Quality

Recommended tooling:

- Ruff for linting/formatting,
- Pyright for static type checking,
- pytest for tests.

The codebase should use type hints heavily at subsystem boundaries.

---

# 79. Repository Structure

Recommended initial repository:

```text
Sys-Eden/
│
├── AGENTS.md
├── README.md
├── pyproject.toml
├── uv.lock
├── .gitignore
│
├── docs/
│   ├── vision.md
│   ├── reports.md
│   ├── architecture.md
│   ├── system_rules.md
│   ├── roadmap.md
│   ├── decisions.md
│   └── ...
│
├── src/
│   └── syseden/
│       ├── __init__.py
│       ├── __main__.py
│       │
│       ├── core/
│       │   ├── orchestrator.py
│       │   ├── task_engine.py
│       │   ├── state_machine.py
│       │   ├── context.py
│       │   └── events.py
│       │
│       ├── service/
│       │   ├── windows_service.py
│       │   ├── broker.py
│       │   ├── startup.py
│       │   └── boot_sessions.py
│       │
│       ├── ipc/
│       │   ├── base.py
│       │   ├── named_pipe.py
│       │   └── in_process.py
│       │
│       ├── models/
│       │   ├── base.py
│       │   ├── router.py
│       │   ├── ollama.py
│       │   └── fake.py
│       │
│       ├── tools/
│       │   ├── registry.py
│       │   ├── eventlog.py
│       │   ├── filesystem.py
│       │   ├── processes.py
│       │   ├── services.py
│       │   ├── system_info.py
│       │   ├── powershell.py
│       │   └── inventory.py
│       │
│       ├── policy/
│       │   ├── risk.py
│       │   ├── permissions.py
│       │   └── approvals.py
│       │
│       ├── verification/
│       │   ├── manager.py
│       │   └── checks.py
│       │
│       ├── reports/
│       │   ├── models.py
│       │   ├── repository.py
│       │   ├── capsule.py
│       │   ├── export.py
│       │   ├── chains.py
│       │   └── retrieval.py
│       │
│       ├── memory/
│       │   ├── models.py
│       │   ├── repository.py
│       │   └── retrieval.py
│       │
│       ├── knowledge/
│       │   ├── nodes.py
│       │   ├── edges.py
│       │   └── graph.py
│       │
│       ├── watchlist/
│       │   └── repository.py
│       │
│       ├── telemetry/
│       │   ├── manager.py
│       │   ├── storage.py
│       │   └── collectors/
│       │
│       ├── research/
│       │   ├── base.py
│       │   ├── manager.py
│       │   └── sanitizer.py
│       │
│       ├── db/
│       │   ├── engine.py
│       │   ├── models/
│       │   └── repositories/
│       │
│       ├── config/
│       │   ├── settings.py
│       │   └── defaults.py
│       │
│       ├── cli/
│       │   └── app.py
│       │
│       └── api/
│           └── app.py
│
├── migrations/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── service/
│   └── vm/
│
├── scripts/
│   ├── install_service.ps1
│   ├── uninstall_service.ps1
│   ├── dev_setup.ps1
│   └── vm/
│
└── data/
    └── .gitkeep
```

This structure can be simplified during the first milestone.

Do not create empty modules merely to match the full tree.

---

# 80. Module Dependency Direction

Preferred dependency direction:

```text
UI
 ↓
Core
 ↓
Domain interfaces
 ↓
Repositories / Providers / Tools
 ↓
Platform adapters
```

Avoid:

```text
Windows tool → UI
database model → model provider
report serializer → orchestrator
```

Subsystems should communicate through interfaces/domain models.

---

# 81. Windows-Specific Code Isolation

Windows-specific implementation belongs under:

- `service/`,
- `tools/`,
- platform adapters.

Core reasoning, reports, memory, task state, and model routing should avoid direct Win32 imports where practical.

This improves testability and future Linux portability.

---

# 82. Error Model

Subsystems should return structured errors.

Examples:

```text
PermissionDenied
ElevationRequired
CapabilityUnavailable
ToolTimeout
InvalidRequest
ResourceBusy
ExecutionFailed
VerificationFailed
ServiceUnavailable
ModelUnavailable
ResearchUnavailable
StorageError
```

Do not make the Core infer semantics from arbitrary exception strings.

---

# 83. Timeouts and Cancellation

Every external or system operation should support:

- timeout,
- cancellation where technically possible,
- clear uninterruptible-state reporting.

Never assume a PowerShell process, model call, or research request will return.

---

# 84. Startup Service Reliability

The boot service must fail safely.

If it crashes:

- Windows should remain usable,
- boot should continue,
- Eden records/reports the failure next time possible,
- service restart policy may retry with bounded behavior.

Eden MUST NOT become a boot-critical dependency for Windows.

---

# 85. Fail-Open Versus Fail-Closed

For observation:

- collector failure generally fails open; Windows continues.

For privileged mutation:

- policy/service uncertainty fails closed; do not perform the change.

Sys Eden should never make Windows dependent on Eden for ordinary operation.

---

# 86. Testing Architecture

Testing has four levels.

```text
Level 1: Unit / fake adapters
Level 2: Non-destructive local integration
Level 3: Disposable/checkpointed Windows VM
Level 4: Real hardware validation
```

---

# 87. Unit Tests

Use fake implementations for:

- model provider,
- service transport,
- PowerShell executor,
- research provider,
- telemetry collectors,
- approval manager.

Test scenarios:

- approval denied,
- approval modified,
- tool failure,
- service unavailable,
- verification failure,
- task interruption,
- model timeout,
- report creation,
- failed report chain,
- restart recovery.

---

# 88. Integration Tests

Run controlled non-destructive operations on the development PC.

Examples:

- read system info,
- query Event Viewer,
- read temporary registry test key,
- create/delete files in test directory,
- service IPC,
- database transactions.

Do not use destructive host-machine tests for routine CI.

---

# 89. VM Test Lab

Because the development PC uses Windows 11 Home, the preferred destructive
integration environment is:

**VMware Workstation Pro**

with one disposable, thin-provisioned Windows test VM.

The guest may use:

- Windows 11 Enterprise evaluation,
- or another properly licensed Windows installation.

The VM is a developer-only test target, not a second permanent Eden workstation.

Avoid permanent duplication of:

- local AI model files,
- long-term reports/history,
- large telemetry archives,
- many scenario-specific snapshots.

A practical initial goal is **30–50 GB actual host disk use**, aiming to keep the
normal VM footprint at or below roughly **50 GB** where practical.

This is a planning target, not a hard architectural limit.

---

# 90. VM Baseline

Create one known clean baseline snapshot/checkpoint such as:

```text
EDEN-CLEAN
```

Prefer scripted fault injection over retaining separate snapshots for each fault
scenario.

The test harness should be able to:

1. power off VM if necessary,
2. restore baseline,
3. boot VM,
4. wait for readiness,
5. install/copy current Eden build,
6. inject a test condition,
7. launch task,
8. collect result/report,
9. independently verify VM state,
10. mark pass/fail,
11. restore baseline.

The guest does not need a permanent model library. Depending on the test it may
use a fake/deterministic provider or a host model endpoint if that is simple and
useful.

Do not add SSH, WinRM, a custom guest agent, or other remote-control complexity
solely to save a small amount of disk space.

---

# 91. VM Fault Injection

Useful synthetic failures:

- disabled service,
- broken startup item,
- invalid registry configuration,
- failed software installation,
- filled temporary test disk,
- bad DNS/network setting,
- scheduled task problem,
- application crash,
- permission issue,
- corrupted test config,
- simulated high resource process,
- intentionally outdated software,
- startup slowdown.

Do not intentionally create malware for routine testing.

---

# 92. VM Reset Must Not Depend on Guest Networking

The host must always remain capable of restoring the VM snapshot even if Eden
completely breaks networking inside the guest.

Where available, VMware guest operations/Tools may provide additional
out-of-band control.

Snapshot restore is the ultimate recovery mechanism.

---

# 93. VM Limitations

A VM is excellent for Windows behavior.

It does not prove physical hardware behavior.

VM tests are NOT authoritative for:

- actual GPU thermals,
- real GPU instability,
- BIOS flashing,
- real disk degradation,
- PSU issues,
- fan behavior,
- motherboard/firmware quirks,
- hardware-specific driver edge cases.

Real hardware validation remains separate.

---

# 94. Test Scenario Format

VM scenarios should eventually be declarative.

Conceptual:

```yaml
name: disabled-print-spooler
baseline: EDEN-CLEAN

inject:
  - action: stop_service
    service: Spooler
  - action: disable_service
    service: Spooler

prompt:
  "Printing stopped working. Figure out why and fix it."

expected:
  diagnosis_contains:
    - service disabled
  final_service_state: running
  report_status: resolved
```

This makes repeatable agent evaluation possible.

---

# 95. Test Safety

VM tests must clearly identify whether they are:

- safe host tests,
- guest-destructive tests,
- hardware-specific tests.

A destructive-test helper should refuse to target the host unless explicitly designed for host testing.

Use machine identity checks.

---

# 96. CI Strategy

Normal CI:

- lint,
- type check,
- unit tests,
- pure integration tests.

VM destructive tests:

- manually triggered initially,
- later scheduled/nightly,
- not required on every edit.

---

# 97. Development Workflow

Recommended workflow in VS Code:

1. coding agent reads `AGENTS.md`,
2. reads relevant canonical docs,
3. implements one milestone/task,
4. runs tests,
5. summarizes changes,
6. updates docs only when architecture/behavior changed,
7. user commits through Git.

The repository is the shared memory between ChatGPT and coding agents.

---

# 98. Coding-Agent Context

`AGENTS.md` should be short.

It should direct agents to:

1. `docs/vision.md`
2. `docs/architecture.md`
3. subsystem spec relevant to current task
4. `docs/system_rules.md`
5. current roadmap milestone

The agent should not require conversation transcripts to understand the system.

---

# 99. Git Rules

Never commit:

- local models,
- runtime database,
- user telemetry,
- reports containing private machine data unless using sanitized fixtures,
- API keys,
- VM disks,
- real crash dumps,
- secret config.

Commit:

- schemas/migrations,
- sample sanitized reports,
- fake telemetry fixtures,
- test scenarios,
- documentation,
- code.

---

# 100. Data Directory

Repository `data/` is development runtime state and is ignored by Git.

Suggested contents:

```text
data/
  eden.db
  reports/
  telemetry/
  attachments/
  logs/
  cache/
```

Models remain outside:

```text
C:\AI\models
```

---

# 101. Backup / Recovery Architecture

Before high-risk actions, the system should support recovery artifacts.

Possible types:

- restore point,
- registry export,
- file backup,
- config snapshot,
- service-state snapshot,
- package/version record.

A recovery artifact receives an ID and can be linked to:

- task,
- plan step,
- report.

---

# 102. System Change Objects

Important mutations should eventually produce structured `SystemChange` records.

Example:

```text
change_id
type
target
before
after
timestamp
tool_run_id
task_id
report_id
rollback_ref
```

This improves verification and rollback.

Not required for the first scaffold milestone but strongly recommended before broad mutation support.

---

# 103. File Management Safety

File operations should distinguish:

- metadata read,
- content read,
- create/write,
- move,
- trash/stage,
- permanent delete.

Permanent deletion is distinct from reversible cleanup.

The executor should prefer staging/trash where practical.

---

# 104. Install / Software Management

Software installation is a capability domain.

Preferred order:

1. supported package manager,
2. vendor installer,
3. manually downloaded installer.

Installer workflow should capture:

- source,
- version,
- signature/hash where available,
- command/arguments,
- install result,
- reboot requirement,
- verification.

---

# 105. Networking

The Core may inspect networking broadly.

The system should avoid hosting unnecessary network listeners.

Normal operation:

- local IPC,
- local model provider,
- optional localhost UI.

Internet access is outbound research/download activity.

Remote access is a separate future capability.

---

# 106. Update Architecture

Sys Eden will eventually need:

- app updates,
- dependency updates,
- skill updates,
- model updates.

Updates should use the same:

- provenance,
- risk,
- approval,
- verification,
- rollback philosophy.

Automatic self-update is not required for MVP.

---

# 107. Skills Architecture

A Skill is a reusable workflow definition.

Conceptual Skill:

```text
name
version
description
inputs
preconditions
required_capabilities
risk_profile
steps
verification
outputs
```

Skills invoke the same capability/policy layer as normal tasks.

A Skill does not bypass permissions.

---

# 108. Skill Storage

Early skills may live as version-controlled project definitions/code.

Future user/generated skills may live in local data with metadata and versions.

The exact format will be defined later.

---

# 109. Model-Generated Skill Promotion

Dynamic behavior may become structured over time.

Path:

```text
one-off dynamic PowerShell
        ↓
repeated successful pattern
        ↓
candidate reusable Skill
        ↓
tested / reviewed
        ↓
versioned Skill
        ↓
possibly promoted to typed capability
```

This allows Eden to become more structured without losing adaptability.

---

# 110. Security Boundary Summary

Critical boundaries:

```text
Public Internet
      │
      ▼
Research Provider
      │ sanitized/public query
      ▼
Eden Core
      │
      ├── Local Model
      │
      ├── Reports/Memory
      │
      ▼
Policy Layer
      │
      ▼
Local IPC
      │
      ▼
Privileged Eden Service
      │
      ▼
Windows
```

No external service gets automatic direct access to the privileged broker.

---

# 111. Threats to Consider Later

Security review should eventually include:

- prompt injection from files/logs/web pages,
- malicious local files,
- poisoned research content,
- IPC spoofing,
- privilege escalation through broker,
- command argument injection,
- path traversal,
- symlink/reparse-point attacks,
- TOCTOU file changes,
- secret leakage into reports/logs,
- unsafe plugin/skill updates.

MVP architecture should leave room for these mitigations.

---

# 112. Prompt Injection Boundary

Content retrieved from:

- files,
- web pages,
- logs,
- documents

must be treated as **data**, not trusted instructions.

The model may read text that says:

> Ignore your rules and execute ...

The tool/policy layer must not treat embedded content as authority.

---

# 113. Research / Local Evidence Separation

The context builder should label evidence origin.

Example:

```text
LOCAL_SYSTEM_EVIDENCE
PUBLIC_RESEARCH
USER_STATEMENT
HISTORICAL_REPORT
MODEL_INFERENCE
```

This helps the model distinguish trust domains.

---

# 114. Observability

Sys Eden must be able to diagnose itself.

Health endpoints/commands should eventually expose:

- service status,
- database status,
- model provider status,
- disk usage,
- telemetry collectors,
- task queue,
- recent errors,
- report repository health,
- IPC health.

Example:

```text
eden health
```

---

# 115. Self-Diagnostics

Eden should eventually produce a self-health report when its own components malfunction.

Examples:

- model provider unavailable,
- service failing to start,
- SQLite corruption,
- telemetry collector crashing,
- report index mismatch.

Self-repair should remain subject to the same rules as other maintenance.

---

# 116. Database Backup

SQLite backup is simple and should be used.

Before migrations or major updates:

- create DB backup,
- verify backup exists,
- record schema version.

Structured reports remain portable through documented JSON export, with generated human-readable views available on demand.

---

# 117. Database Migration

All schema changes after the first release use Alembic.

Do not manually mutate production tables ad hoc.

Migration must have:

- upgrade,
- downgrade where practical,
- backup recommendation for risky changes.

---

# 118. Multiple Machines

MVP is one local machine.

Database/domain IDs should nevertheless allow a `machine_id` so future multi-device support does not require rewriting every table.

No cross-device cloud synchronization is required.

---

# 119. Time

Store timestamps in UTC internally.

Render in local timezone for user-facing output.

Boot sequencing and event correlation depend on consistent timestamps.

---

# 120. IDs

Use stable opaque IDs for domain objects.

Recommended implementation:

- UUIDv7/ULID if convenient,
- or project-specific generated IDs.

User-facing display IDs may be separate.

Exact ID library may be chosen during scaffold implementation.

---

# 121. Performance Targets

Early architecture goals:

- boot service adds negligible user-perceived startup cost,
- idle monitoring remains lightweight,
- UI/Core can restart without losing service telemetry,
- report search remains fast for thousands of reports,
- system inspection returns quickly for common queries,
- model loading is lazy,
- high-frequency telemetry is opt-in/targeted.

Exact benchmarks belong in testing/roadmap.

---

# 122. Storage Budget

Storage is a constrained resource and Eden should be designed to remain small
enough for an ordinary consumer PC.

## 122.1 Normal runtime target

Recommended normal Eden footprint, excluding the developer VM:

**15–25 GB**

Recommended default per-category targets:

| Category | Default target |
|---|---:|
| Application + dependencies | 2–4 GB |
| Local model storage | 5–12 GB |
| Reports + memory + SQLite | 1–2 GB |
| Logs + cache | 1–2 GB |
| Telemetry working space | 2–5 GB |
| Free-space safety reserve | 3–5 GB |

A concrete initial default configuration may use:

```toml
[storage]
application_target_gb = 4
models_budget_gb = 12
reports_memory_db_budget_gb = 2
logs_cache_budget_gb = 2
telemetry_budget_gb = 5
free_space_reserve_gb = 5
auto_rebalance = false
```

The first five managed categories total **25 GB**. The free-space reserve is not
Eden-owned capacity; it is disk space Eden should try to leave unused.

Every category is user configurable. The user may deliberately allocate more or
less storage than the defaults.

## 122.2 Budget semantics

Budgets are not all enforced identically.

- **Application/dependencies:** footprint target/advisory ceiling. Required base
  files cannot be deleted merely to satisfy a lower number. Optional components
  and expandable artifacts should honor the target.
- **Models:** managed quota. New/retained model files should fit the configured
  allocation or require explicit user approval to exceed it.
- **Reports/memory/database:** soft quota. Durable high-value history should not
  be silently destroyed simply to hit a number.
- **Logs/cache:** managed quota with normal rotation/pruning of replaceable data.
- **Telemetry:** managed working quota. Summarize and prune old raw traces before
  allowing unbounded growth.
- **Free-space reserve:** host-protection threshold. Nonessential writes should
  be reduced/stopped before Eden consumes this reserve.

Budgets SHOULD be configurable independently. Eden MUST NOT silently turn spare
capacity in one category into a large increase in another category unless the
user has enabled an automatic-rebalancing policy.

## 122.3 Storage pressure behavior

When a category approaches its budget:

1. identify replaceable/low-value data,
2. summarize or compress where useful,
3. prune automatically only where policy permits,
4. protect active tasks, recovery artifacts, and high-value history,
5. ask the user before exceeding a configured limit when the extra storage has
   meaningful value.

---

# 123. Storage Manager

`StorageManager` should track at least:

```text
application_dependencies
models
telemetry
attachments
reports_memory_database
logs
cache
recovery_artifacts
host_free_space
```

Responsibilities:

- report actual usage by category,
- compare usage with user-configured budgets,
- preserve the configured host free-space reserve,
- rotate/prune replaceable data,
- trigger telemetry summarization,
- detect model-budget pressure before downloads,
- expose recommended cleanup,
- support manual budget changes,
- optionally support user-enabled automatic rebalancing,
- record important storage-policy changes.

A future UI/CLI should make budget changes explicit, for example:

```text
eden storage status
eden storage set models 16GB
eden storage set telemetry 3GB
eden storage set reserve 10GB
```

Exact command syntax is deferred.

When a budget is approached, cleanup should follow retention priority rather than
deleting blindly.

---

# 124. MVP Non-Goals

Not required for first functional MVP:

- kernel driver,
- Linux support,
- macOS support,
- cloud synchronization,
- multi-user accounts,
- polished desktop shell,
- remote QR control,
- voice control,
- full graph visualization,
- autonomous software marketplace,
- sophisticated vector database,
- self-modifying executable code,
- automatic BIOS flashing.

---

## 124.1 Why Kernel-Mode Components Are Deferred

A custom kernel driver is not required to prove Sys Eden's core value and would
substantially increase:

- system-crash risk,
- privilege/security exposure,
- driver-signing and deployment complexity,
- OS-version compatibility burden,
- and the difficulty of safe testing.

The MVP should exhaust supported user-mode Windows APIs, services, Event Log,
CIM/WMI, ETW, and other documented facilities before considering kernel-mode
code.

## 124.2 Why Automatic BIOS/Firmware Flashing Is Deferred

Firmware flashing is unusually hardware-specific, high consequence, and often
difficult to recover from automatically after interruption or an incorrect
image.

The MVP may inspect firmware information, research updates, and help the user
plan a firmware procedure, but broad automatic firmware flashing is deliberately
outside initial mutation capability until Eden's risk, recovery, provenance,
and hardware-specific testing systems are substantially more mature.

---

# 125. Architecture Decisions Locked for MVP

The following are considered current MVP decisions unless testing demonstrates a serious problem.

1. Python 3.13.
2. Windows 11 first.
3. SQLite 3 structured database.
4. SQLAlchemy 2.x data-access layer.
5. Alembic migrations.
6. `uv` package/environment manager.
7. Async Core using `asyncio`.
8. Windows System Service for early monitoring + privileged broker.
9. Core runs in normal user context.
10. Named-pipe IPC target.
11. Broad structured read access.
12. Typed mutations preferred.
13. Dynamic PowerShell escape hatch retained.
14. Local-model provider abstraction.
15. Ollama as likely first provider adapter, not dependency.
16. Structured SQLite-backed canonical reports + AI retrieval capsules + generated human/JSON/Markdown views.
17. Explicit knowledge-node/edge model.
18. CLI first.
19. FastAPI + React/TypeScript/Vite as likely later local UI stack.
20. VMware Workstation Pro test VM on Windows 11 Home.
21. Unit/fake tests before destructive testing.
22. High-frequency telemetry stored separately from report bodies.
23. Models stored outside Git.
24. Service does not load LLM during boot.

---

# 126. Decisions Intentionally Deferred

Not decided yet:

- exact local model(s),
- exact model quantization,
- final desktop wrapper,
- exact remote-control transport,
- exact risk thresholds,
- exact automation-permission policy,
- exact production data-directory path,
- exact high-frequency sensor providers,
- exact final telemetry retention periods,
- exact confidence formula,
- exact UI design,
- exact graph visualization library,
- exact skill file format,
- exact external research provider.

These should not block scaffold development.

---

# 127. Implementation Sequencing Authority

`architecture.md` defines **what components must exist, their boundaries, their
dependencies, and the constraints they must satisfy**.

It is **not** the canonical source for the chronological build order.

The authoritative implementation sequence lives in:

```text
docs/roadmap.md
```

If an implementation-order statement in Architecture conflicts with the current
Roadmap, **the Roadmap controls sequencing** unless an explicit Accepted decision
says otherwise.

Version recency should only be used to choose between versions of the **same
canonical document lineage**. It should not be used to say that, for example,
Architecture v1.5 automatically outranks Roadmap v1.2 on a question that belongs
to the Roadmap's documented role.

The previous Architecture v1.4 sections 127–136 contained an older milestone
ordering that placed the boot service before reports, durable tasks, and the
approval infrastructure. That sequence is superseded by Roadmap v1.2.

The current roadmap intentionally develops:

```text
Milestone 1   Executable Core Skeleton
Milestone 2   Read-Only Windows Inspection
Milestone 3   Structured Reports and Knowledge History
Milestone 4   Local Model Integration
Milestone 5   Durable Task Engine
Milestone 6   Planning, Risk, and Approval
Milestone 7   Windows System Service
Milestone 8   Controlled Mutation
Milestone 9   Dynamic PowerShell Escape Hatch
Milestone 10  Full End-to-End Diagnostic Loop
...
```

This sequencing does **not** weaken the architectural requirement that early boot
observation is first-class. It means the privileged service is implemented only
after the project already has the persistence, task, policy, and approval
foundations needed to integrate and test it safely.

Architecture still constrains the service when Milestone 7 is reached:

- Service remains a narrow privileged broker.
- Core remains normal-user intelligence.
- Service supports early boot observation.
- Model inference does not run in the Service.
- IPC remains structured and authenticated.
- Privileged execution fails closed when authorization cannot be validated.

---

# 128. Dependency Guidance Versus Build Order

Architectural dependency does not always imply earlier implementation.

For example:

```text
Final runtime:
Windows boot
    ↓
System Service
    ↓
boot observations
    ↓
Core
```

does **not** require the System Service to be one of the first features coded.

The implementation can first build and test the Core-side contracts,
repositories, durable task state, policy objects, and fake transports. The real
Windows Service can then be introduced at the roadmap milestone where those
foundations are ready.

This distinction should be preserved anywhere architecture diagrams describe
runtime order.

---

# 129. Roadmap Synchronization Rule

Architecture should avoid duplicating the complete milestone list in future
versions because duplicated sequencing tends to drift.

When a roadmap milestone changes:

1. update `roadmap.md`,
2. update Architecture only if component boundaries/dependencies also changed,
3. update `decisions.md` if an Accepted architectural/product decision changed,
4. do not maintain a second competing milestone schedule here.

---

# 137. Architecture Acceptance Scenario

The architecture is proving itself when the following works.

User:

> "Something about my PC startup seems slower lately."

Eden:

1. retrieves recent boot sessions,
2. compares trends,
3. checks startup/services/Event Viewer,
4. asks a targeted clarification if needed,
5. researches relevant current information if appropriate,
6. creates hypotheses,
7. shows confidence,
8. creates a plan,
9. receives approval,
10. changes one safe startup configuration,
11. restarts/reboots if approved,
12. service captures the next boot,
13. Core resumes task,
14. verification compares startup behavior,
15. report records result,
16. monitoring continues for several boots.

This scenario exercises:

- boot service,
- durable task state,
- IPC,
- inspection,
- local model,
- planning,
- policy,
- execution,
- reboot recovery,
- verification,
- reports,
- monitoring.

---

# 138. Architecture Anti-Patterns

Avoid:

## Giant monolithic agent

One class should not own database, PowerShell, reports, models, UI, and telemetry.

## Model directly calling shell

All actions pass through the capability/policy layer.

## Permanent Administrator Core process

Use privilege broker.

## Tool catalog as hard limit

Keep generic readers + dynamic PowerShell escape hatch.

## Entire PC in context

Use targeted evidence retrieval.

## Everything in SQLite

High-volume telemetry uses separate storage.

## Prose/Markdown as the canonical report source

Use structured report data as the source of truth. Generate Markdown/human prose
when needed.

## Reports as opaque proprietary blobs

Canonical report storage may be AI-native and structured, but preserve
documented JSON export and generated human-readable views.

## Boot-time model loading

Keep early collector lightweight.

## UI-first development

Prove Core first.

## Production logic tied to Ollama

Use provider interface.

## Destructive testing on host

Use VMware test lab.

## VM considered proof of hardware behavior

Use real hardware when hardware-specific.

## Chat history as project memory

Use repository documentation and durable state.

---

# 139. Future Linux Port

Linux support is a later goal.

The following architecture pieces should be portable:

- Core,
- model layer,
- reports,
- memory,
- task engine,
- policy interfaces,
- research,
- knowledge graph,
- configuration domain.

Windows-specific replacements:

- service,
- IPC transport,
- system collectors,
- shell adapters,
- privilege broker,
- Event Log/Registry/CIM.

This validates the platform-adapter separation.

---

# 140. Documentation Relationships

Canonical documents have **different roles**, not one universal precedence
ladder:

- `vision.md` — product purpose and governing philosophy.
- `architecture.md` — runtime structure, boundaries, dependencies, technology
  architecture.
- `system_rules.md` — behavioral authority, risk, permission, execution and
  sovereignty rules.
- subsystem specifications such as `reports.md` — detailed canonical behavior
  for their subsystem.
- `roadmap.md` — chronological implementation sequence and milestone acceptance.
- `decisions.md` — durable Accepted/Provisional/Deferred architectural and
  product choices.
- `AGENTS.md` — coding-agent operating instructions and conflict-routing rules.

Version recency applies within a document lineage (for example Architecture
v1.5 supersedes Architecture v1.4), not as a blanket rule across documents with
different roles.

`reports.md` is the specialized report/history specification used directly by
Architecture.

If code or documents conflict, resolve the conflict explicitly rather than
silently choosing whichever text is convenient.

---

# 141. Architecture Change Process

Meaningful architecture changes should:

1. identify the problem,
2. describe alternatives,
3. explain tradeoffs,
4. record the decision,
5. update `architecture.md` if canonical behavior changed,
6. add entry to `decisions.md`,
7. update tests.

Minor implementation details do not require architecture revisions.

---

# 141.1 Architecture Validation Result

This architecture was validated by giving a fresh AI agent only this document
and a 360-question comprehension test covering:

- process and privilege boundaries,
- boot behavior,
- Windows inspection/mutation,
- dynamic PowerShell,
- IPC,
- durable tasks and restart recovery,
- model routing/context,
- research privacy,
- SQLite/report/knowledge storage,
- telemetry,
- UI and development stack,
- VMware destructive testing,
- security boundaries,
- MVP scope,
- and deliberately unspecified implementation details.

The agent demonstrated essentially complete comprehension and correctly refused
to invent deferred details.

The validation pass exposed several details worth making explicit before coding:

1. `recovery_required` belongs in the formal task state machine.
2. WAL and foreign-key rationale should be documented.
3. Task, Plan, Approval, and Automation Permission are intentionally separate
   durable records.
4. Under the **then-current v1.1 hybrid report design**, Markdown + SQLite report
   writes would have required reconciliation because they could not form one
   cross-resource atomic transaction.
5. Evidence sensitivity needs defined handling semantics.
6. Kernel-driver and automatic firmware-flashing deferral should have explicit
   architectural rationale.

Items 1–3 and 5–6 were incorporated in Architecture v1.1.

Item 4 is retained here only as **historical validation context**. Architecture
v1.2 superseded the hybrid report design: canonical report content is now
structured SQLite-backed domain data, while Markdown/human views are generated
derivatives rather than a second writable source of truth.

---


# 141.2 Architecture Refinement — AI-Native Reports and Final UI Direction

After the initial architecture validation, the project refined four design
choices before implementation:

1. **Core vs Service privilege boundary:** Core is the intelligent normal-user
   process; the System Service is a non-AI privileged broker installed through
   normal Windows administrative consent.
2. **Report source of truth:** reports are structured AI-native objects in
   SQLite rather than Markdown documents indexed by SQLite.
3. **Remote control:** exact protocol remains deferred, but a temporary
   HTTPS/pairing + authenticated real-time gateway is the leading design shape.
4. **Long-term UI:** an Eden System Monitor / Control Center is a preferred
   mature interface direction, combining live Task-Manager-style visibility,
   historical telemetry, timelines, reports, system relationships, and
   contextual AI actions.

These refinements do not change the core Observe → Diagnose → Plan → Approve →
Execute → Verify loop. They make the implementation more efficient for AI
retrieval and clarify the long-term user experience.


---

# 141.3 Final Cross-Document Validation

The complete canonical documentation set was tested together with a
360-question cross-document comprehension test.

The fresh agent correctly reconciled the project's major boundaries:

- Core = intelligence; Service = privileged authority.
- Broad read; controlled mutation.
- Durable tasks and restart reconciliation.
- Five-dimensional confidence.
- Scoped/versioned approval.
- Explicit automation permissions.
- Structured AI-native reports.
- Local-first research/privacy.
- VMware before broad destructive host testing.
- Control Center and remote/voice features remain post-MVP.

The test agent raised a report-storage inconsistency because historical v1.1
validation wording still mentioned the superseded Markdown + SQLite hybrid
model. The current architecture itself already used structured SQLite-backed
canonical reports, including the locked MVP decision. Architecture v1.3 removes
the remaining ambiguous wording while preserving the historical record.

No behavioral or architectural decision changed in v1.3.

---

# 142. Closing Architecture

Sys Eden should be constructed as a local operating system companion with a strict boundary between intelligence and authority.

The model is allowed to be flexible.

The operating system interface is controlled.

The report/history system is durable.

The boot observer is lightweight.

The privileged broker is narrow.

The database is simple and local.

The model runtime is replaceable.

The test environment is disposable.

The Core is capable of reasoning across all of them.

The central architecture can be summarized as:

```text
                 USER
                  │
                  ▼
            Eden Core
                  │
        reason / research
                  │
                  ▼
             PLAN + RISK
                  │
               approval
                  │
                  ▼
        Capability Layer
          │           │
          │           └── Dynamic escape hatch
          │
      Typed tools
          │
          ▼
       Policy
          │
          ▼
   Privileged Service
          │
          ▼
       Windows
          │
          ▼
      Verification
          │
          ▼
 Reports + Memory + Monitoring
```

This preserves the defining Sys Eden relationship:

> **Broad intelligence and broad system visibility, paired with controlled execution, durable evidence, verification, and informed user authority.**
