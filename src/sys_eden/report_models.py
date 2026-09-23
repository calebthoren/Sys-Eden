"""Validated domain models for durable structured reports."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_report_id() -> str:
    return f"rpt-{uuid4()}"


def new_chain_id() -> str:
    return f"chn-{uuid4()}"


def new_evidence_id() -> str:
    return f"evd-{uuid4()}"


class ReportState(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class ReportStatus(StrEnum):
    ACTIVE = "active"
    RESOLVED = "resolved"
    FAILED = "failed"
    ARCHIVED = "archived"
    CANCELED = "canceled"


class ReportPriority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class ReportActivity(StrEnum):
    ACTIVE = "active"
    WAITING_USER = "waiting_user"
    WAITING_CONDITION = "waiting_condition"
    MONITORING = "monitoring"
    PAUSED = "paused"


class PurposeTag(StrEnum):
    PROBLEM = "problem"
    MONITORING = "monitoring"
    RESEARCH = "research"
    OPTIMIZATION = "optimization"
    UPGRADE = "upgrade"
    MAINTENANCE = "maintenance"
    INSTALLATION = "installation"
    CLEANUP = "cleanup"
    BENCHMARK = "benchmark"
    SECURITY = "security"
    CONFIGURATION = "configuration"
    RECOVERY = "recovery"


class ComponentTag(StrEnum):
    CPU = "cpu"
    GPU = "gpu"
    RAM = "ram"
    STORAGE = "storage"
    NETWORK = "network"
    DRIVERS = "drivers"
    OS = "os"
    PSU = "psu"
    MOTHERBOARD = "motherboard"
    FIRMWARE = "firmware"
    BIOS_UEFI = "bios_uefi"
    AUDIO = "audio"
    BLUETOOTH = "bluetooth"
    USB = "usb"
    DISPLAY = "display"
    COOLING = "cooling"
    BATTERY = "battery"
    SOFTWARE = "software"
    SECURITY = "security"
    FILESYSTEM = "filesystem"


class ObservationKind(StrEnum):
    OBSERVED_FACT = "observed_fact"
    INFERENCE = "inference"
    UNKNOWN = "unknown"
    USER_OBSERVATION = "user_observation"


class HypothesisStatus(StrEnum):
    ACTIVE = "active"
    SUPPORTED = "supported"
    REJECTED = "rejected"
    UNRESOLVED = "unresolved"


class VerificationVerdict(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"


class RelationshipType(StrEnum):
    PREVIOUS_ATTEMPT = "previous_attempt"
    FOLLOW_UP = "follow_up"
    MONITORING_OF = "monitoring_of"
    CAUSED_BY = "caused_by"
    RELATED_TO = "related_to"
    SUPERSEDES = "supersedes"
    VERIFICATION_OF = "verification_of"
    RESEARCH_FOR = "research_for"
    USES_EVIDENCE_FROM = "uses_evidence_from"


class ReportObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: ObservationKind
    statement: str = Field(min_length=1, max_length=4000)
    source: str | None = Field(default=None, max_length=1000)
    observed_at: datetime = Field(default_factory=utc_now)


class ReportHypothesis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statement: str = Field(min_length=1, max_length=4000)
    status: HypothesisStatus = HypothesisStatus.ACTIVE
    rationale: str | None = Field(default=None, max_length=8000)
    created_at: datetime = Field(default_factory=utc_now)


class EvidenceReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=new_evidence_id, min_length=1, max_length=100)
    evidence_type: str = Field(min_length=1, max_length=100)
    source: str = Field(min_length=1, max_length=1000)
    summary: str = Field(min_length=1, max_length=8000)
    reference: str | None = Field(default=None, max_length=4000)
    sensitivity: str = Field(default="internal", min_length=1, max_length=100)
    captured_at: datetime = Field(default_factory=utc_now)


class ConfidenceSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checkpoint: str = Field(min_length=1, max_length=100)
    diagnostic: float | None = Field(default=None, ge=0, le=1)
    research: float | None = Field(default=None, ge=0, le=1)
    execution: float | None = Field(default=None, ge=0, le=1)
    safety: float | None = Field(default=None, ge=0, le=1)
    overall: float | None = Field(default=None, ge=0, le=1)
    rationale: str | None = Field(default=None, max_length=8000)
    recorded_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def require_a_dimension(self) -> ConfidenceSnapshot:
        if all(
            value is None
            for value in (
                self.diagnostic,
                self.research,
                self.execution,
                self.safety,
                self.overall,
            )
        ):
            raise ValueError("At least one confidence dimension is required")
        return self


class VerificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    success_criteria: str = Field(min_length=1, max_length=8000)
    method: str = Field(min_length=1, max_length=4000)
    verdict: VerificationVerdict
    summary: str = Field(min_length=1, max_length=8000)
    evidence_ids: list[str] = Field(default_factory=list)
    performed_at: datetime = Field(default_factory=utc_now)


class ReportRelationship(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_report_id: str = Field(min_length=1, max_length=100)
    relationship_type: RelationshipType
    created_at: datetime = Field(default_factory=utc_now)


class Report(BaseModel):
    """One coherent report effort, independent from task runtime state."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=new_report_id, min_length=1, max_length=100)
    schema_version: int = Field(default=1, ge=1)
    revision: int = Field(default=1, ge=1)
    title: str = Field(min_length=1, max_length=300)
    objective: str = Field(min_length=1, max_length=8000)
    state: ReportState = ReportState.OPEN
    status: ReportStatus = ReportStatus.ACTIVE
    priority: ReportPriority = ReportPriority.NORMAL
    activity: ReportActivity | None = ReportActivity.ACTIVE
    trigger: str | None = Field(default=None, max_length=4000)
    summary: str | None = Field(default=None, max_length=8000)
    outcome: str | None = Field(default=None, max_length=8000)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    closed_at: datetime | None = None
    primary_chain_id: str | None = Field(default=None, max_length=100)
    purpose_tags: set[PurposeTag] = Field(default_factory=set)
    component_tags: set[ComponentTag] = Field(default_factory=set)
    observations: list[ReportObservation] = Field(default_factory=list)
    hypotheses: list[ReportHypothesis] = Field(default_factory=list)
    evidence: list[EvidenceReference] = Field(default_factory=list)
    confidence_history: list[ConfidenceSnapshot] = Field(default_factory=list)
    verifications: list[VerificationResult] = Field(default_factory=list)
    relationships: list[ReportRelationship] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_lifecycle(self) -> Report:
        if self.state is ReportState.OPEN and self.status not in {
            ReportStatus.ACTIVE,
            ReportStatus.RESOLVED,
            ReportStatus.FAILED,
        }:
            raise ValueError("Open reports must have an active or transitional status")
        if self.state is ReportState.CLOSED and self.status is ReportStatus.ACTIVE:
            raise ValueError("Closed reports cannot remain active")
        if self.state is ReportState.CLOSED and not self.outcome:
            raise ValueError("Closed reports require an outcome summary")
        if self.state is ReportState.CLOSED and self.closed_at is None:
            raise ValueError("Closed reports require a closure timestamp")
        if self.state is ReportState.OPEN and self.closed_at is not None:
            raise ValueError("Open reports cannot have a closure timestamp")
        if self.state is ReportState.CLOSED and self.activity is not None:
            raise ValueError("Closed reports cannot retain an active operational activity")
        if self.status is ReportStatus.RESOLVED and not any(
            result.verdict is VerificationVerdict.PASSED for result in self.verifications
        ):
            raise ValueError("Resolved reports require passing verification")
        if any(relationship.target_report_id == self.id for relationship in self.relationships):
            raise ValueError("A report cannot relate to itself")
        evidence_ids = [item.id for item in self.evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("Evidence IDs must be unique within a report")
        known_evidence = set(evidence_ids)
        if any(
            evidence_id not in known_evidence
            for result in self.verifications
            for evidence_id in result.evidence_ids
        ):
            raise ValueError("Verification results may reference only report evidence")
        relationship_keys = [
            (item.target_report_id, item.relationship_type) for item in self.relationships
        ]
        if len(relationship_keys) != len(set(relationship_keys)):
            raise ValueError("Duplicate report relationships are not allowed")
        return self


class ReportChain(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=new_chain_id, min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=300)
    summary: str | None = Field(default=None, max_length=8000)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ReportSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    objective: str
    state: ReportState
    status: ReportStatus
    priority: ReportPriority
    updated_at: datetime
    purpose_tags: set[PurposeTag] = Field(default_factory=set)
    component_tags: set[ComponentTag] = Field(default_factory=set)
    primary_chain_id: str | None = None
    outcome: str | None = None


class ReportSearch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str | None = Field(default=None, max_length=300)
    state: ReportState | None = None
    status: ReportStatus | None = None
    priority: ReportPriority | None = None
    purpose_tag: PurposeTag | None = None
    component_tag: ComponentTag | None = None
    chain_id: str | None = Field(default=None, max_length=100)
    limit: int = Field(default=100, ge=1, le=1000)


class ReportCapsule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    objective: str
    state: ReportState
    status: ReportStatus
    priority: ReportPriority
    purpose_tags: set[PurposeTag]
    component_tags: set[ComponentTag]
    conclusion: str | None
    key_observations: list[str]
    hypotheses: list[str]
    strongest_evidence: list[str]
    latest_confidence: ConfidenceSnapshot | None
    verification: VerificationResult | None
    unresolved: list[str]
    related_report_ids: list[str]
    primary_chain_id: str | None
    updated_at: datetime
