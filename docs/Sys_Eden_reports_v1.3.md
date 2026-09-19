# Sys Eden — Reports System

> **Document role:** Canonical specification for Sys Eden reports, report chains, monitoring records, watchlist integration, and report-oriented knowledge retrieval  
> **Status:** Reports v1.3 — retention aligned with configurable storage budgets  
> **Depends on:** `vision.md`  
> **Purpose:** Define what a report is, when one is created, how it changes over time, how reports relate to each other, and how Eden uses them as durable system memory

---

## 1. Purpose of This Document

Reports are one of the central long-term memory structures in Sys Eden.

This document defines the report system in enough detail that a new developer or AI agent can understand:

- What a report represents.
- What a report does not represent.
- When a report should be created.
- When an existing report should be updated instead.
- When a report should be closed.
- How report status differs from report state.
- How reports relate to monitoring and watchlist concerns.
- How report chains work.
- How confidence should be represented.
- How reports preserve evidence and execution history.
- How reports should be searched and retrieved.
- How reports fit into the larger Obsidian-inspired knowledge graph.
- How reports should remain concise without losing important technical history.

The report system is intended to make Sys Eden better over time.

A successful report system should prevent Eden from repeatedly rediscovering the same problem, repeating failed fixes, losing track of unresolved concerns, or forgetting how the computer changed.

This document is a subsystem specification. It should remain consistent with `vision.md`.

Normative language:

- **MUST / MUST NOT** — required or prohibited.
- **SHOULD / SHOULD NOT** — strong default unless there is a specific reason to deviate.
- **MAY** — optional or context-dependent.

---

## 2. Core Definition

A **report** is a structured, persistent record of one coherent Sys Eden effort or objective.

Examples:

- Investigating a crash.
- Diagnosing GPU instability.
- Monitoring storage health.
- Researching an upgrade.
- Optimizing gaming performance.
- Cleaning storage.
- Performing system maintenance.
- Installing or repairing software.
- Tracking a recurring concern.
- Verifying the long-term result of a previous repair.

A report represents the **whole meaningful effort**, not one command, one message, one reasoning step, or one subagent call.

### 2.1 Canonical representation

The canonical Sys Eden report is an **AI-native structured object**, not a
prose document.

Its primary job is to preserve compact, typed, queryable knowledge for future
Eden instances. It MAY contain short natural-language summaries, but full
human-readable prose is a derived view rather than the source of truth.

Conceptually, a report may contain structured collections such as:

```text
Report
├── objective
├── observations
├── hypotheses
├── evidence_refs
├── research_findings
├── confidence_history
├── alternatives
├── plans
├── approvals
├── executions
├── verification
├── outcome
├── monitoring
└── relationships
```

The user does not need to read this raw representation. Eden can render it into
a concise human summary, detailed explanation, timeline, Markdown document, or
other view when requested.

This improves AI retrieval efficiency and avoids storing repetitive prose when
structured fields communicate the same information more precisely.


A report should answer:

> What happened, why did Eden care, what did Eden learn, what did Eden do, what happened afterward, and what should future Eden know?

---

## 3. What a Report Is Not

A report is **not**:

- A raw chat transcript.
- A dump of every internal thought.
- A list of every command with no interpretation.
- One report per execution step.
- One report per subagent.
- One report per tool call.
- One report per log entry.
- One report per notification.
- A replacement for raw telemetry storage.
- A replacement for task state.
- A replacement for configuration.
- A replacement for a watchlist item.
- A generic note with no clear purpose.

A report MAY reference any of those systems, but it remains a distinct structured record.

---

## 4. The Single-Effort Rule

The most important report-boundary rule is:

> **One report represents one coherent effort or objective.**

If one investigation includes:

1. User complaint.
2. Diagnostics.
3. Research.
4. Diagnosis.
5. Plan.
6. Execution.
7. Verification.
8. Follow-up monitoring.

that can all belong in **one report** if it is one continuous effort toward one objective.

Do NOT automatically create:

- “Diagnosis Report”
- “Repair Report”
- “Verification Report”

for one ordinary troubleshooting session.

Artificial fragmentation makes retrieval worse and creates meaningless chains.

---

## 5. When to Create a New Report

A new report SHOULD be created when at least one of the following is true.

### 5.1 New objective

The user or Eden begins a meaningfully different objective.

Example:

- Existing report: monitor SSD health.
- New objective: replace the SSD.

These are related, but they are different efforts.

### 5.2 New attempt after a previous effort has ended

A previous repair attempt closed or failed, and a later effort uses a new approach.

Example:

- Report A: GPU crash repair using driver rollback — failed.
- Two weeks later:
- Report B: GPU crash repair using background-software isolation — resolved.

These should be separate reports linked in the same chain.

### 5.3 Monitoring becomes a distinct long-running objective

A repair ends, but Eden opens a separate post-fix monitoring effort.

Example:

- Problem report resolves a driver crash.
- Separate monitoring report tracks stability for 30 days.

This is appropriate because the repair effort is complete while monitoring becomes a new objective.

### 5.4 Research is independently valuable

A research task may become its own report if the research itself is the objective.

Example:

- “Research the best GPU upgrade options under $600.”

That is not merely supporting research inside another repair report. It is the task.

### 5.5 A recurring issue returns after the prior report is closed

If the old effort is complete and the same problem returns later, create a new report and link it to the previous chain.

Do not reopen old history merely because the symptom returned unless the original report was deliberately left open for ongoing recurrence tracking.

### 5.6 User explicitly requests separation

The user may request separate reports for organizational reasons.

Eden should comply unless it would make the report system misleading.

---

## 6. When NOT to Create a New Report

Do not create a new report when the work is still clearly part of the same active effort.

Examples:

- Gathering one additional log.
- Running another diagnostic.
- Asking another subagent.
- Performing verification.
- Executing the approved repair.
- Retrying a substantially equivalent low-risk step.
- Updating the confidence score.
- Adding evidence.
- Writing the final summary.
- Recording short-term monitoring that is still part of the active repair workflow.

These normally belong in the current report.

---

## 7. Report State Versus Status

State and status are separate concepts and MUST NOT be merged.

### 7.1 State

**State** answers:

> Is this report still actively editable as a current effort?

Allowed core states:

- **Open**
- **Closed**

#### Open

The effort is active, unfinished, under investigation, being monitored, awaiting action, or otherwise still current.

#### Closed

The effort is no longer active as a current work item.

A closed report can still be read, linked, searched, and referenced.

Closed does not necessarily mean success.

### 7.2 Status

**Status** answers:

> What is the report's current outcome or operational meaning?

Core statuses:

- **Active**
- **Resolved**
- **Failed**
- **Archived**
- **Canceled**

Optional future statuses may be added carefully, but the core vocabulary should remain stable.

#### Active

The effort is ongoing.

Typical combination:

- State: Open
- Status: Active

#### Resolved

The objective was successfully completed and verified.

Typical combination:

- State: Closed
- Status: Resolved

A report MAY temporarily remain Open + Resolved during a short verification/monitoring phase if the implementation finds that useful, but the meaning must remain clear.

#### Failed

The effort ended without successfully resolving the objective.

Typical combination:

- State: Closed
- Status: Failed

Failure is not a useless report. Failed reports are important history.

#### Archived

The report is retained primarily for history/reference and is not considered active operational context.

Typical combination:

- State: Closed
- Status: Archived

Archiving may be used for very old, obsolete, superseded, or intentionally de-emphasized reports.

#### Canceled

The effort was intentionally stopped before reaching a normal conclusion.

Typical combination:

- State: Closed
- Status: Canceled

Canceled should be distinguishable from Failed.

Example:

- Failed: Eden tried and could not solve the issue.
- Canceled: User decided not to continue.

---

## 8. Valid State/Status Combinations

The system SHOULD validate obviously inconsistent combinations.

Common combinations:

| State | Status | Meaning |
|---|---|---|
| Open | Active | Normal active report |
| Closed | Resolved | Successfully completed |
| Closed | Failed | Unsuccessful completed attempt |
| Closed | Archived | Historical / de-emphasized |
| Closed | Canceled | Intentionally stopped |

