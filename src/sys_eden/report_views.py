"""Derived report capsules and human-readable views."""

from __future__ import annotations

from sys_eden.report_models import (
    HypothesisStatus,
    ObservationKind,
    Report,
    ReportCapsule,
    ReportSummary,
)


def build_capsule(report: Report) -> ReportCapsule:
    """Build compact model context from the canonical structured aggregate."""
    unresolved = [
        item.statement
        for item in report.hypotheses
        if item.status in {HypothesisStatus.ACTIVE, HypothesisStatus.UNRESOLVED}
    ]
    return ReportCapsule(
        id=report.id,
        title=report.title,
        objective=report.objective,
        state=report.state,
        status=report.status,
        priority=report.priority,
        purpose_tags=report.purpose_tags,
        component_tags=report.component_tags,
        conclusion=report.outcome or report.summary,
        key_observations=[item.statement for item in report.observations[:5]],
        hypotheses=[f"{item.status.value}: {item.statement}" for item in report.hypotheses[:5]],
        strongest_evidence=[item.summary for item in report.evidence[:5]],
        latest_confidence=(report.confidence_history[-1] if report.confidence_history else None),
        verification=report.verifications[-1] if report.verifications else None,
        unresolved=unresolved,
        related_report_ids=[item.target_report_id for item in report.relationships],
        primary_chain_id=report.primary_chain_id,
        updated_at=report.updated_at,
    )


def render_report_summary(summary: ReportSummary) -> str:
    tags = sorted(tag.value for tag in summary.purpose_tags | summary.component_tags)
    suffix = f" [{', '.join(tags)}]" if tags else ""
    return (
        f"{summary.id}  {summary.status.value}/{summary.state.value}  "
        f"{summary.priority.value}  {summary.title}{suffix}"
    )


def render_report(report: Report) -> str:
    """Render a deterministic user view without creating another source of truth."""
    lines = [
        report.title,
        f"ID: {report.id}",
        f"State: {report.state.value}",
        f"Status: {report.status.value}",
        f"Priority: {report.priority.value}",
        f"Updated: {report.updated_at.isoformat()}",
        "",
        "Objective",
        report.objective,
    ]
    if report.summary:
        lines.extend(("", "Summary", report.summary))
    if report.trigger:
        lines.extend(("", "Trigger", report.trigger))
    if report.observations:
        lines.extend(("", "Observations"))
        lines.extend(
            f"- {item.kind.value}: {item.statement}" + (f" ({item.source})" if item.source else "")
            for item in report.observations
        )
    if report.hypotheses:
        lines.extend(("", "Hypotheses"))
        lines.extend(
            f"- {item.status.value}: {item.statement}"
            + (f" — {item.rationale}" if item.rationale else "")
            for item in report.hypotheses
        )
    if report.evidence:
        lines.extend(("", "Evidence"))
        lines.extend(
            f"- {item.id} [{item.evidence_type}] {item.summary} (source: {item.source})"
            for item in report.evidence
        )
    if report.confidence_history:
        lines.extend(("", "Confidence"))
        for item in report.confidence_history:
            dimensions = ", ".join(
                f"{name}={value:.0%}"
                for name, value in (
                    ("diagnostic", item.diagnostic),
                    ("research", item.research),
                    ("execution", item.execution),
                    ("safety", item.safety),
                    ("overall", item.overall),
                )
                if value is not None
            )
            lines.append(f"- {item.checkpoint}: {dimensions}")
    if report.verifications:
        lines.extend(("", "Verification"))
        lines.extend(
            f"- {item.verdict.value}: {item.summary} "
            f"(criteria: {item.success_criteria}; method: {item.method})"
            for item in report.verifications
        )
    if report.outcome:
        lines.extend(("", "Outcome", report.outcome))
    if report.relationships:
        lines.extend(("", "Related Reports"))
        lines.extend(
            f"- {item.relationship_type.value}: {item.target_report_id}"
            for item in report.relationships
        )
    unresolved = [
        item.statement
        for item in report.hypotheses
        if item.status in {HypothesisStatus.ACTIVE, HypothesisStatus.UNRESOLVED}
    ] + [item.statement for item in report.observations if item.kind is ObservationKind.UNKNOWN]
    if unresolved:
        lines.extend(("", "Remaining Uncertainty"))
        lines.extend(f"- {item}" for item in unresolved)
    return "\n".join(lines)
