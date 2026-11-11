# Sys Eden — Issue Tracking

> **Document role:** Development workflow for tracking implementation and testing
> **Status:** v1.0

Canonical repository documents own requirements and implementation order.
GitHub issues track progress, evidence, and defects against those requirements.

Use one issue for each independently testable milestone objective. Titles use
`Milestone 5: CLI Visual Overview`, for example. Each issue describes the
experience in use, cites the roadmap acceptance items it covers, lists observable
checks, records actual verification, and links remaining defects. Avoid an issue
per function or one giant issue for the entire implementation.

| Status | Meaning |
| --- | --- |
| Not started | Planned scope with no implementation work underway |
| In progress | Implementation or engineering verification is underway |
| Ready for user testing | A named candidate is available with engineering evidence |
| Blocked | A specific dependency prevents progress; name it in the issue |
| Done | Required verification and applicable owner acceptance passed |

Keep the current status near the top of each issue. Open issues may have any of
the first four statuses. Close as completed only for Done; lack of owner testing
is not a passed check. Checked engineering evidence does not imply visual signoff.
Change status and checklists when new evidence arrives, including regression
failures. The overview issue links all objectives and records milestone gates.

GitHub native milestones are the recommended grouping for objective issues.
Custom status labels or a Projects board can add filtering later. The current
connector supports issue creation and updates but cannot create those grouping
objects. The initial tracker therefore uses a linked overview and explicit body
status; native milestone and custom-label setup are not yet configured.

Initial overview: [Milestone 5 closeout #1](https://github.com/calebthoren/Sys-Eden/issues/1).
The acceptance guide maps all 35 roadmap checks to objective issues.

[Milestone 6 overview #12](https://github.com/calebthoren/Sys-Eden/issues/12)
links objective issues #17–#25 with dependencies, acceptance checks, and initial
Not started status. Milestone 5 implementation acceptance, owner visual approval,
final validation, and source/template publication are complete; #11/#1 record
the closeout evidence.

File each independent defect as a linked issue with candidate/commit, reproduction
steps, expected/actual behavior, impact, and a verification checklist. Preserve
the failed-check history rather than silently changing the original expectation.
Issue templates are in `.github/ISSUE_TEMPLATE/`; they become available on GitHub
after the templates reach the default branch.

The repository is public. Publish generated examples, sanitized failures, and
verification summaries. Keep real transcripts, machine snapshots, identifiers,
credentials, database files, and raw local evidence off public issues.