Potential transitional combinations:

| State | Status | Meaning |
|---|---|---|
| Open | Resolved | Fix succeeded but formal follow-up/monitoring is still finishing |
| Open | Failed | Rare; failure recognized but report intentionally remains open for immediate reconsideration |

The implementation SHOULD avoid ambiguous transitional states unless they provide real value.

---

## 9. Report Identity

Every report MUST have a stable unique identifier.

The identifier MUST NOT change when:

- Title changes.
- Tags change.
- Status changes.
- Report is moved.
- File name changes.
- Report is added to a chain.

Recommended properties:

- Unique.
- Machine-readable.
- Short enough for references.
- Independent from the human title.

Example conceptual IDs:

- `RPT-2026-000184`
- UUID-based ID
- ULID-based ID

Exact implementation is an architecture decision.

Human-readable titles are separate.

---

## 10. Report Title

A report title SHOULD be concise, specific, and useful in search results.

Good:

- `GPU Driver Instability During Gaming`
- `SSD Health Degradation Monitoring`
- `Windows Boot Time Investigation`
- `RTX 4070 Upgrade Research`
- `Storage Cleanup — September 2026`

Poor:

- `Computer Problem`
- `Issue`
- `Test`
- `Report 5`
- `Fixing Stuff`

Titles SHOULD describe the objective or concern rather than the final solution.

A title MAY be updated if the diagnosis becomes clearer.

Example:

Initial:

`Gaming Stutter Investigation`

Later:

`Gaming Stutter — Background Overlay Conflict`

The report ID remains unchanged.

---

## 11. Core Report Header

Every report SHOULD have structured metadata.

Minimum recommended header:

```yaml
id:
title:
created:
last_updated:
state:
status:
priority:
purpose_tags:
component_tags:
confidence:
monitoring:
chain:
related_reports:
related_nodes:
```

Exact serialization may use YAML frontmatter, JSON, database fields, or another structured representation.

The information model matters more than the syntax.

---

## 12. Required Metadata Fields

### 12.1 ID

Stable unique report identity.

### 12.2 Title

Human-readable report name.

### 12.3 Created Date

When the report began.

### 12.4 Last Updated Date

Most recent meaningful update.

This should not change merely because a formatter touched whitespace.

### 12.5 State

Open / Closed.

### 12.6 Status

Active / Resolved / Failed / Archived / Canceled.

### 12.7 Priority

Represents importance or urgency.

Priority implementation may use:

- Low
- Normal
- High
- Critical

or a more detailed system later.

Priority SHOULD reflect operational importance, not emotional intensity.

### 12.8 Purpose Tags

Describe what kind of work the report represents.

Core purpose tags:

- Problem
- Monitoring
- Research
- Optimization
- Upgrade
- Maintenance

Additional future tags may include:

- Installation
- Cleanup
- Benchmark
- Security
- Configuration
- Recovery

New tags should be added only when they improve retrieval.


### 12.8.1 Purpose Tag Cardinality

A report MAY have more than one Purpose Tag when the work genuinely spans
multiple purposes.

Example:

```yaml
purpose_tags: [Problem, Monitoring]
```

However, tags should describe real report characteristics rather than being
added merely to improve search recall.

### 12.9 Component Tags

Describe affected system areas.

Core component tags:

- CPU
- GPU
- RAM
- Storage
- Network
- Drivers
- OS
- PSU

Likely future tags:

- Motherboard
- Firmware
- BIOS/UEFI
- Audio
- Bluetooth
- USB
- Display
- Cooling
- Battery
- Software
- Security
- Filesystem

Component tags SHOULD remain broad enough for indexing.

Specific devices belong in related knowledge nodes.

---


### 12.9.1 Component Tag Cardinality

A report MAY contain multiple Component Tags.

Example:

```yaml
component_tags: [GPU, Drivers, OS]
```

This is preferred when an issue legitimately crosses several broad system
areas.

Specific device identity still belongs in related knowledge nodes rather than
creating highly specific component tags.

## 13. Confidence in Reports

Reports SHOULD preserve the confidence model used during the effort.

Core dimensions:

- Diagnostic Confidence
- Research Confidence
- Execution Confidence
- Safety Confidence
- Overall Confidence

### 13.1 Confidence is time-sensitive

Confidence changes during investigation.

The report SHOULD distinguish important confidence checkpoints rather than storing only one unexplained final number.

Useful checkpoints:

- Initial assessment.
- Pre-plan.
- Pre-execution.
- Post-verification.

Not every task requires all four checkpoints.

### 13.2 Confidence history

A report MAY contain:

```text
Initial Diagnostic Confidence: 42%
After telemetry collection: 71%
After reproduction test: 88%
Final Diagnostic Confidence: 93%
```

The reason for meaningful confidence changes SHOULD be recorded.

### 13.3 Final confidence

Final confidence should represent the best-supported understanding at closure.

A failed report may still have high diagnostic confidence and low execution confidence.

Example:

- Diagnostic: 92%
- Research: 89%
- Execution: 38%
- Safety: 91%
- Overall: limited by execution uncertainty

That is meaningful information.

### 13.4 No fake precision requirement

The report format may display percentages, labels, or calibrated scores depending on implementation.

The system MUST NOT imply statistical precision it cannot justify.

---


## 13.5 Human Summary and AI Capsule

A report SHOULD support two small derived summaries:

### Human summary

A concise explanation optimized for the user. This can be generated on demand
and may be cached.

### AI retrieval capsule

A compact structured representation optimized for model context and retrieval.

Neither derived summary replaces the canonical structured report.

---

## 14. Recommended Report Body

A general report body SHOULD support these sections.

Not every report requires every section.

### 14.1 Summary

Short description of the objective and current/final conclusion.

### 14.2 Trigger / Origin

What caused the report to exist?

Examples:

- User request.
- Monitoring alert.
- Watchlist escalation.
- Scheduled maintenance.
- Follow-up from another report.
- Eden-detected concern.

### 14.3 Symptoms / Observations

What was observed?

Keep facts separate from interpretation when useful.

### 14.4 Evidence

Important evidence used.

Examples:

- Logs.
- Telemetry.
- Event Viewer.
- Error messages.
- Driver versions.
- Performance metrics.
- SMART values.
- System configuration.
- User-observed behavior.

Raw evidence MAY be linked rather than pasted.

### 14.5 Research

Relevant outside information.

Include:

- Important source conclusions.
- Conflicts.
- Version-specific findings.
- Vendor guidance.
- Community evidence when relevant.
- Research confidence.

Avoid turning reports into full web archives.

### 14.6 Diagnosis / Analysis

What Eden thinks is happening and why.

Should distinguish:

- Facts.
- Inferences.
- Hypotheses.
- Unknowns.

### 14.7 Alternatives Considered

Record plausible alternative diagnoses or solutions that materially influenced the decision.

This prevents future Eden from needlessly rediscovering the same branches.

### 14.8 Plan

The approved plan.

Include:

- Actions.
- Why.
- Risk.
- Privileges.
- Reversibility.
- Success criteria.
- Backup approach if applicable.

### 14.9 Approval

Record enough information to understand what the user approved.

Do not store meaningless text such as only `approved: yes`.

Useful approval context:

- Approved plan version.
- Approval time.
- Any user modifications.
- Any denied alternatives.
- Automation permission used, if any.

### 14.10 Execution

Record important actions performed.

This should summarize the meaningful execution trace.

Do not paste thousands of commands or log lines unless needed.

### 14.11 Verification

Record:

- Success criteria.
- Tests performed.
- Before/after comparison.
- Verification evidence.
- Verdict.

### 14.12 Outcome

Examples:

- Resolved.
- Partially resolved.
- Failed.
- Canceled.
- Monitoring continues.

### 14.13 Monitoring

If monitoring applies:

- Why monitoring is needed.
- Start time.
- End condition.
- Sampling strategy if relevant.
- Alert thresholds.
- Current monitoring status.

### 14.14 Follow-Up

Any future action that should occur.

### 14.15 Relationships

Links to:

- Parent/previous reports.
- Follow-up reports.
- Chain.
- Watchlist item.
- Hardware/software nodes.
- Skills.
- Relevant configuration.

