"""Read-only storage attribution for Eden's shared reports/memory/database budget."""

from __future__ import annotations

import shutil
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from sys_eden.config import StorageSettings
from sys_eden.storage import Database

_PROTECTED_CONVERSATION = """
    c.pinned = 1 OR EXISTS (
        SELECT 1 FROM task_conversation_links work
        JOIN tasks t ON t.id = work.task_id
        WHERE work.conversation_id = c.id AND t.state NOT IN ('completed', 'failed', 'canceled')
    ) OR EXISTS (
        SELECT 1 FROM report_conversation_links links JOIN reports r ON r.id = links.report_id
        WHERE links.conversation_id = c.id AND (
            r.state = 'open' OR links.contribution_summary IS NULL
            OR links.contribution_through_sequence < c.last_message_sequence
            OR NOT EXISTS (
                SELECT 1 FROM conversation_retention_candidates review
                WHERE review.report_id = links.report_id AND review.conversation_id = c.id
                    AND review.eligible = 1
            )
        )
    )
"""


class StoragePressure(StrEnum):
    NORMAL = "normal"
    APPROACHING_BUDGET = "approaching_budget"
    OVER_BUDGET = "over_budget"
    RESERVE_BREACHED = "reserve_breached"


class StorageAttribution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    structured_reports: int = Field(ge=0)
    conversation_transcripts_full: int = Field(ge=0)
    conversation_records_compact: int = Field(ge=0)
    structured_memory: int = Field(ge=0)
    attachments: int = Field(ge=0)
    search_indexes_and_summaries: int = Field(ge=0)
    database_wal_and_overhead: int = Field(ge=0)
    protected: int = Field(ge=0)
    estimated_reclaimable: int = Field(ge=0)


class StorageCounts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reports: int = Field(ge=0)
    conversations_full: int = Field(ge=0)
    conversations_compact: int = Field(ge=0)
    conversations_deleted: int = Field(ge=0)
    pinned_conversations: int = Field(ge=0)
    active_report_links: int = Field(default=0, ge=0)
    closed_report_links: int = Field(default=0, ge=0)


class StorageConsumer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str
    object_id: str
    title: str
    estimated_bytes: int = Field(ge=0)
    protected: bool = False


class StorageStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data_directory: Path
    database_file_bytes: int = Field(ge=0)
    wal_file_bytes: int = Field(ge=0)
    shared_budget_bytes: int = Field(gt=0)
    shared_budget_remaining_bytes: int
    host_free_bytes: int = Field(ge=0)
    protected_free_space_reserve_bytes: int = Field(gt=0)
    pressure: StoragePressure
    attribution: StorageAttribution
    counts: StorageCounts
    largest_consumers: list[StorageConsumer]
    estimated: bool = True
    changed_data: bool = False
    notes: list[str]


class StorageRecommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    priority: int = Field(ge=1)
    action: str
    reason: str
    requires_confirmation: bool = True


