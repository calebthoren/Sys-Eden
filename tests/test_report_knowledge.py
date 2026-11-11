from pathlib import Path

from sys_eden.conversation_models import ConversationRole, ReportLinkRole
from sys_eden.conversation_repository import ConversationRepository
from sys_eden.conversation_service import ConversationService
from sys_eden.report_knowledge import ReportKnowledgeService, render_report_knowledge
from sys_eden.report_models import Report
from sys_eden.report_repository import ReportRepository
from sys_eden.storage import Database


def test_report_views_separate_core_supporting_information_and_linked_artifacts(
    tmp_path: Path,
):
    database = Database(tmp_path / "eden.db")
    database.initialize()
    reports = ReportRepository(database)
    conversations = ConversationRepository(database)
    try:
        report = reports.create(
            Report(
                id="rpt-tiered-view",
                title="Tiered report fixture",
                objective="Keep material summaries separate from raw transcripts.",
            )
        )
        chat = ConversationService(conversations, reports)
        conversation = chat.create_saved(title="Detailed supporting conversation")
        conversation = chat.append(
            conversation.conversation.id,
            role=ConversationRole.USER,
            content="Private raw fixture wording that must not enter the report view.",
        )
        chat.link_saved_conversation(
            conversation.conversation.id,
            report.id,
            role=ReportLinkRole.PRIMARY,
            contribution_summary="The user supplied a material test constraint.",
        )

        view = ReportKnowledgeService(reports, conversations).get(report.id)
        human = render_report_knowledge(view)

        assert view.report.id == report.id
        assert view.capsule.conversation_contributions == [
            "The user supplied a material test constraint."
        ]
        assert view.capsule.linked_conversation_ids == [conversation.conversation.id]
        assert "Supporting Information" in human
        assert "Linked Artifacts" in human
        assert "Private raw fixture wording" not in human
        assert "Private raw fixture wording" not in view.capsule.model_dump_json()
    finally:
        database.close()