---

## 15. Report Lifecycle

A typical report may move through:

1. Detection or user request.
2. Report creation.
3. Initial evidence gathering.
4. Clarification.
5. Research.
6. Diagnosis / hypothesis formation.
7. Confidence assessment.
8. Plan generation.
9. User approval.
10. Execution.
11. Verification.
12. Outcome determination.
13. Monitoring if needed.
14. Closure.
15. Later linkage to follow-up reports if the concern returns.

Not every report includes execution.

Examples:

- Research report may stop after recommendation.
- Monitoring report may never execute a change.
- Upgrade report may end with a purchase recommendation.
- Failed report may end after diagnosis if no safe fix is available.

---

## 16. Opening a Report

A report SHOULD be opened when there is enough substance to justify durable tracking.

Do not create reports for every casual question.

A report becomes appropriate when at least one is true:

- The issue may require multiple steps.
- The issue may recur.
- The user or Eden may need historical context later.
- Monitoring is involved.
- System changes may be made.
- Risk is meaningful.
- Research is substantial.
- The task affects long-term device state.
- A watchlist concern is being actively investigated.

A short factual answer such as:

> “What GPU do I have?”

does not need a report.

---

## 17. Updating a Report

An open report SHOULD be updated when new information materially changes understanding.

Meaningful updates include:

- New evidence.
- New diagnosis.
- Confidence change.
- Plan change.
- Approval.
- Execution result.
- Verification result.
- Monitoring event.
- Priority change.
- Status change.
- New relationship.

Do not write a report revision for every minor internal event.

---

## 18. Closing a Report

A report should close when its current effort is finished.

Possible closure reasons:

- Objective resolved.
- Repair failed and no further immediate attempt is planned.
- User canceled.
- Research completed.
- Monitoring period completed.
- Report superseded by a new effort.
- Issue no longer relevant.
- User declined further work.

Closure MUST include an outcome summary.

A closed report SHOULD include:

- Final diagnosis/conclusion.
- Final confidence.
- Actions performed.
- Verification result.
- Reason for closure.
- Remaining uncertainty.
- Follow-up or monitoring requirements.
- Links to any continuation report.

---

## 19. Reopening a Report

Reopening should be rare.

Prefer a new linked report when:

- Significant time has passed.
- A new attempt begins.
- The old report already represents a completed effort.
- The environment has meaningfully changed.
- The problem recurs after a verified resolution.

Reopening is appropriate when:

- The report was closed accidentally.
- A short-term continuation was expected.
- Closure happened before final data arrived.
- The effort is clearly the same uninterrupted task.

The goal is historical clarity.

---

## 20. Failed Reports

A failed report is a first-class knowledge asset.

It SHOULD preserve:

- What was tried.
- Why it was tried.
- Evidence supporting it.
- Why it failed or why success could not be verified.
- Errors encountered.
- What was ruled out.
- What remains possible.
- Untested alternatives.
- Any safety limitations.
- Next recommended approach.

Future Eden SHOULD read failed reports before attempting another repair for the same concern.

---

## 21. Partial Success

Not every result is binary.

A report may record:

- Major symptom resolved, minor issue remains.
- Performance improved but target not reached.
- Root cause identified but repair deferred.
- Temporary workaround successful.
- Repair succeeded but long-term stability unverified.

Status may remain Active until the user and system define the final outcome.

Do not falsely label partial improvement as Resolved.

---


## 21.1 Terminal Partial Success

Partial success needs an explicit terminal rule so the report does not remain
Open forever merely because some value was achieved.

If an effort ends and the **primary success criteria were not met**, the report
SHOULD normally close as:

- State: `Closed`
- Status: `Failed`

while the Outcome section clearly records the partial value achieved.

Example:

```text
State: Closed
Status: Failed
Outcome: Partial success

Average frame time improved by 18%, but the original stutter still recurs and
the defined success criterion of eliminating the recurring spikes was not met.
```

`Failed` in this context means **the report's defined objective was not fully
achieved**. It does not mean the effort produced no useful result.

If the user and Eden deliberately revise the success criteria and agree that
the achieved result satisfies the revised objective, the report MAY instead
close as `Resolved`, provided the revised criteria and the reason for the
change are recorded.

This avoids incorrectly labeling unresolved problems as Resolved while still
preserving useful partial improvements.

## 22. Monitoring Reports

Monitoring is a distinct report purpose.

A monitoring report represents ongoing observation of a target or concern.

Examples:

- SSD wear monitoring.
- GPU temperature monitoring.
- Crash recurrence monitoring.
- Post-repair stability monitoring.
- Gaming performance tracking.
- Boot-time trend monitoring.

### 22.1 Monitoring target

Every monitoring report MUST define what is being monitored.

Examples:

- `Samsung 980 Pro health`
- `RTX 4070 hotspot temperature`
- `game stutter recurrence`
- `Windows boot time`

### 22.2 Monitoring reason

Why is monitoring justified?

Example:

> Intermittent storage latency was observed but not severe enough to justify immediate replacement.

### 22.3 Monitoring boundary

Monitoring MUST be:

- Time-bound, or
- Condition-bound.

Examples:

- 30 days.
- 20 gaming sessions.
- Until issue recurs.
- Until drive health drops below threshold.
- Until user cancels.
- Until another report resolves the concern.

Avoid vague “monitor indefinitely” language when a measurable condition can express the intent.

### 22.4 Monitoring frequency

Sampling should match the question.

Examples:

- Daily health check.
- Every boot.
- During gaming sessions only.
- Continuous high-frequency capture during a short diagnostic window.
- Weekly maintenance check.

### 22.5 Monitoring updates

Do not append every raw telemetry sample to the report.

The report should store:

- Significant events.
- Summaries.
- Trends.
- Threshold crossings.
- Interpretation.
- Links to raw data if retained.

### 22.6 Monitoring outcome

At the end, the report should conclude whether:

- Concern was disproven.
- Concern remained stable.
- Concern worsened.
- Concern became actionable.
- Monitoring transitioned to another report.
- Monitoring ended by user decision.

---

## 23. Post-Fix Monitoring

Successful repairs SHOULD normally be followed by a monitoring period appropriate to the issue.

Examples:

- Driver crash: monitor 14 days / 10 gaming sessions.
- Boot issue: monitor 10 successful boots.
- Storage error: monitor until defined health criteria remain stable for 30 days.

The exact default should be configurable.

Post-fix monitoring may:

- Remain inside the repair report if brief.
- Become a separate monitoring report if substantial or long-running.

Use a separate report when monitoring becomes its own objective.

---

## 24. Watchlist Integration

The watchlist and report system are related but different.

### 24.1 Watchlist item

A watchlist item represents a concern worth remembering.

It does not need to contain the full investigation history.

### 24.2 Report

A report represents a structured effort involving that concern.

One watchlist item may link to multiple reports over time.

Example:

Watchlist item:

`Possible SSD degradation`

Related reports:

1. Monitoring — initial SMART anomaly.
2. Problem report — first repair attempt.
3. Problem report — later replacement.
4. Monitoring — post-replacement verification.

### 24.3 Creating a watchlist item from a report

Eden MAY create or recommend a watchlist item when a report identifies an unresolved concern.

The watchlist entry should link back to the report.

### 24.4 Closing a watchlist item

A watchlist item may close when:

- Underlying issue is resolved.
- Monitoring proves it non-concerning.
- Hardware/software is removed.
- User explicitly dismisses it after informed review.

The associated reports remain historical.

---

## 25. Report Chains

A **report chain** groups separate reports that share the same underlying concern, target, or historical thread.

A chain is not a workflow.

A chain is a relationship across efforts.

### 25.1 Chain example

Underlying concern:

`Intermittent GPU instability`

Possible chain:

1. Monitoring report — rare crashes observed.
2. Problem report — driver rollback attempt — failed.
3. Problem report — background overlay removal — resolved.
4. Monitoring report — 30-day post-fix validation.

### 25.2 Chain rule

Create a chain when:

> Multiple distinct reports are meaningfully related to the same underlying concern or target and seeing them together improves understanding.