class StorageStatusService:
    """Attribute logical payload and physical SQLite use without changing data."""

    def __init__(self, database: Database, settings: StorageSettings):
        self.database = database
        self.settings = settings

    def status(self) -> StorageStatus:
        database_bytes = self._size(self.database.path)
        wal_bytes = self._size(Path(f"{self.database.path}-wal"))
        shm_bytes = self._size(Path(f"{self.database.path}-shm"))
        physical_bytes = database_bytes + wal_bytes + shm_bytes
        with self.database.session() as session:
            reports = self._scalar(
                session,
                """
                SELECT COALESCE(SUM(
                    length(id) + length(title) + length(objective) +
                    length(COALESCE(trigger, '')) + length(COALESCE(summary, '')) +
                    length(COALESCE(outcome, ''))
                ), 0) FROM reports
                """,
            )
            report_children = sum(
                self._scalar(session, statement)
                for statement in (
                    "SELECT COALESCE(SUM(length(statement) + length(COALESCE(source, ''))), 0) FROM report_observations",
                    "SELECT COALESCE(SUM(length(statement) + length(COALESCE(rationale, ''))), 0) FROM report_hypotheses",
                    "SELECT COALESCE(SUM(length(summary) + length(source) + length(COALESCE(reference, ''))), 0) FROM report_evidence",
                    "SELECT COALESCE(SUM(length(COALESCE(rationale, ''))), 0) FROM report_confidence_history",
                    "SELECT COALESCE(SUM(length(summary) + length(success_criteria) + length(method)), 0) FROM report_verifications",
                    "SELECT COALESCE(SUM(length(COALESCE(contribution_summary, ''))), 0) FROM report_conversation_links",
                    "SELECT COALESCE(SUM(length(summary)), 0) FROM standalone_conversation_contributions",
                )
            )
            full_bytes = self._conversation_bytes(session, "full")
            compact_bytes = self._conversation_bytes(session, "compact")
            summaries = self._scalar(
                session,
                "SELECT COALESCE(SUM(length(COALESCE(rolling_summary, ''))), 0) FROM conversations",
            )
            protected = self._protected_conversation_bytes(session)
            reclaimable = self._reclaimable_conversation_bytes(session)
            counts = StorageCounts(
                active_report_links=self._scalar(session, "SELECT COUNT(*) FROM report_conversation_links l JOIN reports r ON r.id = l.report_id WHERE r.state = 'open'"),
                closed_report_links=self._scalar(session, "SELECT COUNT(*) FROM report_conversation_links l JOIN reports r ON r.id = l.report_id WHERE r.state = 'closed'"),
                reports=self._scalar(session, "SELECT COUNT(*) FROM reports"),
                conversations_full=self._conversation_count(session, "full"),
                conversations_compact=self._conversation_count(session, "compact"),
                conversations_deleted=self._conversation_count(session, "deleted"),
                pinned_conversations=self._scalar(
                    session, "SELECT COUNT(*) FROM conversations WHERE pinned = 1"
                ),
            )
            consumers = self._largest_consumers(session)
        attributed_payload = reports + report_children + full_bytes + compact_bytes + summaries
        overhead = max(physical_bytes - attributed_payload, 0)
        budget = int(self.settings.reports_memory_db_budget_gb * 1024**3)
        reserve = int(self.settings.free_space_reserve_gb * 1024**3)
        host_free = shutil.disk_usage(self.database.path.parent).free
        pressure = self._pressure(physical_bytes, budget, host_free, reserve)
        return StorageStatus(
            data_directory=self.database.path.parent,
            database_file_bytes=database_bytes,
            wal_file_bytes=wal_bytes,
            shared_budget_bytes=budget,
            shared_budget_remaining_bytes=budget - physical_bytes,
            host_free_bytes=host_free,
            protected_free_space_reserve_bytes=reserve,
            pressure=pressure,
            attribution=StorageAttribution(
                structured_reports=reports + report_children,
                conversation_transcripts_full=full_bytes,
                conversation_records_compact=compact_bytes,
                structured_memory=0,
                attachments=0,
                search_indexes_and_summaries=summaries,
                database_wal_and_overhead=overhead,
                protected=protected,
                estimated_reclaimable=reclaimable,
            ),
            counts=counts,
            largest_consumers=consumers,
            notes=[
                "Subcategory values estimate logical UTF-8 payload; SQLite page allocation is shared.",
                "Memory and attachment usage are zero until those repositories are implemented.",
                "Reclaimable space is advisory and no cleanup was performed.",
            ],
        )

    def recommendations(self) -> list[StorageRecommendation]:
        status = self.status()
        recommendations: list[StorageRecommendation] = []
        if status.attribution.estimated_reclaimable > 0:
            recommendations.append(
                StorageRecommendation(
                    priority=1,
                    action="Review eligible Full conversations for manual compaction.",
                    reason=(
                        f"Approximately {status.attribution.estimated_reclaimable} logical bytes "
                        "are potentially reclaimable after retention review."
                    ),
                )
            )
        if status.pressure is StoragePressure.RESERVE_BREACHED:
            recommendations.insert(
                0,
                StorageRecommendation(
                    priority=1,
                    action="Stop nonessential storage growth and restore host free space.",
                    reason="The configured host free-space reserve has been breached.",
                ),
            )
        elif status.pressure in {
            StoragePressure.APPROACHING_BUDGET,
            StoragePressure.OVER_BUDGET,
        }:
            recommendations.insert(
                0,
                StorageRecommendation(
                    priority=1,
                    action="Review replaceable exports, caches, and compaction candidates.",
                    reason=f"Shared storage pressure is {status.pressure.value}.",
                ),
            )
        return recommendations

    @staticmethod
    def _size(path: Path) -> int:
        try:
            return path.stat().st_size
        except FileNotFoundError:
            return 0

    @staticmethod
    def _scalar(session: Session, statement: str) -> int:
        value = session.execute(text(statement)).scalar_one()
        return int(value or 0)

    @classmethod
    def _conversation_bytes(cls, session: Session, state: str) -> int:
        statement = (
            "SELECT COALESCE(SUM(length(c.title) + "
            "COALESCE(messages.message_bytes, 0)), 0) FROM conversations c "
            "LEFT JOIN (SELECT conversation_id, SUM(length(content)) AS message_bytes "
            "FROM conversation_messages GROUP BY conversation_id) messages "
            "ON messages.conversation_id = c.id WHERE c.transcript_state = :state"
        )
        value = session.execute(text(statement), {"state": state}).scalar_one()
        return int(value or 0)

    @classmethod
    def _protected_conversation_bytes(cls, session: Session) -> int:
        statement = f"""
            SELECT COALESCE(SUM(length(c.title) + length(COALESCE(c.rolling_summary, '')) +
                COALESCE(messages.message_bytes, 0)), 0)
            FROM conversations c
            LEFT JOIN (
                SELECT conversation_id, SUM(length(content)) AS message_bytes
                FROM conversation_messages GROUP BY conversation_id
            ) messages ON messages.conversation_id = c.id
            WHERE c.transcript_state != 'deleted' AND ({_PROTECTED_CONVERSATION})
        """
        return cls._scalar(session, statement)

    @classmethod
    def _reclaimable_conversation_bytes(cls, session: Session) -> int:
        statement = f"""
            SELECT COALESCE(SUM(COALESCE(messages.message_bytes, 0)), 0)
            FROM conversations c
            LEFT JOIN (
                SELECT conversation_id, SUM(length(content)) AS message_bytes
                FROM conversation_messages GROUP BY conversation_id
            ) messages ON messages.conversation_id = c.id
            WHERE c.transcript_state = 'full' AND NOT ({_PROTECTED_CONVERSATION})
        """
        return cls._scalar(session, statement)

    @classmethod
    def _conversation_count(cls, session: Session, state: str) -> int:
        value = session.execute(
            text("SELECT COUNT(*) FROM conversations WHERE transcript_state = :state"),
            {"state": state},
        ).scalar_one()
        return int(value)

    @classmethod
    def _largest_consumers(cls, session: Session) -> list[StorageConsumer]:
        rows = session.execute(
            text(
                f"""
                SELECT c.id, c.title, CASE WHEN {_PROTECTED_CONVERSATION} THEN 1 ELSE 0 END AS protected,
                       length(c.title) + length(COALESCE(c.rolling_summary, '')) +
                       COALESCE(messages.message_bytes, 0) AS estimated_bytes
                FROM conversations c
                LEFT JOIN (
                    SELECT conversation_id, SUM(length(content)) AS message_bytes
                    FROM conversation_messages GROUP BY conversation_id
                ) messages ON messages.conversation_id = c.id
                ORDER BY estimated_bytes DESC, c.id
                LIMIT 10
                """
            )
        ).mappings()
        return [
            StorageConsumer(
                category="conversation",
                object_id=row["id"],
                title=row["title"],
                estimated_bytes=int(row["estimated_bytes"] or 0),
                protected=bool(row["protected"]),
            )
            for row in rows
        ]

    @staticmethod
    def _pressure(
        used: int, budget: int, host_free: int, reserve: int
    ) -> StoragePressure:
        if host_free < reserve:
            return StoragePressure.RESERVE_BREACHED
        if used > budget:
            return StoragePressure.OVER_BUDGET
        if used >= budget * 0.85:
            return StoragePressure.APPROACHING_BUDGET
        return StoragePressure.NORMAL
