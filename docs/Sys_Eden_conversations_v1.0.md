# Sys Eden — Conversations and Chat Persistence

> **Document role:** Canonical specification for chat sessions, transcript
> persistence, report links, conversation resumption, and explicit promotion of
> chat content into structured memory
> **Status:** Conversations v1.0
> **Depends on:** `architecture.md`, `system_rules.md`, and `reports.md`

---

# 1. Purpose

This document separates three concepts that must not be conflated:

1. **Conversation persistence** — whether a raw user/Eden chat transcript can be
   reopened and continued.
2. **Report knowledge** — the compact, structured record of a meaningful effort.
3. **Structured memory** — an intentionally retained preference, fact,
   permission, recurring pattern, or concern that may be useful across work.

A saved transcript is not automatically a report or a memory. A report may link
to one or more transcripts without embedding them. A memory may be created from
a temporary chat without making the entire transcript persistent.

---

# 2. Conversation Modes

Every chat has a visible persistence mode.

## 2.1 Temporary

- The transcript exists only for the owning CLI client session.
- It remains available while that client visits home or another thread and may
  continue receiving live work updates.
- It is not resumable after the owning client closes, Core restarts, or its
  temporary lifetime ends.
- It is not available to later chats or general retrieval.
- Eden does not silently extract structured memory from it.
- Redacted operational logs may still record failures or performance events,
  but they are not a recoverable chat transcript.

Temporary is the privacy-first default for a new unclassified conversation.

Meaningful or working temporary conversations cause an exit warning with the
choices to save, stop/discard, or cancel. Operating-system terminal close events
cannot provide a dependable interactive prompt. Core therefore owns a client
lease: after an unexpected disconnect and short grace period, it safely stops
that client's temporary work and discards only that client's temporary chats.
The home screen should also warn while temporary work is active.

## 2.2 Saved

- The transcript is persisted locally.
- It can be listed, reopened, searched by the user, exported, and deleted.
- Interactive `/delete` confirms before removing the transcript and holds an
  undo copy only for the owning CLI session. `/restore` can reopen it before
  that session closes; disconnect or lease expiry discards the undo copy.
  One-shot `eden chat delete` is permanent because it has no continuing session.
- It may have a rolling summary for efficient resumption.
- Saving it does not automatically make its contents available as general
  cross-chat memory.
- It does not require a report.

This mode supports ordinary conversations that should be resumable but do not
represent a formal system effort.

## 2.3 Report-linked

- The conversation is associated with one primary report and may reference
  additional related reports.
- The transcript remains a separate conversation artifact rather than becoming
  report body content.
- The normal default when linking a conversation to a report is to save the
  transcript and create the relationship.
- If the current conversation is temporary, Eden must disclose that linking it
  normally makes the transcript persistent. The user may instead choose to add
  only a distilled contribution to the report and leave the transcript
  temporary.
- Multiple conversations may be linked to the same report.

Report association and transcript persistence are represented separately even
when the UI presents report-linked persistence as one convenient mode.

---

# 3. Visible State

The current state must remain visible near the conversation title or input area.

Examples:

```text
[TEMPORARY — not saved]
[SAVED — CHT-0042 — PC build ideas]
[REPORT RPT-0184 — Gaming stutter investigation]
```

State changes must be announced. Eden must not quietly turn a temporary chat
into a saved or report-linked chat.

The indicator should expose, directly or through details:

- conversation ID when durable,
- persistence state,
- primary report when linked,
- whether a report contribution was last updated,
- and whether any memory was explicitly created during the chat.

---

# 4. Conversation and Report Relationship

A report remains the durable structured account of an effort. A transcript is
supporting source material and conversational history.

The report should not contain the raw transcript. It may contain a concise
conversation-contribution summary when the chat materially affects the report,
such as:

- important initial information or constraints from the user,
- a symptom clarification,
- a consequential decision,
- an accepted or rejected alternative,
- an approval or correction,
- a conclusion that changes the report,
- or useful follow-up information.

The report links to the conversation artifact so the user can inspect the full
history when it still exists. Routine greetings, repeated explanations, and
conversational filler do not belong in the report summary.

## 4.1 Link selection

The user may explicitly link or relink a conversation to a report. Eden may
suggest a more relevant report when evidence supports the suggestion, but it
must not silently move the conversation.

Example:

> This appears more closely related to RPT-0212, “GPU power instability,” than
> the currently selected report. Link this conversation to RPT-0212 instead?

One report is the primary conversational context. Other reports may be attached
as related context without blending their objectives.

## 4.2 Transcript deletion

Deleting a transcript does not silently rewrite independently valid report
knowledge. The report retains its structured conclusions and records that a
linked source transcript was deleted by the user. Removing derived report
content is a separate explicit operation.

---

# 5. Report Information Tiers