### 25.3 Do not force chains

Many reports will be standalone.

Do not create:

- Empty reports.
- Artificial “link reports.”
- One-step reports.

just to produce a visually impressive chain.

### 25.4 Chain identity

A chain SHOULD have:

- Stable chain ID.
- Human-readable title.
- Created date.
- Related report IDs.
- Current concern state.
- Optional related knowledge nodes.

Example:

```yaml
chain_id: CHN-00031
title: Intermittent GPU Instability
reports:
  - RPT-00091
  - RPT-00104
  - RPT-00137
```


### 25.5 Primary Chain Membership

A report SHOULD belong to **zero or one primary report chain**.

The primary chain represents the main underlying concern or historical thread
for that report.

If a report is relevant to several other concerns, use:

- `related_reports`
- typed relationships
- related knowledge nodes

rather than placing the same report into several primary chronological chains.

This keeps chains readable and prevents one report from creating ambiguous
history in multiple incident timelines.

A future graph layer MAY still represent secondary cross-links between chains.

### 25.5 Chain ordering

Default order SHOULD be chronological.

The UI may also group by:

- Status.
- Report type.
- Severity.
- Relevance.

### 25.6 Chain summary

For large chains, Eden SHOULD be able to generate a concise chain summary.

Example:

> First observed in March. Driver rollback failed. Overlay conflict later identified. Fix resolved issue in May. No recurrence across 42 gaming sessions.

This helps retrieval without opening every report.

---

## 26. Related Reports Without a Chain

Not every relationship requires a chain.

Examples:

- A storage cleanup report references a game-install report.
- A GPU upgrade report references previous gaming benchmark reports.
- A network problem report references a Windows update report.

These can use `related_reports` without implying one underlying concern.

---

## 27. Knowledge Graph Integration

The report system should be compatible with an Obsidian-inspired knowledge graph without requiring Obsidian.

Reports become one class of node inside a broader connected knowledge model.

Possible node classes:

- Report.
- Hardware component.
- Software package.
- Driver.
- OS build.
- Watchlist concern.
- User preference.
- Benchmark.
- Skill.
- System change.
- Device.
- Model.
- Configuration item.

### 27.1 Example

```text
RTX 4070
  |
  +-- uses --> NVIDIA Driver 580.xx
  |
  +-- related report --> Gaming Stutter Investigation
  |
  +-- related report --> GPU Temperature Monitoring
  |
  +-- watchlist --> Hotspot Temperature Trend
```

### 27.2 Reports as evidence nodes

Reports should provide durable interpretations of events.

Knowledge nodes should provide durable entities.

Example:

- Node: `RTX 4070`
- Node: `NVIDIA Driver 580.xx`
- Report: `Gaming Stutter Investigation`
- Watchlist: `Recurring Driver Instability`

The report links facts and reasoning to those entities.

### 27.3 Structured portability and generated views

Report portability does not require Markdown to be the canonical store.

The system SHOULD support a structured export such as JSON that preserves:

- report identity,
- typed fields,
- evidence references,
- confidence history,
- state/status,
- tags,
- chains,
- knowledge relationships,
- and schema version.

Human-readable Markdown MAY be generated from that structured report on demand.

An Obsidian-compatible export may therefore contain links such as:

```markdown
Related Hardware: [[RTX 4070]]
Related Driver: [[NVIDIA Driver 580.xx]]
Watchlist: [[Recurring GPU Instability]]
Previous Report: [[RPT-00124]]
```

but this is a **view/export**, not necessarily the source of truth.

### 27.4 Obsidian is optional

Obsidian MAY be useful as an external viewer/editor during development.

Sys Eden MUST NOT require Obsidian as a runtime dependency.

Eden owns its knowledge model.

---

## 28. Search and Retrieval

Reports are useful only if Eden can retrieve the right ones quickly.

### 28.1 Metadata-first retrieval

Eden SHOULD search metadata before reading full reports.

Searchable fields should include:

- ID.
- Title.
- Created date.
- Updated date.
- State.
- Status.
- Priority.
- Purpose tags.
- Component tags.
- Chain.
- Related hardware/software.
- Monitoring state.
- Confidence.
- Outcome.
- Keywords.

### 28.2 Retrieval strategy

When solving a new problem, Eden SHOULD:

1. Identify likely components/keywords.
2. Search relevant report metadata.
3. Inspect chains/watchlist relationships.
4. Rank likely relevant reports.
5. Load compact AI retrieval capsules for the best candidates.
6. Load the full structured report only when needed.
7. Load raw evidence only when necessary.

This avoids consuming model context with complete historical records when a
small structured capsule already contains the useful result.


### 28.3 AI retrieval capsules

Each mature report SHOULD be able to expose a compact model-oriented capsule.

Example:

```text
RPT-184
type: Problem
subject: Gaming stutter
components: [GPU, Drivers]
final_cause: overlay_conflict
diagnostic_confidence: 0.93
failed_hypotheses:
  - thermal_throttling
  - driver_regression
actions:
  - disabled_overlay
verification:
  - 10 gaming sessions
  - no recurrence
related:
  - RPT-121
  - WL-19
```

A capsule is not a lossy replacement for the full report. It is the normal
first layer loaded into AI context.

Capsules SHOULD prioritize:

- objective,
- final conclusion,
- strongest evidence,
- important failed hypotheses/attempts,
- successful actions,
- verification,
- unresolved concerns,
- confidence,
- relationships.

They may be regenerated whenever the underlying structured report changes.

### 28.4 Semantic retrieval

A future vector/semantic index MAY supplement structured metadata.

Semantic retrieval SHOULD NOT replace structured metadata.

Structured relationships are more deterministic for known entities and chains.

### 28.5 Recency

Recent reports may deserve ranking preference, but older reports can remain highly relevant.

Eden should distinguish:

- Latest attempt.
- Latest successful attempt.
- Latest related monitoring.
- Most similar historical issue.

---

## 29. Report Storage

The canonical report should be persisted as structured local data.

For the current architecture:

- **SQLite** stores the canonical structured report model and relationships.
- **JSON export** provides a portable machine-readable representation.
- **AI retrieval capsules** provide compact model context.
- **Markdown/human views** are generated when the user wants to inspect,
  export, or read the report.
- A separate telemetry store holds high-volume raw measurements.
- An optional semantic index may supplement retrieval later.

This design makes reports efficient for Eden while preserving user ownership and
portability.

### 29.1 The logical report may span structured records

A report does not need to be one database row or one giant JSON blob.

The logical report may reference structured records for:

- observations,
- hypotheses,
- evidence,
- plans,
- approvals,
- executions,
- verification,
- monitoring,
- relationships.

The Report Repository presents those records as one coherent domain object.

### 29.2 Human readability is generated, not mandatory storage

Users SHOULD be able to inspect any report, but the underlying storage does not
need to resemble the rendered document.

Eden should be able to generate:

- a one-line result,
- a short human summary,
- a detailed explanation,
- a chronological timeline,
- Markdown,
- structured JSON.

The generated view MUST reflect the canonical structured data rather than
becoming a second independent source of truth.

### 29.3 Portability

A user SHOULD be able to export reports in a documented structured form without
requiring Sys Eden to interpret a proprietary opaque blob.

JSON is the preferred portable structured export for the initial architecture.

Markdown remains a useful optional human/Obsidian-oriented export.

---

## 30. Evidence Attachments

Reports may refer to evidence too large or inappropriate to embed.

Examples:

- Event log export.
- Screenshot.
- Benchmark CSV.
- Telemetry trace.
- Crash dump.
- Installer log.
- Configuration snapshot.

Evidence attachments SHOULD have:

- Stable ID.
- Type.
- Timestamp.
- Source.
- Associated report.
- Optional checksum.
- Retention policy.

The report should explain why the attachment matters.

---

## 31. Raw Logs Versus Reports

Raw logs and reports serve different purposes.

### Raw logs

- High-volume.
- Machine-oriented.
- Shorter retention.
- Detailed evidence.
- Often hard to interpret directly.

### Reports

- Low-volume.
- Human/agent-oriented.
- Long-lived.
- Structured interpretation.
- Preserve decisions and outcomes.

