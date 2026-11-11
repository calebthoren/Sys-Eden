"""Core-owned report search and tiered retrieval service."""

from __future__ import annotations

from sys_eden.json_contract import EdenJsonEnvelope, JsonAssociations
from sys_eden.report_knowledge import ReportKnowledgeService, ReportKnowledgeView
from sys_eden.report_models import (
    Report,
    ReportSearch,
    ReportState,
    ReportStatus,
    ReportSummary,
    utc_now,
)
from sys_eden.report_repository import ReportRepository


class ReportService:
    def __init__(
        self,
        repository: ReportRepository,
        knowledge: ReportKnowledgeService,
    ) -> None:
        self.repository = repository
        self.knowledge = knowledge

    def search(self, query: ReportSearch | None = None) -> list[ReportSummary]:
        return self.repository.search(query)

    def get(self, report_id: str) -> ReportKnowledgeView:
        return self.knowledge.get(report_id)

    def export_json(self, report_id: str) -> str:
        """Export canonical report knowledge plus artifact references, never raw transcripts."""
        return EdenJsonEnvelope[ReportKnowledgeView](
            type="report.export", data_version=2, status="success",
            request_id=f"export-{report_id}"[:100], generated_at=utc_now(),
            associations=JsonAssociations(report_id=report_id), data=self.get(report_id),
        ).model_dump_json(indent=2)

    def close(
        self, report_id: str, *, status: ReportStatus, summary: str, outcome: str
    ) -> Report:
        """Record a reviewed conclusion before retention candidates are generated."""
        proposed = self.prepare_close(report_id, status=status, summary=summary, outcome=outcome)
        return self.repository.update(proposed)

    def prepare_close(
        self, report_id: str, *, status: ReportStatus, summary: str, outcome: str
    ) -> Report:
        """Validate closure, including verification, before invoking contribution inference."""
        if status is ReportStatus.ACTIVE:
            raise ValueError("a closed report cannot remain active")
        if not summary.strip() or not outcome.strip():
            raise ValueError("closing a report requires a summary and outcome")
        report = self.repository.get(report_id)
        if report.state is ReportState.CLOSED:
            raise ValueError("this report is already closed")
        values = report.model_dump(mode="python")
        values.update(
            state=ReportState.CLOSED,
            status=status,
            activity=None,
            summary=summary.strip(),
            outcome=outcome.strip(),
            closed_at=utc_now(),
        )
        return Report.model_validate(values)
