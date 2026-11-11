import json
import re
from pathlib import Path
from typing import Any

import pytest

from sys_eden.chat_service import ChatService
from sys_eden.conversation_repository import ConversationRepository
from sys_eden.conversation_service import ConversationService
from sys_eden.diagnostics import (
    DiagnosticAssessment,
    DiagnosticConfidence,
    DiagnosticObservation,
    DiagnosticProgress,
    DiagnosticResult,
)
from sys_eden.models import FakeModelProvider, ModelRequest, ModelResponse
from sys_eden.report_repository import ReportRepository
from sys_eden.storage import Database


class FakeDiagnosticAssessor:
    def __init__(self) -> None:
        self.concern: str | None = None
        self.component: str | None = None

    async def assess(
        self,
        *,
        concern: str,
        component: str = "system",
        snapshot: Any | None = None,
        historical_capsules: list[dict[str, Any]] | None = None,
        progress: DiagnosticProgress | None = None,
    ) -> DiagnosticResult:
        self.concern = concern
        self.component = component
        return DiagnosticResult(
            model_id="fake-diagnostic",
            provider="fake",
            assessment=DiagnosticAssessment(
                summary="Generated fake diagnosis: GPU evidence was checked.",
                observations=[
                    DiagnosticObservation(
                        statement="Generated test evidence shows normal GPU utilization."
                    )
                ],
                confidence=DiagnosticConfidence(
                    diagnostic=0.8,
                    research=0,
                    execution=0,
                    safety=1,
                    overall=0.7,
                    rationale="This is generated evidence used only by an isolated test.",
                ),
                explanation="No fault appears in the generated fake GPU snapshot.",
            ),
            context_character_count=100,
        )


def _chat_provider() -> FakeModelProvider:
    def respond(request: ModelRequest) -> ModelResponse:
        if request.output_schema is not None:
            return ModelResponse(
                provider="fake",
                model_id=request.model_id,
                text="",
                structured_data={
                    "summary": "The user asked a generated test question and Eden answered it.",
                    "through_sequence": 2,
                },
            )
        return ModelResponse(
            provider="fake",
            model_id=request.model_id,
            text="This is a generated fake-model response for an isolated test.",
        )

    return FakeModelProvider(responder=respond)


def _diagnostic_routing_provider() -> FakeModelProvider:
    def respond(request: ModelRequest) -> ModelResponse:
        if request.output_schema is not None:
            return ModelResponse(
                provider="fake",
                model_id=request.model_id,
                text="",
                structured_data={"operation": "diagnosis", "component": "gpu"},
            )
        raise AssertionError("diagnostic intent should not use the ordinary chat response")

    return FakeModelProvider(responder=respond)


@pytest.mark.asyncio
async def test_chat_handles_temporary_and_saved_conversations_without_cross_promotion(
    tmp_path: Path,
):
    database = Database(tmp_path / "eden.db")
    database.initialize()
    repository = ConversationRepository(database)
    reports = ReportRepository(database)
    conversations = ConversationService(repository, reports)
    chat = ChatService(conversations, _chat_provider(), summary_interval_messages=2)
    try:
        temporary = conversations.create_temporary(title="Temporary test chat")
        temporary_result = await chat.send(
            temporary.conversation.id, "Generated question for the fake provider."
        )
        assert temporary_result.conversation_id.startswith("TMP-")
        assert repository.list() == []

        saved = conversations.create_saved(title="Saved test chat")
        result = await chat.send(saved.conversation.id, "Generated saved-chat question.")

        assert result.summary_updated
        stored = repository.get(saved.conversation.id)
        assert len(stored.messages) == 2
        assert stored.conversation.rolling_summary == (
            "The user asked a generated test question and Eden answered it."
        )
        assert temporary.conversation.id not in {item.id for item in repository.list()}
    finally:
        database.close()


@pytest.mark.asyncio
async def test_auto_compaction_summarizes_in_bounded_batches_without_deleting_transcript(
    tmp_path: Path,
):
    database = Database(tmp_path / "eden.db")
    database.initialize()
    repository = ConversationRepository(database)
    conversations = ConversationService(repository, ReportRepository(database))
    summary_prompts: list[str] = []
    chat_prompts: list[str] = []

    def respond(request: ModelRequest) -> ModelResponse:
        if request.output_schema is None:
            chat_prompts.append(request.prompt)
            return ModelResponse(provider="fake", model_id=request.model_id, text="Test answer.")
        if "message_parts" not in request.prompt:
            return ModelResponse(
                provider="fake", model_id=request.model_id, text="",
                structured_data={"operation": "chat"},
            )
        summary_prompts.append(request.prompt)
        sequences = re.findall(r'"sequence": (\d+)', request.prompt)
        return ModelResponse(
            provider="fake", model_id=request.model_id, text="",
            structured_data={
                "summary": "The generated test request remains in context.",
                "through_sequence": int(sequences[-1]),
            },
        )

    chat = ChatService(
        conversations,
        FakeModelProvider(responder=respond),
        context_max_characters=1500,
        summary_interval_messages=100,
    )
    try:
        saved = conversations.create_saved(title="Generated long chat")
        result = await chat.send(saved.conversation.id, "x" * 1800)

        stored = repository.get(saved.conversation.id)
        assert result.response == "Test answer."
        assert len(summary_prompts) > 1
        assert all(len(prompt) <= 1500 for prompt in summary_prompts)
        assert len(chat_prompts) == 1
        assert len(chat_prompts[0]) <= 1500
        recent = chat_prompts[0].split("<RECENT_MESSAGES>\n", 1)[1].split(
            "\n</RECENT_MESSAGES>", 1
        )[0]
        assert isinstance(json.loads(recent), list)
        assert stored.conversation.summary_through_sequence == 1
        assert stored.conversation.transcript_state.value == "full"
        assert [message.content for message in stored.messages] == ["x" * 1800, "Test answer."]
    finally:
        database.close()


@pytest.mark.asyncio
async def test_chat_automatically_routes_a_diagnostic_request_through_core_services(
    tmp_path: Path,
):
    database = Database(tmp_path / "eden.db")
    database.initialize()
    repository = ConversationRepository(database)
    conversations = ConversationService(repository, ReportRepository(database))
    diagnostics = FakeDiagnosticAssessor()
    chat = ChatService(
        conversations,
        _diagnostic_routing_provider(),
        diagnostics=diagnostics,
    )
    try:
        temporary = conversations.create_temporary(title="Generated diagnostic test")

        result = await chat.send(
            temporary.conversation.id,
            "Why is my generated test game stuttering? Check the GPU.",
        )

        assert result.operation == "diagnosis"
        assert result.diagnostic_component == "gpu"
        assert diagnostics.component == "gpu"
        assert diagnostics.concern == "Why is my generated test game stuttering? Check the GPU."
        assert "Generated fake diagnosis" in result.response
        stored = conversations.get_current(
            temporary.conversation.id,
            owner_client_id=temporary.conversation.owner_client_id,
        )
        assert [message.role.value for message in stored.messages] == ["user", "eden"]
    finally:
        database.close()