Eden SHOULD summarize raw logs into durable report evidence when the logs are important.

A report should not duplicate megabytes of logs.

---

## 32. Report Retention

Reports are generally high-value historical knowledge and SHOULD be retained much longer than raw telemetry.

A report may be:

- Active.
- Closed.
- Archived.
- Exported.
- Compressed/summarized in the distant future.

Deletion of reports SHOULD be rare compared with deletion of raw telemetry.

### 32.1 Safe pruning

Reports, memory, and SQLite share a configurable storage budget in the initial
storage policy. The default target is approximately **1–2 GB**, but the user may
raise or lower that allocation.

This budget is a **soft durability limit**, not permission to destroy important
history automatically.

If storage pressure requires report cleanup:

1. Preserve active/open reports.
2. Preserve unresolved concern history.
3. Preserve reports tied to important system changes.
4. Preserve successful repairs likely to recur.
5. Preserve failed attempts that prevent repeated mistakes.
6. Prefer removing large raw attachments before report summaries.
7. Archive/compress before deleting where possible.
8. Ask the user before destructive pruning of high-value durable history.

The Report Repository should expose enough size/accounting information for the
Storage Manager to attribute report/database usage without making report logic
responsible for global storage policy.

---

## 33. Priority

Priority communicates urgency and attention.

A possible model:

### Low

Minor optimization, curiosity, non-urgent research.

### Normal

Ordinary maintenance or problem.

### High

Meaningful degradation, recurring failure, important unresolved concern.

### Critical

Potential imminent data loss, hardware damage, severe instability, or security compromise.

Priority SHOULD be based on impact and urgency.

Priority may change during the report lifecycle.

Example:

- SSD monitoring starts Normal.
- SMART critical warning appears.
- Priority becomes Critical.

---

## 34. Report Notifications

Reports themselves should not become notification spam.

Notifications should be generated from:

- Significant status changes.
- Risk escalation.
- Important monitoring events.
- Required user decision.
- Completion.
- Failure.
- Critical watchlist escalation.

Routine report updates may remain silent.

---

## 35. Reports and Task State

Task state and reports are related but distinct.

Task state answers:

> What is Eden doing right now?

Report answers:

> What has this effort learned and accomplished?

Task state may contain:

- Current command.
- Queue.
- Worker status.
- Paused/resume token.
- Temporary execution details.

The report should preserve only the meaningful history.

---

## 36. Reports and Internal Reasoning

Reports SHOULD preserve reasoning conclusions, evidence, alternatives, uncertainty, and decision logic.

Reports SHOULD NOT attempt to preserve unrestricted internal chain-of-thought.

Useful:

> Driver regression was considered likely because crashes began immediately after version X, vendor issue notes mention the same error, and rollback removed the symptom.

Not useful:

> Token-by-token hidden reasoning dump.

The report should preserve the information needed to reproduce or review the decision.

---

## 37. Reports and User Communication

The report is the durable record.

The chat message is the conversational interface.

After a report closes, Eden SHOULD summarize:

- What happened.
- What was found.
- What changed.
- Whether it worked.
- What monitoring continues.
- What the user should know next.

The user does not need to read the full report unless desired.

---

## 38. Report Templates

Templates should standardize reports without forcing irrelevant sections.

### 38.1 Problem Report Template

```markdown
---
id:
title:
created:
last_updated:
state:
status:
priority:
purpose_tags: [Problem]
component_tags:
chain:
related_reports:
related_nodes:
---

# Summary

# Trigger

# Symptoms / Observations

# Evidence

# Research

# Diagnosis

# Confidence

# Alternatives Considered

# Plan

# Approval

# Execution

# Verification

# Outcome

# Monitoring / Follow-Up

# Relationships
```

### 38.2 Monitoring Report Template

```markdown
---
id:
title:
created:
last_updated:
state:
status:
priority:
purpose_tags: [Monitoring]
component_tags:
monitoring_target:
monitoring_start:
monitoring_end_condition:
chain:
related_reports:
related_nodes:
---

# Summary

# Why Monitoring Exists

# Baseline

# Monitoring Method

# Significant Events

# Trends

# Confidence

# Outcome

# Escalation / Follow-Up

# Relationships
```

### 38.3 Research Report Template

```markdown
---
id:
title:
created:
last_updated:
state:
status:
priority:
purpose_tags: [Research]
component_tags:
related_reports:
related_nodes:
---

# Question / Objective

# Context

# Sources / Evidence

# Conflicting Information

# Analysis

# Confidence

# Recommendation

# Alternatives

# Outcome

# Relationships
```

### 38.4 Optimization Report Template

```markdown
---
id:
title:
created:
last_updated:
state:
status:
priority:
purpose_tags: [Optimization]
component_tags:
related_reports:
related_nodes:
---

# Objective

# Baseline

# Constraints

# Evidence

# Proposed Changes

# Approval

# Execution

# Benchmark / Verification

# Result

# Tradeoffs

# Follow-Up
```

### 38.5 Upgrade Report Template

```markdown
---
id:
title:
created:
last_updated:
state:
status:
priority:
purpose_tags: [Upgrade]
component_tags:
related_reports:
related_nodes:
---

# Upgrade Goal

# Current Hardware

# Workload / Bottleneck Evidence

# Budget / Constraints

# Options

# Compatibility

# Expected Improvement

# Recommendation

# Confidence

# Decision / Outcome

# Follow-Up
```

---

## 39. Example — Complete Problem Report

Conceptual example:

```markdown
---
id: RPT-2026-00142
title: Gaming Stutter — Background Overlay Conflict
created: 2026-09-11
last_updated: 2026-09-12
state: Closed
status: Resolved
priority: Normal
purpose_tags: [Problem]
component_tags: [GPU, OS]
chain: CHN-2026-0017
related_nodes:
  - RTX 4070
  - NVIDIA Driver 580.xx
  - Game Overlay Software
---

# Summary

Intermittent frame-time spikes occurred across two games. High GPU temperature
was initially considered, but telemetry did not correlate temperature with the
stutters. Disabling an overlay process removed the spikes.

# Trigger

User reported: "Games have been stuttering lately."

# Evidence

- Frame-time spikes reproduced in two sessions.
- GPU temperature remained below thermal-throttle range.
- GPU utilization did not drop during every stutter.
- Overlay process showed repeated activity at the same timestamps.
- Similar historical report existed six months earlier.

# Research

Vendor and community reports documented overlay conflicts with the affected
rendering mode.

# Diagnosis

Primary diagnosis: background overlay conflict.

# Confidence

Initial:
- Diagnostic: 58%
- Research: 71%
- Execution: 96%
- Safety: 98%

After reproduction:
- Diagnostic: 91%
- Research: 85%
- Execution: 97%
- Safety: 98%

# Alternatives Considered

- GPU thermal throttling.
- Driver regression.
- Storage latency.

# Plan

Disable overlay auto-start, reproduce game workload, compare frame-time trace.

# Approval

User approved plan v2.

# Execution

Overlay auto-start disabled. No other software removed.

# Verification

Three 30-minute test sessions showed no recurrence of the original frame-time
spikes.

# Outcome

Resolved.

# Monitoring

Monitor next 10 gaming sessions for recurrence.

# Relationships

Previous report: RPT-2026-00088
Watchlist item: WL-0021
```

This example shows the intended level of detail: enough to understand the case without storing every raw telemetry sample.

---

## 40. Example — Failed Attempt Chain

### Report 1

`SSD Health Monitoring`

- Open monitoring report.
- Latency spikes observed.
- No immediate critical failure.

### Report 2

`SSD Error Remediation — Firmware Update`

- Separate repair objective.
- Firmware update completed.
- Errors persisted.
- Closed / Failed.

### Report 3

`SSD Error Remediation — Cable and Port Isolation`

- New attempt.
- Port issue identified.
- Resolved.

### Report 4

`SSD Stability Monitoring After Port Change`

- 30-day monitoring.
- No recurrence.
- Closed / Resolved.

All belong to one chain.

The chain tells a story without forcing all work into one enormous report.

---

## 41. Example — Watchlist Without Immediate Repair