Reports expose information in three logical tiers. These tiers organize
retrieval and presentation; they do not require three separate report files.

## 5.1 Core information

The compact, high-value account of the effort:

- objective and trigger,
- crucial initial conditions and user constraints,
- current or final conclusion,
- strongest evidence,
- important decisions and actions,
- verification and outcome,
- unresolved risks and next steps.

The AI retrieval capsule and concise human summary primarily draw from this
tier.

## 5.2 Supporting information

Useful detail that should not crowd the core account:

- secondary observations,
- detailed chronology,
- meaningful but rejected alternatives,
- lower-priority evidence,
- expanded explanations,
- and conversation-contribution summaries.

## 5.3 Linked artifacts

Detailed source material retrieved only when needed:

- saved chat transcripts,
- raw logs,
- evidence attachments,
- exports,
- command output,
- and research captures.

This preserves important detail without filling normal model context with raw
history.

---

# 6. Structured Memory Capture During Chat

Structured memory is independent of transcript persistence.

If Eden believes the user may intend a statement to become durable memory, Eden
asks before storing it. The prompt should show the proposed memory content and
scope rather than ask a vague question.

Example:

> You may want me to remember: “Prefer stability over maximum gaming
> performance.” Save this as a user preference?

Declining leaves no memory entry. Eden should not repeatedly ask about the same
statement in the same conversation.

The slash form is explicit authorization:

```text
/memory Prefer stability over maximum gaming performance
```

It creates the memory without a second intent-confirmation prompt and then
shows what was stored. The equivalent direct terminal command must also exist.
Normal validation still applies: Eden must not store credentials or clearly
unsafe secret material in ordinary memory, and it may ask for clarification if
the requested memory content or scope is ambiguous.

This behavior applies in temporary, saved, and report-linked chats. Creating a
memory from a temporary chat does not save the transcript. The memory entry
keeps its own provenance, including that it came from an explicit user request
in a temporary conversation.

Deleting a conversation does not silently delete separately confirmed memory.
Forgetting the memory is a distinct user-controlled action.

---

# 7. Resumption and Model Context

Any retained conversation can be resumed for as long as it remains stored.
Resumption does not require placing the full transcript in the model context.

The context builder should normally use:

1. the conversation identity and mode,
2. a bounded recent-message window,
3. a rolling conversation summary,
4. current durable task state when applicable,
5. the primary report retrieval capsule when linked,
6. specifically relevant older messages or artifacts only when needed.

The user can browse or export the full transcript even when the model receives
only a bounded context.

In the Milestone 5 CLI, Eden updates the rolling summary when the prepared
context reaches 80% of the configured character budget. This is model-context
summarization, not transcript deletion. Interactive `/compact` requests that
summary explicitly and retains the full transcript. `eden chat compact <id>`
is a separate, confirmed retention action that may remove older raw messages.

Temporary conversations cannot be resumed after their temporary lifetime ends.

---

# 8. Cross-Conversation Context

Saving a transcript does not grant Eden blanket permission to inject it into
unrelated chats.

Default cross-conversation retrieval may use:

- structured report capsules,
- explicitly stored memory,
- durable task state,
- and user-selected conversations.

Raw messages from a different saved conversation require an explicit user
request or a visible relevance prompt. When Eden uses another conversation, it
identifies the source conversation. Temporary chats are never candidates.

This keeps “resume this chat” distinct from “search everything I have ever
said.”

---

# 9. Storage Model

For the MVP, canonical conversation metadata and messages should use normalized
SQLite records through a repository abstraction. A report links to a
conversation entity; it does not embed message rows or copy a transcript into
report fields.

Conceptual records:

```text
conversations
-------------
id
title
persistence_mode
state
created_at
updated_at
last_resumed_at
rolling_summary
retention_policy

conversation_messages
---------------------
id
conversation_id
sequence
role
content
created_at
metadata

report_conversation_links
-------------------------
report_id
conversation_id
relationship_role
contribution_summary
linked_at
linked_by
```

An export may render the transcript as JSON, text, or Markdown so it behaves
like a linked file to the user. The export is a view; it is not a second
writable source of truth.

Conversation storage is charged to the existing reports/memory/database budget
for the MVP. Persistent transcripts must not be silently deleted merely to meet
a soft budget. Eden should show usage, support user-controlled retention, and
ask before consequential pruning.

Storage accounting must attribute the shared budget internally rather than
showing only one opaque database size. At minimum it should distinguish:

- structured reports and report relationships,
- full conversation transcripts,
- compact conversation records,
- structured memory,
- report/conversation attachments,
- search indexes and generated summaries,
- SQLite/WAL and other database overhead,
- and an estimated reclaimable amount.

---

# 10. Retention and Deletion

Persistent conversations have three storage states:

