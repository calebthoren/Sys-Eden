# Sys Eden — Milestone 5 Acceptance and Testing

> **Document role:** Test handoff, coverage map, and closeout evidence
> **Status:** v1.0 — owner feedback received; CLI corrections awaiting retest

Milestone 5 implements durable tasks, the Core/client boundary, conversation
persistence, progress, report links, storage visibility, and the integrated CLI.
Its canonical requirements remain in `Sys_Eden_roadmap_v1.2.md`, section 9.
The owner explicitly approved the final visuals and requested full closeout.
All final checks pass on the approved candidate. Verified source and issue
templates are published on GitHub; #11/#1 record the milestone signoff.

## Start testing

Run from the repository root in a normal Windows terminal:

```powershell
.\.venv\Scripts\python.exe scripts/milestone5_candidate.py --candidate 896c70ed7b94cc99 open
```

Candidate `896c70ed7b94cc99` is a frozen copy of the built wheel. Its manifest
records SHA-256 hashes of the package files and is checked on each launch. It
includes the terminal artwork. Source edits do not change this candidate.

The launcher uses separate local data under
`data/milestone5-candidates/896c70ed7b94cc99/runtime/`. It reuses the existing
local `qwen3.5:9b` installation and the development Python dependencies. Do not
change those shared dependencies while this candidate is being tested. No
second model library or Windows service installation is required.

Opening a client does not start Core. If the candidate Core is stopped, choose
Start Core explicitly. Its lifecycle and conversations are separate from the
normal development profile. Avoid admin elevation; the app runs as the owner.

The app's `/exit` closes that client; `/corestop` stops this test Core. For a
direct command in another terminal, use the same candidate ID:

```powershell
.\.venv\Scripts\python.exe scripts/milestone5_candidate.py --candidate 896c70ed7b94cc99 command storage status --details
.\.venv\Scripts\python.exe scripts/milestone5_candidate.py --candidate 896c70ed7b94cc99 status
.\.venv\Scripts\python.exe scripts/milestone5_candidate.py --candidate 896c70ed7b94cc99 stop
```

## First owner test pass

1. Review the running home at your usual size and a narrower size. Check the
   header, tree, composer, and Conversations/Monitoring buttons.
2. Type a generated draft. Move the cursor, use Backspace/Delete, and press Esc
   with text present. The draft should remain intact.
3. Open `/help` and try slash-command filtering. Return with Esc.
4. Ask a general question such as "What does a computer fan do?" Check the
   temporary badge and that this stays a normal conversation.
5. Run `/inspect cpu`. Check progress and the resulting evidence-based answer.
   Use `/details` for operation details and `/tasks` to inspect the diagnostic task.
6. Use `/home` and Conversations to return to that temporary thread. Navigation
   must not discard it or interleave another thread's transcript.
7. Use `/save`, record its conversation ID, and exit the client. Reopen the same
   candidate and resume the saved chat from Conversations.
8. Resize and scroll a long conversation. The title/buttons/composer should stay
   fixed while the transcript scrolls; long replies should remain accessible.
9. Try deleting a generated saved chat, cancel once, then confirm and restore
   it in the same client session. Inspect the Activity and Conversations views.
10. Try `/corestop`, cancel first, then confirm after saving wanted temporary
    chats. The CLI should stay open in the stopped view. Start Core again and
    verify the saved chat remains available.

Reports can be empty in a fresh profile: a chat or completed task does not
automatically create a report. Report-link/retention logic is covered with
generated report fixtures in the automated suite; the owner may review those
checks separately rather than invent a real system incident.

The Monitoring destination does not mean Milestone 11's scheduled monitoring
is implemented. System mutation, the privileged service, and screenshot access
are outside this candidate's scope.

## Track results

The owner's feedback and follow-ups report that the tested behavior otherwise appeared
to work, with these requested CLI corrections:

- [#14](https://github.com/calebthoren/Sys-Eden/issues/14): save/pin notices stay
  at their chronological position and scroll away with later turns.
- [#15](https://github.com/calebthoren/Sys-Eden/issues/15): actions below the
  composer, help text below those actions, a rounded title/status header with dark gray characters on black,
  and a feed filling the space
  directly between header and composer. Down at the composer's bottom edge
  reaches actions; Up returns to editing.
- [#16](https://github.com/calebthoren/Sys-Eden/issues/16): two wrapped transcript
  lines per mouse-wheel event, retaining Page Up/Down for larger movements.

DEC-053 defines the accepted layout. The owner has now explicitly approved its
final appearance; automated evidence covers the individual failure fixtures.

Use [overview #1](https://github.com/calebthoren/Sys-Eden/issues/1) and the linked
objective issues. A useful result is: candidate ID, objective/check, steps,
expected behavior, actual behavior, and pass/fail. Report each independent
defect separately and link its objective. Use generated text and sanitize
public issue content; raw local evidence stays in ignored `data/`.

| Objective | Roadmap acceptance items | GitHub issue |
| --- | --- | --- |
| CLI visual overview | 5, 7, 26, 27, 30, 31 | [#2](https://github.com/calebthoren/Sys-Eden/issues/2) |
| Keyboard navigation and discovery | 8, 28, 32, 33, 35 | [#3](https://github.com/calebthoren/Sys-Eden/issues/3) |
| Unified chat and diagnostics | 24, 34 | [#4](https://github.com/calebthoren/Sys-Eden/issues/4) |
| Persistence and temporary privacy | 17, 18, 20, 23 | [#5](https://github.com/calebthoren/Sys-Eden/issues/5) |
| Tasks, progress, and recovery | 1, 2, 3, 4, 6, 15, 24, 25 | [#6](https://github.com/calebthoren/Sys-Eden/issues/6) |
| Core/client lifecycle | 10, 11, 13, 14, 16 | [#7](https://github.com/calebthoren/Sys-Eden/issues/7) |
| Report links and retention | 19, 20, 22 | [#8](https://github.com/calebthoren/Sys-Eden/issues/8) |
| Storage visibility | 21 | [#9](https://github.com/calebthoren/Sys-Eden/issues/9) |
| Direct commands and JSON | 5, 9, 12, 29 | [#10](https://github.com/calebthoren/Sys-Eden/issues/10) |
| Candidate and release closeout | All; completion rule | [#11](https://github.com/calebthoren/Sys-Eden/issues/11) |

## Final signoff verification

- Full current Windows suite: **239 passed**.
- Ruff: passed; Pyright: zero errors/warnings.
- All eight live packaged checks pass on approved candidate `896c70ed7b94cc99`.
- Sanitized result: `data/milestone5-candidates/896c70ed7b94cc99/verification-edff8623/smoke-result.json`.
- Owner explicitly approved the final visual arrangement and requested closeout.
- No privileged service, real system-mutation authority, or screen capture is introduced.

The following sections preserve earlier implementation/test history; the final
results above supersede older test counts and pending visual-review notes.

## Earlier engineering verification

- Automated closeout run: 236 tests pass; Ruff passes; Pyright reports zero
  errors and warnings. These cover deterministic adapters, isolated Core process
  interruption, migrations, privacy, recovery, report retention, and CLI input.
- Source distribution and wheel build successfully with `uv build --offline`.
- The frozen candidate starts a normal-user Core and connects over Windows named
  pipes; its local Ollama health check passes.
- All eight real-model packaged smoke checks passed for candidate
  `04535d7ff34abe92`: status without auto-start, idempotent Core start, local model
  health/discovery, CPU inspection, saved conversational inference without a
  task, restart/resumption, CPU diagnosis with a durable task, and storage/error
  JSON. Sanitized evidence is in the ignored verification profile's
  `smoke-result.json`.
- Owner visual and behavior acceptance remains pending.

### Crash-recovery correction

Closeout reproduced a Windows `SQLITE_IOERR_TRUNCATE` failure in 11 of 12
immediate forced-crash/reopen trials. This matches a reported Windows shared
memory cleanup problem in the installed SQLite runtime; the database inspected
afterward passed its integrity check. The fix retries only that error during
WAL initialization for at most three seconds. Other storage errors are not
retried, and recovery never removes journal files. All 12 repeated crash/reopen
trials passed after the fix; deterministic regressions also cover eventual
success, a bounded failure, and immediate propagation of other error types.

The original candidate `1f67e5da7c3c8711` remains frozen and does not contain
this correction. The earlier candidate `04535d7ff34abe92` contains that fix and the CLI
feedback corrections in DEC-053, and
passes the same eight packaged live smoke checks. Existing owner test sessions
are not stopped or migrated automatically.
[Issue #13](https://github.com/calebthoren/Sys-Eden/issues/13) records the defect
and verification. The upstream report and maintainer response are on the
[SQLite forum](https://sqlite.org/forum/info/ba7afbd0e81501118563617430fe06d0aca052e55ece2b0d457f8e16fcf85bba).

Repeat the packaged smoke check without touching the owner's testing runtime:

```powershell
.\.venv\Scripts\python.exe scripts/milestone5_smoke.py --candidate 04535d7ff34abe92
```

It uses a new verification profile and stops only its own Core. Sanitized
results contain check names and timing, excluding raw model answers and machine
inspection payloads. The script performs local inference and read-only CPU
inspection. Windows named-pipe validation must run outside a sandbox that blocks
pipe creation; this does not require Administrator privileges for Eden.

To prepare a later candidate after fixes, build a fresh wheel and run
`scripts/milestone5_candidate.py prepare`. Record the new ID before switching
tests. Existing candidates and test data are preserved. Keep using an explicit
candidate ID so a newer build cannot silently replace the one being tested.

## Completed closeout gates

- [x] Record the owner's acceptance results and fix blocking defects.
- [x] Complete live packaged smoke verification and record its outcome.
- [x] Review the changed scope and exclude private runtime artifacts from the release.
- [x] Commit the verified implementation as a local owner-acceptance snapshot.
- [x] Publish reviewed code/templates to GitHub and verify the remote tree and file hashes.
- [x] Mark Milestone 5 complete after required checks and explicit owner approval.

Milestone 6 remains next: planning, risk evaluation, and scoped approval before
system writes. Native GitHub milestone/custom-status-label setup remains pending;
the current tracker uses overview links, body status, and open/closed state.

Footer follow-up: candidate `5563c4a285bec433` places the composer, buttons,
then help text in that order. All 77 terminal regressions, Ruff, package builds,
and whitespace checks pass. The existing live-model smoke evidence above
belongs to the earlier candidate; model/runtime paths did not change.

Top-alignment follow-up: current candidate `c7b39ff543f2203f` includes the
composer ? buttons ? help order and starts short conversations directly below
the header, with blank space below messages. All 80 terminal regressions, Ruff,
package builds, and whitespace checks pass. No model/runtime paths changed.

Rounded-header and scroll refinement: current candidate `365dce98323711a1`
restores a rounded title/status panel using the same dark gray background as
the composer, with light text, and scrolls two wrapped rows per wheel event.
All 80 terminal regressions pass, including narrow/short terminals, rounded
corners, matching backgrounds, footer placement, and exact wheel distances.
Ruff, package builds, and whitespace checks pass. Owner retest remains pending.

Header color correction: current candidate `d467c58d492968cd` keeps the
rounded header black and colors its border/text characters dark gray, using the
gray previously used as the composer fill. Two-row wheel scrolling remains.
All 80 terminal regressions pass, including an explicit check that no gray
background fill is emitted for the header. Ruff and package builds also pass.

Gray calibration and buttons: current candidate `896c70ed7b94cc99` lightens
header characters and uses exactly the same lighter gray for the navigation
buttons, with black backgrounds. The composer fill is unchanged. All 80
terminal regressions, Ruff, package builds, and whitespace checks pass.
Visual owner retesting remains pending.

Milestone 6 is prepared in [overview #12](https://github.com/calebthoren/Sys-Eden/issues/12)
with nine objective issues (#17?#25), each Not started. No implementation is
claimed by creating those issues.

## Publication and final transition

The verified source snapshot is published on GitHub main in commit
`d43a44e0942fba3b84a821f9d2ffef6ce9cc278c`. Its Git tree exactly matches
the reviewed local source tree, and the issue template and CLI source blob
hashes were checked after publication. Private runtime data, conversations,
databases, local model files, and the untracked large artwork were excluded.
The original granular development history remains preserved locally.

The final documentation sync records this completed status. Milestone 6 remains
Not started, with objective issues #17?#25 and dependencies under #12.