Eden detects rising SSD wear.

Correct behavior:

1. Create or update monitoring report.
2. Add watchlist concern if justified.
3. Record baseline evidence.
4. Notify user at appropriate severity.
5. Recommend monitoring or action.
6. Do not automatically replace/repair hardware without approval.
7. Escalate if conditions worsen.
8. Link later repair efforts to the same chain.

---

## 42. Report Editing Rules

Reports are durable but may be corrected.

### 42.1 Append versus revise

Use revision when correcting:

- Typo.
- Incorrect metadata.
- Misclassified tag.
- Factual error discovered later.

Use append/update when adding:

- New evidence.
- New event.
- Monitoring result.
- New confidence.
- New outcome.

### 42.2 Historical integrity

Do not silently rewrite history to make Eden appear more correct.

If diagnosis changes:

Bad:

> Delete original diagnosis and pretend it was always correct.

Good:

> Initial hypothesis was driver regression. New reproduction evidence reduced that likelihood and supported overlay conflict instead.

Reports should show learning.

### 42.3 Audit trail

A lightweight revision history MAY be maintained for important changes.

Full Git-style history for every tiny report edit is not required, but meaningful corrections should be traceable.

---

## 43. Report Versioning

Report content format itself should have a schema version.

Example:

```yaml
schema_version: 1
```

This allows future migrations.

Schema version is not the same as report revision number.

A report may also have:

```yaml
revision: 7
```

if useful.

---

## 44. Report Schema Evolution

The report system WILL evolve.

Schema changes SHOULD:

- Be backward-compatible where practical.
- Include migration logic.
- Preserve unknown fields where possible.
- Avoid breaking old report readability.
- Increment schema version.
- Be documented.

Future Eden should still be able to understand old reports.

---

## 45. Report Validation

Before saving/closing a report, the system SHOULD validate:

- ID exists.
- Title exists.
- State/status valid.
- Dates valid.
- Tags valid.
- Required closure summary exists if closed.
- Monitoring boundary exists for active monitoring.
- Related report IDs resolve if expected.
- Chain ID resolves if expected.
- Confidence fields are internally valid.
- No impossible state/status combination.
- Required success/verification information exists for Resolved reports.

Resolved reports without verification should be flagged.

---

## 46. Resolution Requirements

A report SHOULD NOT receive `Resolved` merely because Eden completed the planned commands.

Resolved requires:

1. Objective-defined success criteria.
2. Verification performed when practical.
3. Evidence supports success.
4. No known critical unresolved contradiction.

If verification cannot be performed:

- Use another appropriate outcome.
- Or mark resolution with explicit uncertainty if schema later supports it.

Do not falsely communicate certainty.

---

## 47. Failure Requirements

Use `Failed` when:

- The approach did not achieve its objective.
- Eden reached a stopping condition.
- Further progress requires a new approach.
- The task cannot safely continue.

Do not use `Failed` merely because one command returned an error if Eden recovered and completed the effort successfully.

---

## 48. Cancellation Requirements

Use `Canceled` when:

- User stops the effort.
- User withdraws approval.
- Task is intentionally abandoned.
- The objective becomes irrelevant.

Record the reason.

If cancellation leaves partial system changes, those MUST be documented.

---

## 49. Archiving

Archiving reduces active clutter without deleting history.

Good archive candidates:

- Very old closed informational reports.
- Reports for removed hardware.
- Superseded research.
- Historical benchmarks.
- Reports no longer relevant to current device state.

Archived reports SHOULD remain searchable.

---

## 50. Report Relationships

Useful relationship types may include:

- `previous_attempt`
- `follow_up`
- `monitoring_of`
- `caused_by`
- `related_to`
- `supersedes`
- `verification_of`
- `research_for`
- `uses_evidence_from`
- `same_chain`

Relationships SHOULD be explicit enough to support graph traversal.

---


### 50.1 Relationship Semantics

Relationship types SHOULD be treated as structured, typed edges rather than
free-form prose.

Some relationships are naturally directional:

- `follow_up`
- `previous_attempt`
- `supersedes`
- `monitoring_of`
- `verification_of`
- `research_for`

Others may be symmetric:

- `related_to`

The exact database representation, inverse-edge behavior, and cardinality
rules belong in `architecture.md`, but the report model should preserve enough
semantic information that graph traversal does not depend on guessing what a
generic link means.

## 51. Chain Versus Relationship Decision

Use a chain when:

- Same underlying concern.
- Multiple separate efforts.
- Chronological history matters.

Use a simple relationship when:

- Reports are relevant but not one ongoing concern.

Example:

GPU upgrade research may reference gaming benchmark reports but does not necessarily belong to their incident chain.

---

## 52. Report Search Examples

### Query

> Have we seen GPU driver instability before?

Retrieval:

1. Filter component tag: Drivers/GPU.
2. Search titles for instability/crash.
3. Search related GPU node.
4. Inspect relevant chains.
5. Rank recent and resolved/failed cases.
6. Open top reports.

### Query

> What happened the last time this SSD had errors?

Retrieval:

1. Resolve SSD hardware node.
2. Retrieve related Problem/Monitoring reports.
3. Prefer latest same-chain events.
4. Summarize last outcome and verification.

---

## 53. User-Facing Report Browser

A future report UI SHOULD support:

- Search.
- Sort.
- Filter by state.
- Filter by status.
- Filter by purpose.
- Filter by component.
- Filter by date.
- Filter by priority.
- Chain view.
- Related-node view.
- Watchlist integration.
- Open/closed toggle.
- Confidence overview.
- Monitoring indicator.

A report list item might show:

```text
[High] [Problem] [GPU] Gaming Stutter — Overlay Conflict
Resolved • Closed • Sep 12, 2026 • Overall confidence: High
Chain: Intermittent Gaming Stutter
```

The UI does not need to display every metadata field.

---

## 54. Graph View

A future graph view MAY visualize:

- Reports.
- Components.
- Watchlist items.
- Software.
- Drivers.
- Skills.
- Benchmarks.
- System changes.

The graph is a navigation tool, not a replacement for structured search.

Avoid turning the graph into decorative complexity.

---

## 55. Agent Retrieval Rules

When a new agent handles a system issue, it SHOULD not immediately read the entire report archive.

Recommended process:

1. Read current system summary.
2. Identify affected component(s).
3. Search open reports.
4. Search watchlist.
5. Search same-component recent reports.
6. Search same-chain/similar historical reports.
7. Open only likely relevant full reports.
8. Use semantic search only when structured retrieval is insufficient.

This should make long-term history scalable.

---

## 56. Reporting and Model Context Limits

Reports help solve model context limitations.

Instead of passing months of raw logs into an AI model, Eden can provide:

- Current system state.
- Relevant report summaries.
- Chain summary.
- Watchlist concern.
- Targeted raw evidence.

This reduces context size while preserving useful knowledge.

---

## 57. Report Summarization

Long reports MAY be summarized for retrieval.

A summary MUST NOT replace the original durable report unless storage policy explicitly permits compression.

Possible layers:

- 1-line index summary.
- Short retrieval summary.
- Full report.
- Raw evidence attachments.

This supports efficient agent routing.

---

## 58. Report Quality Standard

A good report should allow a competent new agent to answer:

1. What was the objective?
2. What evidence mattered?
3. What did Eden think?
4. How confident was it?
5. What alternatives were considered?
6. What did the user approve?
7. What did Eden do?
8. Did it work?
9. How was success verified?
10. What remains unresolved?
11. What should be monitored?
12. What related history matters?

If the report cannot answer those when relevant, it is probably incomplete.

---

## 59. Anti-Patterns

The report system MUST avoid:

### 59.1 One report per command

Creates massive fragmentation.

### 59.2 Raw chat logs as reports

Too noisy and hard to retrieve.

### 59.3 Overwriting failed history

Destroys useful evidence.

### 59.4 Resolved without verification

Creates false confidence.

### 59.5 Infinite open reports

Open reports must remain operationally meaningful.

### 59.6 Giant combined watchlist report

Unrelated concerns need separate efforts.

### 59.7 Chains created only for aesthetics