- **Full** — the complete retained transcript is available.
- **Compact** — the rolling summary, selected key messages, report links, and
  required provenance remain while removable raw conversational detail has been
  discarded.
- **Deleted** — the durable transcript is gone; an interactive client may keep a
  session-only undo copy until that CLI session ends. Independently valid report knowledge or
  structured memory remains unless separately removed.

The state must be visible. Converting a conversation promised as persistent from
Full to Compact is a retention action, not ordinary context summarization. Eden
must not do it silently. Automatic compaction requires a user-enabled policy;
otherwise Eden recommends candidates and asks.

- Temporary chat: discarded when its temporary lifetime ends.
- Saved chat: retained until user deletion or an explicitly configured
  retention policy applies.
- Report-linked chat: retained under its conversation retention policy; the
  report relationship does not make deletion impossible.
- Report knowledge, transcript history, and structured memory each have
  separate deletion controls.
- Deletion should be local, auditable, and clear about derived summaries or
  links that remain.

The exact default duration for saved raw transcripts remains configurable. “Can
resume” means the conversation is logically resumable while retained, not that
the entire transcript always fits in one model prompt.

Creating a rolling summary while retaining the raw transcript reduces model
context use but does not materially reclaim disk. Storage is reclaimed only
when raw content is compressed or removed.

## 10.1 Closed-report retention checkpoint

Closing a report does not automatically compact or delete its conversations. It
creates a retention checkpoint that should:

1. confirm the report contains crucial initial information, conclusions,
   actions, verification, outcome, and unresolved concerns,
2. update material conversation-contribution summaries,
3. identify transcript content that remains unique evidence,
4. remove or archive duplicate raw tool output before conversational history,
5. mark eligible linked transcripts as compaction candidates,
6. preserve transcripts that are pinned, linked to active work, connected to
   another open report, or contain important unextracted information.

## 10.2 Storage-pressure cleanup order

When the shared budget is under pressure, Eden should normally:

1. discard expired temporary-chat data,
2. remove regenerable exports and caches,
3. remove duplicate tool output already retained as evidence elsewhere,
4. prune large low-value attachments according to their retention policies,
5. recommend compaction of old unlinked saved conversations,
6. recommend compaction of transcripts linked only to closed reports after the
   retention checkpoint passes,
7. archive/compress closed reports,
8. request explicit approval before deleting durable reports or other
   high-value history.

Pinned conversations and conversations linked to active/open reports are
protected from ordinary automatic cleanup.

---

# 11. Command Surface

Candidate interactive commands for Milestone 5:

```text
/new
/home
/save
/compact
/chats
/resume CHT-0042
/report RPT-0184
/report unlink
/memory <content>
```

While Core is running, the interactive home itself ends in the chat composer;
there is no separate New Chat button or chat mode to enter. Typing sends a
message into a newly created temporary conversation and opens its dedicated
thread screen. Further messages continue that conversation. `/home` or `Esc`
returns home without stopping in-progress work, and `/new` returns the composer
to a new empty temporary context. Conversations and Monitoring remain
secondary inline actions while Core is running; More is limited to the
stopped-Core menu. In the composer, `Esc` leaves the current thread context
only when the draft is empty; it does not erase a draft.

The interactive client owns an alternate terminal screen while it is open and
redraws that application surface in place. A thread displays its conversation
ID once in the header and its user/Eden transcript below; individual responses
do not repeat the ID. Home's Activity section is a history of conversations
opened or worked on in this terminal, including reopened saved chats. It shows
compact working or completed entries, not interleaved transcript output;
deleting a chat marks its entry Deleted while hiding it from Conversations;
restoring it changes the entry back to Complete. The top
home status section has a smooth enclosing box; a conversation's title/status
header has rounded corners and dark gray characters on black. Its character
color is lightened to balance its appearance against the composer fill.
Navigation buttons use the same gray characters on black. The scrollable
transcript fills the rows immediately between its header and composer, with two
wrapped lines per wheel event. Short transcripts start at the top below the
header, with unused rows below the messages; overflow follows the latest text
unless the owner scrolls up. Save/pin confirmations and other client-only
notices stay at their chronological position among the turns and scroll away
normally; they are not stored or sent to the model as conversation messages.
The composer is borderless with a
dark neutral background. Its message placeholder disappears as soon as the user
types, while `/help for commands` sits below the button row. Typing `/` opens an
in-place list of at most five commands whose names match the current prefix.
After an ID-bearing command such as `/resume`, `/delete`, `/restore`, or
`/monitoring`, the same list suggests matching chats or monitoring tasks,
newest first; arrow keys and Enter select one.
Further typing narrows the list, and arrow keys move or scroll the selection.
The button row sits below the composer when the palette is closed; Down at the
composer's bottom edge selects buttons and Up returns to the composer. Within wrapped draft
text, left/right move the insertion point by character and up/down move between
text rows. Left/right select buttons only on the button row. Exiting the
client restores the original shell screen; direct commands continue to use
ordinary terminal output.

