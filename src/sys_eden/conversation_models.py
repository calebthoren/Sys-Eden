"""Conversation persistence, transcript, and report-link domain models."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

type JsonScalar = str | int | float | bool | None


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12].upper()}"


def new_conversation_id(*, generated_test_data: bool = False) -> str:
    return _new_id("TCH" if generated_test_data else "CHT")


def new_temporary_conversation_id() -> str:
    return _new_id("TMP")


def new_contribution_id() -> str:
    return _new_id("RCN")


class ConversationPersistence(StrEnum):
    TEMPORARY = "temporary"
    SAVED = "saved"


class TranscriptState(StrEnum):
    FULL = "full"
    COMPACT = "compact"
    DELETED = "deleted"


class ConversationRole(StrEnum):
    USER = "user"
    EDEN = "eden"


class ReportLinkRole(StrEnum):
    PRIMARY = "primary"
    RELATED = "related"


class LinkActor(StrEnum):
    USER = "user"
    EDEN = "eden"


class ConversationMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_id: str = Field(min_length=1, max_length=100)
    sequence: int = Field(ge=1)
    role: ConversationRole
    content: str = Field(min_length=1, max_length=200_000)
    created_at: datetime
    retained_in_compact: bool = False
    generated_test_data: bool = False
    metadata: dict[str, JsonScalar] = Field(default_factory=dict)


class Conversation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=100)
    schema_version: int = Field(default=1, ge=1)
    revision: int = Field(default=1, ge=1)
    title: str = Field(min_length=1, max_length=300)
    persistence: ConversationPersistence
    transcript_state: TranscriptState
    pinned: bool = False
    created_at: datetime
    updated_at: datetime
    last_resumed_at: datetime | None = None
    rolling_summary: str | None = Field(default=None, max_length=20_000)
    summary_through_sequence: int = Field(default=0, ge=0)
    retention_policy: str | None = Field(default=None, max_length=200)
    last_message_sequence: int = Field(default=0, ge=0)
    generated_test_data: bool = False
    owner_client_id: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def validate_storage(self) -> Conversation:
        if self.persistence is ConversationPersistence.TEMPORARY:
            if self.transcript_state is not TranscriptState.FULL:
                raise ValueError("temporary conversations exist only as full active sessions")
            if not self.id.startswith("TMP-"):
                raise ValueError("temporary conversations require a TMP identifier")
            if not self.owner_client_id:
                raise ValueError("temporary conversations require an owning CLI client")
        elif self.id.startswith("TMP-"):
            raise ValueError("saved conversations cannot use a TMP identifier")
        elif self.owner_client_id is not None:
            raise ValueError("saved conversations cannot be owned by one CLI client")
        if self.generated_test_data and not self.id.startswith("TCH-"):
            raise ValueError("generated test conversations require a TCH identifier")
        if not self.generated_test_data and self.id.startswith("TCH-"):
            raise ValueError("TCH identifiers are reserved for generated test conversations")
        if self.transcript_state is TranscriptState.DELETED and (
            self.rolling_summary is not None or self.summary_through_sequence != 0
        ):
            raise ValueError("deleted transcripts cannot retain a rolling summary")
        if self.summary_through_sequence > self.last_message_sequence:
            raise ValueError("summary cannot cover messages that do not exist")
        return self


class ConversationAggregate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation: Conversation
    messages: list[ConversationMessage] = Field(default_factory=list)


class ConversationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    transcript_state: TranscriptState
    pinned: bool
    updated_at: datetime
    last_message_sequence: int = Field(ge=0)
    primary_report_id: str | None = None
    generated_test_data: bool = False


class ReportConversationLink(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_id: str = Field(min_length=1, max_length=100)
    conversation_id: str = Field(min_length=1, max_length=100)
    role: ReportLinkRole
    contribution_summary: str | None = Field(default=None, max_length=8000)
    contribution_through_sequence: int = Field(default=0, ge=0)
    contribution_updated_at: datetime | None = None
    linked_at: datetime
    linked_by: LinkActor


class ConversationContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_id: str
    rolling_summary: str | None
    recent_messages: list[ConversationMessage]
    transcript_state: TranscriptState
    primary_report_id: str | None = None


class ConversationWorkStatus(BaseModel):
    """Small UI-independent snapshot of current conversation work."""

    model_config = ConfigDict(extra="forbid")

    conversation_id: str
    active: bool = True
    phase: str = Field(min_length=1, max_length=120)
    detail: str = Field(min_length=1, max_length=500)
    started_at: datetime


class RetentionCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_id: str
    conversation_id: str
    eligible: bool
    reason: str = Field(min_length=1, max_length=2000)
    reviewed_at: datetime


class StandaloneConversationContribution(BaseModel):
    """Material chat knowledge retained without retaining the source transcript."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=new_contribution_id, min_length=1, max_length=100)
    report_id: str = Field(min_length=1, max_length=100)
    source_temporary_conversation_id: str = Field(min_length=1, max_length=100)
    summary: str = Field(min_length=1, max_length=8000)
    created_at: datetime
    transcript_retained: bool = False

    @model_validator(mode="after")
    def require_unretained_temporary_source(self) -> StandaloneConversationContribution:
        if not self.source_temporary_conversation_id.startswith("TMP-"):
            raise ValueError("standalone contributions require a temporary source identifier")
        if self.transcript_retained:
            raise ValueError("standalone contributions must not claim transcript retention")
        return self