Chains must represent real historical continuity.

### 59.8 Unbounded raw telemetry inside the report record

Store high-volume raw data separately and reference it through evidence/dataset IDs.

### 59.9 Weak generic titles

Titles must aid search.

### 59.10 Reports with no objective

Every report needs a coherent reason to exist.

### 59.11 Treating tags as the knowledge graph

Tags categorize.

Relationships connect specific entities.

Those are different jobs.

### 59.12 Treating structured storage as an opaque proprietary prison

Canonical reports may be optimized for AI rather than human prose, but users
must retain practical access through documented structured export and generated
human-readable views.

---

## 60. Implementation Guidance for MVP

The MVP does not need the final knowledge-graph UI or polished report viewer.

A practical first version can use:

1. Structured report domain models.
2. SQLite as canonical persistence.
3. Basic report metadata/tags.
4. Chain IDs and typed relationships.
5. Evidence references.
6. Compact AI retrieval capsules.
7. Search/filter CLI.
8. Generated short human summaries.
9. JSON export.
10. Optional Markdown export.
11. Report retrieval before similar tasks.

This is enough to prove the report system before building sophisticated
visualization.

---

## 61. Suggested MVP Report Data Model

Conceptual SQLite structures:

```text
reports
report_observations
report_hypotheses
report_evidence
report_research_findings
report_confidence_history
report_plans
report_approvals
report_executions
report_verifications
report_monitoring
report_tags
report_relationships
report_chains
chain_members
attachments
```

This is guidance, not a required normalized schema. Some low-cardinality fields
may live directly on `reports`; some collections may use JSON columns when that
is simpler and remains queryable enough.

The important requirement is that `ReportRepository` exposes one validated,
structured report object while the database remains the canonical source of
truth.

---

## 62. Monitoring Data Should Not Live Entirely in Reports

High-frequency telemetry belongs in an appropriate telemetry store.

A monitoring report should reference:

- Baseline.
- Important samples.
- Trends.
- Threshold crossings.
- Summary statistics.
- Final conclusion.

This keeps reports readable.

---

## 63. Confidence and Report Closure Example

Suppose:

- Diagnosis: 91%
- Research: 88%
- Execution: 96%
- Safety: 97%

Repair succeeds and verification passes.

Report:

- State: Closed
- Status: Resolved

Suppose instead:

- Diagnosis: 92%
- Research: 90%
- Execution: 42%
- Safety: 95%

Eden identifies the cause but cannot reliably execute the repair.

Possible outcome:

- State: Closed
- Status: Failed

with conclusion:

> Root cause is well-supported, but execution could not be completed safely/reliably with current tooling.

That report remains valuable.

---

## 64. Report Creation Examples

### Create report

> “My PC keeps freezing while gaming.”

Yes.

### Create report

> “Track GPU temperature for the next week.”

Yes.

### Create report

> “Research whether upgrading to a 5070 Ti would help my workloads.”

Yes.

### Probably no report

> “What version of Windows am I running?”

No, unless this is part of a larger effort.

### Probably no report

> “Open Calculator.”

No.

### Create report if consequential

> “Clean up 200 GB of storage.”

Yes.

---

## 65. Relationship With Skills

A report MAY record which reusable skill performed work.

Example:

```yaml
skill:
  name: gpu-driver-health-check
  version: 3
```

This helps future debugging if a skill later changes.

A skill result does not replace a report when the effort itself deserves durable history.

---

## 66. Relationship With System Changes

Important system changes SHOULD be linkable from reports.

Examples:

- Driver updated.
- Registry changed.
- Startup item disabled.
- Software removed.
- BIOS changed.
- Power plan modified.

A future change-log subsystem may provide structured change objects.

Reports should reference those changes rather than duplicating all detail.

---

## 67. Relationship With Rollback

If a plan has a rollback path, the report SHOULD preserve:

- Pre-change state.
- Backup/restore point ID.
- Rollback method.
- Whether rollback was tested.
- Whether rollback was required.

This is particularly important for high-risk reports.

---

## 68. Security and Sensitive Content

Reports may contain sensitive system information.

They MUST follow Sys Eden's local-first privacy model.

Reports SHOULD avoid unnecessarily storing:

- Passwords.
- Tokens.
- API keys.
- Full private document contents.
- Secret recovery codes.

If evidence contains secrets, Eden should redact or reference securely stored evidence.

Reports are part of the private local knowledge base.

---

## 69. Report Export

The user SHOULD eventually be able to export reports.

Useful export forms:

- JSON structured report.
- Markdown human-readable view.
- PDF human-readable view.
- Bundle including attachments/evidence where appropriate.

Export should preserve relationships and metadata where practical.

---

## 70. Report Import

Future versions MAY support importing external technical records.

Imported content should be marked as imported and should not automatically be treated as verified Eden-generated evidence.

---

## 71. Multi-Agent Report Writing

Multiple subagents may contribute findings to one report.

The orchestrator remains responsible for:

- Reconciling contradictions.
- Selecting relevant evidence.
- Maintaining coherent structure.
- Avoiding duplicate content.
- Recording unresolved disagreement.

Do not create one report per subagent merely because several agents were used.

---

## 72. Contradictory Findings

If agents or sources disagree, the report SHOULD preserve meaningful disagreement.

Example:

```text
Research finding A:
Vendor documentation suggests issue X.

Research finding B:
Recent community reports indicate the same version may also trigger Y.

Current conclusion:
X remains more likely due to local evidence, but Y remains an active alternative.
```

This is better than erasing uncertainty.

---

## 73. Report Integrity Principle

Reports should describe what actually happened, not what the plan expected to happen.

Plan:

> Update driver, reboot, verify crash resolved.

Actual:

> Driver installer failed before reboot.

The report execution section records actual behavior.

---

## 74. Report Completeness Versus Brevity

Reports must be concise enough to retrieve efficiently and complete enough to preserve meaning.

Include:

- Important evidence.
- Key reasoning.
- Decisions.
- Actions.
- Results.
- Uncertainty.

Exclude:

- Repeated conversational filler.
- Every thought.
- Every raw line.
- Duplicated logs.
- Irrelevant background.

The goal is **high information density**.

---

## 75. Default Report Closing Summary

A useful closing summary can follow:

```text
Objective:
Root cause / conclusion:
Actions taken:
Verification:
Final status:
Confidence:
Remaining concerns:
Monitoring:
Next recommended action:
```

This should be short enough for a user to skim.

---

## 76. Report Chain Example With Recurrence

Chain:

### RPT-001
`GPU Crash Investigation`
- Closed / Resolved
- Cause: overlay conflict

Six months later:

### RPT-044
`GPU Crash Recurrence Investigation`
- Closed / Failed
- Overlay removed; crash persisted
- Driver issue suspected

Later:

### RPT-052
`GPU Driver Repair`
- Closed / Resolved
- Clean install fixed crash

Later:

### RPT-053
`GPU Stability Monitoring`
- Closed / Resolved
- 30 sessions with no recurrence

Future Eden can see that the same symptom had more than one root cause across time.

This prevents simplistic assumptions.

---

## 77. Chain Naming

Chain title SHOULD describe the underlying concern, not one solution.

Good:

`Recurring Gaming Stutter`

Poor:

`Driver Rollback`

because a later attempt may involve something else.

---

## 78. Report De-Duplication

Before creating a report, Eden SHOULD check for an existing open report with the same objective.

If one exists, update it rather than create a duplicate.

If a closed report exists, decide whether:

- New report + chain link.
- Reopen.
- Merely reference historical context.

---

## 79. Orphan Reports

Reports without relationships are allowed.

Do not force links.

However, if a report obviously relates to:

- Existing chain.
- Hardware node.
- Watchlist item.
- Previous attempt.

Eden SHOULD link it.

---

## 80. Stale Open Reports

The system SHOULD periodically detect open reports that have had no activity.

Eden may classify them as:

- Waiting for user.
- Waiting for condition.
- Active monitoring.
- Stale.
- Candidate for closure.

Do not silently close unresolved reports without reason.

---

## 81. Waiting States

Although State remains Open/Closed, reports MAY include an operational field such as:

```yaml
activity:
  - active
  - waiting_user
  - waiting_condition
  - monitoring
  - paused
```

This avoids overloading Status.

Exact field name is implementation detail.

---

## 82. Report Ownership

The main orchestrator owns report coherence.

Specialized agents may submit structured contributions such as:

- Evidence.
- Research.
- Diagnosis.
- Verification.
- Monitoring summary.

The orchestrator decides what becomes durable report content.

---

## 83. Verification Independence

For significant repairs, verification SHOULD be performed independently enough to reduce confirmation bias.

The report SHOULD indicate:

- What was verified.
- How.
- By what component/agent if relevant.
- What success criteria were used.

---

## 84. Reports as Training/Improvement Data

Locally, reports may eventually help Eden improve routing, confidence calibration, or recommendations.

Examples:

- Which fixes commonly succeed.
- Which diagnoses recur.
- Which hardware components generate repeated issues.
- Which confidence levels correlate with success.

This learning MUST remain consistent with privacy requirements.

---

## 85. User Corrections

The user may correct a report.

Example:

> “That crash happened before the driver update, not after.”

Eden SHOULD:

1. Update the report.
2. Mark the correction.
3. Reassess affected conclusions if necessary.
4. Adjust confidence.
5. Preserve enough history to avoid hiding the original mistake.

---

## 86. Unverified User Claims

User observations are valid evidence but should be labeled as such.

Example:

```text
User observation:
Fan became louder immediately before crash.
```

Do not silently transform this into a measured sensor fact.

---

## 87. Dates and Time

Reports SHOULD store machine-readable timestamps.

Human-facing views may use local time.

Important events SHOULD include timestamps when sequencing matters.

Example:

- Driver installed 18:42.
- First crash 19:03.

---

## 88. Report Priority and Notification Are Different

Priority is report importance.

Notification severity is whether the user should be interrupted now.

A High-priority report may not require immediate interruption if the user already knows about it.

A Critical monitoring event may trigger a notification even if the report was previously Normal.

---

## 89. Multiple Components

Reports may have multiple component tags.

Example:

Gaming stutter could involve:

- GPU
- Drivers
- Storage
- OS

Do not force a single-component classification.

---

## 90. Tag Discipline

Avoid uncontrolled tag explosion.

The system SHOULD maintain a known taxonomy.

Specific entity identity belongs in nodes, not endless tags.

Prefer:

- Component tag: `GPU`
- Related node: `RTX 4070`

instead of tag:

- `RTX4070`

for every report.

---

## 91. Report Status Changes

Important transitions SHOULD be recorded.

Example:

```text
2026-09-11 21:10 — Active
2026-09-11 22:15 — Resolved
2026-09-18 09:00 — Closed after monitoring
```

Exact audit representation may vary.

---

## 92. Report Chain Summary Update

When a new report joins a chain, the chain summary SHOULD update.

This allows quick understanding without opening every member.

---

## 93. Search Result Summaries

Each report SHOULD expose a short index summary.

Example:

> Stutter traced to overlay conflict; disabling overlay resolved issue across 10 verified sessions.

This is different from the full report Summary section if desired.

---

## 94. Report Size

There is no fixed word limit.

A report should be as long as necessary and no longer.

If a report becomes extremely large:

- Move raw evidence out.
- Summarize repetitive monitoring.
- Split only if the work has genuinely become multiple objectives.

Do not split merely because a generated human view is long.

---

## 95. Report Lifecycle Anti-Example

Bad:

1. Create report for log collection.
2. Close.
3. Create report for diagnosis.
4. Close.
5. Create report for plan.
6. Close.
7. Create report for command.
8. Close.
9. Create report for verification.

This destroys coherent history.

Correct:

One problem report containing that entire effort.

---

## 96. Chain Anti-Example

Bad chain:

- Find issue.
- Research issue.
- Fix issue.
- Verify issue.

Those are not necessarily separate reports.

Good chain:

- Monitoring effort.
- Failed repair effort.
- Later alternative repair effort.
- Post-fix monitoring effort.

---

## 97. Future Expansion

Potential future features:

- Interactive knowledge graph.
- Automatic chain summaries.
- Report similarity detection.
- Semantic retrieval.
- Report diff view.
- Timeline visualization.
- Confidence calibration dashboards.
- Report analytics.
- Failure-pattern mining.
- Automatic stale-report review.
- Export bundles.
- Cross-device report history if Sys Eden later supports multiple machines.
- Report templates generated from skills.
- User annotation layer.
- Evidence provenance graph.

These are future opportunities, not MVP blockers.

---

## 98. Implementation Priorities

Recommended order:

### Phase 1 — Core report object

Implement:

- ID.
- Title.
- State.
- Status.
- Tags.
- Dates.
- Markdown body.
- Save/load.

### Phase 2 — Lifecycle

Implement:

- Create.
- Update.
- Close.
- Validation.
- Outcome summary.

### Phase 3 — Relationships

Implement:

- Related reports.
- Chains.
- Watchlist links.
- Related hardware/software nodes.

### Phase 4 — Retrieval

Implement:

- Metadata index.
- Search.
- Filters.
- Read relevant history before task.

### Phase 5 — Monitoring integration

Implement:

- Monitoring fields.
- Significant-event summaries.
- Post-fix monitoring.

### Phase 6 — Knowledge graph

Implement:

- Entity nodes.
- Explicit typed relationships.
- Graph traversal.
- Optional visual graph.

---

## 99. MVP Acceptance Test for Reports

The report system is useful enough for the MVP when the following scenario works:

1. User reports a recurring PC problem.
2. Eden creates one coherent report.
3. Eden records evidence and diagnosis.
4. Eden records confidence.
5. Eden records the approved plan.
6. Eden executes the plan.
7. Eden records verification.
8. Eden closes as Resolved or Failed.
9. Months later the same symptom returns.
10. Eden finds the old report through metadata/search.
11. Eden uses the old successful and failed history to improve the new investigation.
12. A new report is created and linked to the same chain.
13. The user can inspect both reports through a generated human-readable view and export their structured data.

If this works, the system has achieved the core purpose of reporting.

---

## 100. Canonical Reporting Principles

The entire reports system can be reduced to these rules:

1. **One report = one coherent effort.**
2. **Reports preserve decisions and outcomes, not raw conversation.**
3. **State and status are different.**
4. **Resolved requires verification.**
5. **Failed efforts are valuable history.**
6. **Monitoring must have a measurable boundary.**
7. **Separate efforts may form report chains.**
8. **Do not create reports merely to create chains.**
9. **Use metadata to find reports before reading full contents.**
10. **Use explicit relationships for knowledge graph navigation.**
11. **Keep raw telemetry separate from durable interpretation.**
12. **Reports should remain readable and portable.**
13. **Never rewrite history to hide uncertainty or failure.**
14. **Reports should reduce repeated work in future cases.**
15. **The report system exists to help Eden understand the computer over time.**

---


## 100.1 Validation Result

This specification was tested by giving a fresh AI agent only this document
and a 185-question comprehension test covering:

- report boundaries,
- lifecycle,
- state/status,
- confidence,
- monitoring,
- watchlists,
- chains,
- knowledge-graph relationships,
- retrieval,
- storage,
- privacy,
- multi-agent behavior,
- integrated troubleshooting scenarios,
- and deliberately unspecified implementation details.

The agent demonstrated essentially complete comprehension of the intended
report model and correctly declined to invent implementation details that this
specification leaves open.

The validation pass exposed three details worth making explicit before
architecture implementation:

1. Terminal partial-success behavior.
2. Multi-value purpose/component tags.
3. Zero-or-one primary-chain membership and clearer typed relationship
   semantics.

These clarifications are included in this version.

## 101. Closing Principle

A Sys Eden report should make future Eden meaningfully smarter about the device.

When a report is complete, another competent agent should be able to open it months later and understand:

- Why the effort existed.
- What mattered.
- What Eden believed.
- What the user approved.
- What changed.
- What worked.
- What failed.
- What remained uncertain.
- What happened afterward.
- What history should influence the next decision.

If the report cannot do that, it has not fulfilled its purpose.