Read-only diagnostic work started in a conversation creates a linked durable
task with progress and a terminal outcome; an ordinary chat answer does not.
Stop requests apply to the live request, including the classification period
before a diagnostic task exists. A task linked to a temporary chat retains only
generic audit wording, not the temporary prompt or response after that chat is
discarded.

Closing a report records a summary and outcome, then produces a retention
review for its linked conversations. This does not compact or delete any
transcript. A candidate remains protected until unique transcript evidence has
been explicitly reviewed, and also when the report or its conversation link
lacks a material summary. Users can inspect or confirm the saved review through
report-retention commands; that confirmation itself changes no transcripts.

The Conversations subview combines durable conversations with temporary chats
owned by the current CLI session. A normal prompt and `/inspect [area]` both
stay in the same conversation model: Core automatically routes requests that
need machine evidence through read-only diagnosis, while `/inspect` supplies an
explicit starting scope. If meaningful temporary chats require an exit choice,
Discard & Exit is selected initially and Save & Exit remains available.

Candidate direct equivalents:

```text
eden chat "..."
eden chat "..." --save
eden chat "..." --report RPT-0184
eden chat "..." --conversation CHT-0042
eden chat list
eden chat show CHT-0042
eden chat delete CHT-0042
eden chat export CHT-0042
eden chat compact CHT-0042
eden chat pin CHT-0042
eden chat unpin CHT-0042
eden memory add "..."
eden storage status
eden storage status --details
eden storage reports --details
eden storage conversations --details
eden storage attachments --details
eden storage recommendations
```

`eden storage status` shows category totals, configured budgets, remaining
capacity, protected free-space reserve, and pressure state. `--details` shows
the subcategory attribution, counts, largest consumers, Full versus Compact
conversation totals, active versus closed report links, protected/pinned data,
and estimated reclaimable space. Category-specific commands apply the same
detail contract to reports, conversations, and attachments.

Storage inspection commands are read-only. Recommendations do not perform
cleanup. Commands that compact or delete data must preview impact and follow the
applicable confirmation policy.

Exact flag spelling should be finalized with the Milestone 5 CLI design, but
the semantic parity is required.

Milestone 5 finalizes `/corestart`, `/corestop`, `/stop`, `/help`, and `/exit` as
distinct controls. `/stop` applies only to current-conversation work and uses a
second invocation for a hard stop. `/corestop` gracefully stops Core without
closing the client. `/exit` closes only the client. `/help` is generated from a
central command registry and states which commands accept each modifier.

Turning persistence off after messages were already stored requires a clear
choice between stopping future persistence and deleting the previously saved
transcript. Eden must not infer deletion from a mode toggle.

---

# 12. Milestone Ownership

## Milestone 5 — foundation

- Conversation identity and repository.
- Temporary and saved modes.
- Report-conversation links.
- Persistent chat list/resume/delete/export.
- Visible state indicator.
- Bounded recent context and rolling summaries.
- Report contribution summaries and information-tier presentation.
- Full/Compact/Deleted transcript states, manual compact/pin operations, and a
  closed-report retention checkpoint.
- Initial `eden storage status [--details]` attribution for reports,
  conversations, memory, attachments, indexes, and database overhead.
- CLI and direct-command parity.

## Milestone 16 — structured memory integration

- Detect likely durable-memory intent and prompt with a concrete proposal.
- `/memory <content>` and direct equivalent.
- Memory provenance, freshness, confidence, review, and forgetting.
- Controlled retrieval of structured memory across conversations.
- Explicit access to another saved conversation when requested.

## Milestone 18 — local web UI

- Conversation browser.
- Persistence control and visible badges.
- Resume/delete/export controls.
- Report-linked transcript browser.
- Core/supporting/linked-artifact report presentation.
- Memory proposal and management UI.
- Storage usage, retention state, and cleanup-recommendation UI.

---

# 13. Acceptance Principles

1. Temporary conversations leave no resumable transcript.
2. Saved conversations resume after Core restart without requiring the full
   transcript in model context.
3. A saved conversation can exist without a report.
4. A report can link multiple transcripts without embedding them.
5. Report views separate core information, supporting information, and linked
   artifacts.
6. Eden never silently promotes a temporary chat to persistent storage.
7. Eden never silently uses unrelated raw chat history as cross-chat context.
8. Suggested memory requires confirmation; `/memory <content>` is itself the
   explicit instruction to store it.
9. Transcript deletion, report editing, and memory deletion remain separate and
   understandable operations.
10. The active persistence/report state is visible throughout the conversation.
