"""Tiered report views that reference conversations without embedding transcripts."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from sys_eden.conversation_models import ReportLinkRole, TranscriptState
from sys_eden.conversation_repository import ConversationRepository
from sys_eden.report_models import Report, ReportCapsule
from sys_eden.report_repository import ReportRepository
from sys_eden.report_views import build_capsule, render_report


class ConversationContributionView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_id: str
    summary: str


class LinkedConversationArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_id: str
    title: str
    role: ReportLinkRole
    transcript_state: TranscriptState
    available: bool


class ReportKnowledgeView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report: Report
    capsule: ReportCapsule
    supporting_information: list[ConversationContributionView]
    linked_artifacts: list[LinkedConversationArtifact]


class ReportKnowledgeService:
    def __init__(
        self,
        reports: ReportRepository,
        conversations: ConversationRepository,
    ) -> None:
        self.reports = reports
        self.conversations = conversations

    def get(self, report_id: str) -> ReportKnowledgeView:
        report = self.reports.get(report_id)
        contributions: list[ConversationContributionView] = []
        artifacts: list[LinkedConversationArtifact] = []
        for link in self.conversations.links_for_report(report_id):
            conversation = self.conversations.get(link.conversation_id).conversation
            if link.contribution_summary:
                contributions.append(
                    ConversationContributionView(
                        conversation_id=conversation.id,
                        summary=link.contribution_summary,
                    )
                )
            artifacts.append(
                LinkedConversationArtifact(
                    conversation_id=conversation.id,
                    title=conversation.title,
                    role=link.role,
                    transcript_state=conversation.transcript_state,
                    available=conversation.transcript_state is not TranscriptState.DELETED,
                )
            )
        contributions.extend(
            ConversationContributionView(
                conversation_id=item.source_temporary_conversation_id,
                summary=item.summary,
            )
            for item in self.conversations.standalone_contributions_for_report(report_id)
        )
        capsule = build_capsule(
            report,
            conversation_contributions=[item.summary for item in contributions],
            linked_conversation_ids=[item.conversation_id for item in artifacts],
        )
        return ReportKnowledgeView(
            report=report,
            capsule=capsule,
            supporting_information=contributions,
            linked_artifacts=artifacts,
        )


def render_report_knowledge(view: ReportKnowledgeView) -> str:
    lines = [render_report(view.report)]
    if view.supporting_information:
        lines.extend(("", "Supporting Information"))
        lines.extend(
            f"- {item.conversation_id}: {item.summary}"
            for item in view.supporting_information
        )
    if view.linked_artifacts:
        lines.extend(("", "Linked Artifacts"))
        lines.extend(
            (
                f"- conversation {item.conversation_id} [{item.role.value}; "
                f"{item.transcript_state.value}; "
                f"{'available' if item.available else 'transcript deleted'}]: {item.title}"
            )
            for item in view.linked_artifacts
        )
    return "\n".join(lines)
