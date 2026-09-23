"""Transactional SQLite repository for canonical structured reports."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, cast

from sqlalchemy import text
from sqlalchemy.engine import CursorResult, RowMapping
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from sys_eden.report_models import (
    ComponentTag,
    ConfidenceSnapshot,
    EvidenceReference,
    HypothesisStatus,
    ObservationKind,
    PurposeTag,
    RelationshipType,
    Report,
    ReportActivity,
    ReportChain,
    ReportHypothesis,
    ReportObservation,
    ReportPriority,
    ReportRelationship,
    ReportSearch,
    ReportState,
    ReportStatus,
    ReportSummary,
    VerificationResult,
    VerificationVerdict,
    utc_now,
)
from sys_eden.storage import Database


class ReportRepositoryError(Exception):
    """Base error for report persistence operations."""


class ReportNotFound(ReportRepositoryError):
    """The requested report or chain does not exist."""


class ReportConflict(ReportRepositoryError):
    """The stored report changed or a uniqueness constraint was violated."""


def _timestamp(value: datetime) -> str:
    return value.isoformat()


def _datetime(value: str | datetime) -> datetime:
    return value if isinstance(value, datetime) else datetime.fromisoformat(value)


class ReportRepository:
    """Expose complete report aggregates while keeping SQLite canonical."""

    def __init__(self, database: Database):
        self.database = database

    def create_chain(self, chain: ReportChain) -> ReportChain:
        try:
            with self.database.session() as session:
                session.execute(
                    text(
                        """
                        INSERT INTO report_chains (id, title, summary, created_at, updated_at)
                        VALUES (:id, :title, :summary, :created_at, :updated_at)
                        """
                    ),
                    {
                        "id": chain.id,
                        "title": chain.title,
                        "summary": chain.summary,
                        "created_at": _timestamp(chain.created_at),
                        "updated_at": _timestamp(chain.updated_at),
                    },
                )
        except IntegrityError as error:
            raise ReportConflict(f"Report chain already exists: {chain.id}") from error
        return chain

    def get_chain(self, chain_id: str) -> ReportChain:
        with self.database.session() as session:
            row = (
                session.execute(
                    text("SELECT * FROM report_chains WHERE id = :id"), {"id": chain_id}
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise ReportNotFound(f"Report chain not found: {chain_id}")
        return ReportChain(
            id=row["id"],
            title=row["title"],
            summary=row["summary"],
            created_at=_datetime(row["created_at"]),
            updated_at=_datetime(row["updated_at"]),
        )

    def create(self, report: Report) -> Report:
        try:
            with self.database.session() as session:
                self._insert_report(session, report)
                self._insert_children(session, report)
        except IntegrityError as error:
            raise ReportConflict(f"Report could not be created: {report.id}") from error
        return report

    def update(self, report: Report) -> Report:
        """Replace one aggregate with optimistic revision checking."""
        values = report.model_dump(mode="python")
        values["revision"] = report.revision + 1
        values["updated_at"] = utc_now()
        revised = Report.model_validate(values)
        try:
            with self.database.session() as session:
                result = cast(
                    CursorResult[Any],
                    session.execute(
                        text(
                            """
                        UPDATE reports SET
                            schema_version = :schema_version,
                            revision = :new_revision,
                            title = :title,
                            objective = :objective,
                            state = :state,
                            status = :status,
                            priority = :priority,
                            activity = :activity,
                            trigger = :trigger,
                            summary = :summary,
                            outcome = :outcome,
                            updated_at = :updated_at,
                            closed_at = :closed_at,
                            primary_chain_id = :primary_chain_id
                        WHERE id = :id AND revision = :expected_revision
                            """
                        ),
                        {
                            **self._report_parameters(revised),
                            "new_revision": revised.revision,
                            "expected_revision": report.revision,
                        },
                    ),
                )
                if result.rowcount != 1:
                    raise ReportConflict(
                        f"Report revision changed or report is missing: {report.id}"
                    )
                self._delete_children(session, report.id)
                self._insert_children(session, revised)
        except IntegrityError as error:
            raise ReportConflict(
                f"Report update violated persistence constraints: {report.id}"
            ) from error
        return revised

    def get(self, report_id: str) -> Report:
        with self.database.session() as session:
            row = (
                session.execute(text("SELECT * FROM reports WHERE id = :id"), {"id": report_id})
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise ReportNotFound(f"Report not found: {report_id}")
            return self._load_report(session, row)

    def search(self, search: ReportSearch | None = None) -> list[ReportSummary]:
        search = search or ReportSearch()
        clauses: list[str] = []
        parameters: dict[str, object] = {"limit": search.limit}
        if search.query:
            clauses.append(
                "(r.title LIKE :query OR r.objective LIKE :query "
                "OR COALESCE(r.summary, '') LIKE :query OR COALESCE(r.outcome, '') LIKE :query)"
            )
            parameters["query"] = f"%{search.query}%"
        for name in ("state", "status", "priority"):
            value = getattr(search, name)
            if value is not None:
                clauses.append(f"r.{name} = :{name}")
                parameters[name] = value.value
        if search.chain_id:
            clauses.append("r.primary_chain_id = :chain_id")
            parameters["chain_id"] = search.chain_id
        if search.purpose_tag:
            clauses.append(
                "EXISTS (SELECT 1 FROM report_tags t WHERE t.report_id = r.id "
                "AND t.category = 'purpose' AND t.value = :purpose_tag)"
            )
            parameters["purpose_tag"] = search.purpose_tag.value
        if search.component_tag:
            clauses.append(
                "EXISTS (SELECT 1 FROM report_tags t WHERE t.report_id = r.id "
                "AND t.category = 'component' AND t.value = :component_tag)"
            )
            parameters["component_tag"] = search.component_tag.value
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        statement = text(
            f"""
            SELECT r.* FROM reports r
            {where}
            ORDER BY r.updated_at DESC, r.id
            LIMIT :limit
            """
        )
        with self.database.session() as session:
            rows = session.execute(statement, parameters).mappings().all()
            tags = self._load_tags(session, [row["id"] for row in rows])
        return [self._summary_from_row(row, tags.get(row["id"], {})) for row in rows]

    def _insert_report(self, session: Session, report: Report) -> None:
        session.execute(
            text(
                """
                INSERT INTO reports (
                    id, schema_version, revision, title, objective, state, status, priority,
                    activity, trigger, summary, outcome, created_at, updated_at, closed_at,
                    primary_chain_id
                ) VALUES (
                    :id, :schema_version, :revision, :title, :objective, :state, :status,
                    :priority, :activity, :trigger, :summary, :outcome, :created_at,
                    :updated_at, :closed_at, :primary_chain_id
                )
                """
            ),
            self._report_parameters(report),
        )

    @staticmethod
    def _report_parameters(report: Report) -> dict[str, object]:
        return {
            "id": report.id,
            "schema_version": report.schema_version,
            "revision": report.revision,
            "title": report.title,
            "objective": report.objective,
            "state": report.state.value,
            "status": report.status.value,
            "priority": report.priority.value,
            "activity": report.activity.value if report.activity else None,
            "trigger": report.trigger,
            "summary": report.summary,
            "outcome": report.outcome,
            "created_at": _timestamp(report.created_at),
            "updated_at": _timestamp(report.updated_at),
            "closed_at": _timestamp(report.closed_at) if report.closed_at else None,
            "primary_chain_id": report.primary_chain_id,
        }

    def _insert_children(self, session: Session, report: Report) -> None:
        tags = [
            {"report_id": report.id, "category": "purpose", "value": tag.value}
            for tag in sorted(report.purpose_tags)
        ] + [
            {"report_id": report.id, "category": "component", "value": tag.value}
            for tag in sorted(report.component_tags)
        ]
        self._execute_many(
            session,
            "INSERT INTO report_tags (report_id, category, value) "
            "VALUES (:report_id, :category, :value)",
            tags,
        )
        self._execute_many(
            session,
            """
            INSERT INTO report_observations
                (report_id, position, kind, statement, source, observed_at)
            VALUES (:report_id, :position, :kind, :statement, :source, :observed_at)
            """,
            [
                {
                    "report_id": report.id,
                    "position": position,
                    "kind": item.kind.value,
                    "statement": item.statement,
                    "source": item.source,
                    "observed_at": _timestamp(item.observed_at),
                }
                for position, item in enumerate(report.observations)
            ],
        )
        self._execute_many(
            session,
            """
            INSERT INTO report_hypotheses
                (report_id, position, statement, status, rationale, created_at)
            VALUES (:report_id, :position, :statement, :status, :rationale, :created_at)
            """,
            [
                {
                    "report_id": report.id,
                    "position": position,
                    "statement": item.statement,
                    "status": item.status.value,
                    "rationale": item.rationale,
                    "created_at": _timestamp(item.created_at),
                }
                for position, item in enumerate(report.hypotheses)
            ],
        )
        self._execute_many(
            session,
            """
            INSERT INTO report_evidence
                (id, report_id, position, evidence_type, source, summary, reference,
                 sensitivity, captured_at)
            VALUES (:id, :report_id, :position, :evidence_type, :source, :summary,
                    :reference, :sensitivity, :captured_at)
            """,
            [
                {
                    "id": item.id,
                    "report_id": report.id,
                    "position": position,
                    "evidence_type": item.evidence_type,
                    "source": item.source,
                    "summary": item.summary,
                    "reference": item.reference,
                    "sensitivity": item.sensitivity,
                    "captured_at": _timestamp(item.captured_at),
                }
                for position, item in enumerate(report.evidence)
            ],
        )
        self._execute_many(
            session,
            """
            INSERT INTO report_confidence_history
                (report_id, position, checkpoint, diagnostic, research, execution, safety,
                 overall, rationale, recorded_at)
            VALUES (:report_id, :position, :checkpoint, :diagnostic, :research, :execution,
                    :safety, :overall, :rationale, :recorded_at)
            """,
            [
                {
                    "report_id": report.id,
                    "position": position,
                    **item.model_dump(mode="python", exclude={"recorded_at"}),
                    "recorded_at": _timestamp(item.recorded_at),
                }
                for position, item in enumerate(report.confidence_history)
            ],
        )
        self._execute_many(
            session,
            """
            INSERT INTO report_verifications
                (report_id, position, success_criteria, method, verdict, summary,
                 evidence_ids_json, performed_at)
            VALUES (:report_id, :position, :success_criteria, :method, :verdict, :summary,
                    :evidence_ids_json, :performed_at)
            """,
            [
                {
                    "report_id": report.id,
                    "position": position,
                    "success_criteria": item.success_criteria,
                    "method": item.method,
                    "verdict": item.verdict.value,
                    "summary": item.summary,
                    "evidence_ids_json": json.dumps(item.evidence_ids),
                    "performed_at": _timestamp(item.performed_at),
                }
                for position, item in enumerate(report.verifications)
            ],
        )
        self._execute_many(
            session,
            """
            INSERT INTO report_relationships
                (source_report_id, target_report_id, relationship_type, created_at)
            VALUES (:source_report_id, :target_report_id, :relationship_type, :created_at)
            """,
            [
                {
                    "source_report_id": report.id,
                    "target_report_id": item.target_report_id,
                    "relationship_type": item.relationship_type.value,
                    "created_at": _timestamp(item.created_at),
                }
                for item in report.relationships
            ],
        )

    @staticmethod
    def _execute_many(
        session: Session, statement: str, parameters: Sequence[Mapping[str, Any]]
    ) -> None:
        if parameters:
            session.execute(text(statement), list(parameters))

    @staticmethod
    def _delete_children(session: Session, report_id: str) -> None:
        for table_name, field in (
            ("report_tags", "report_id"),
            ("report_observations", "report_id"),
            ("report_hypotheses", "report_id"),
            ("report_evidence", "report_id"),
            ("report_confidence_history", "report_id"),
            ("report_verifications", "report_id"),
            ("report_relationships", "source_report_id"),
        ):
            session.execute(
                text(f"DELETE FROM {table_name} WHERE {field} = :report_id"),
                {"report_id": report_id},
            )

    def _load_report(self, session: Session, row: RowMapping) -> Report:
        report_id = row["id"]
        tags = self._load_tags(session, [report_id]).get(report_id, {})
        observations = session.execute(
            text("SELECT * FROM report_observations WHERE report_id = :id ORDER BY position"),
            {"id": report_id},
        ).mappings()
        hypotheses = session.execute(
            text("SELECT * FROM report_hypotheses WHERE report_id = :id ORDER BY position"),
            {"id": report_id},
        ).mappings()
        evidence = session.execute(
            text("SELECT * FROM report_evidence WHERE report_id = :id ORDER BY position"),
            {"id": report_id},
        ).mappings()
        confidence = session.execute(
            text("SELECT * FROM report_confidence_history WHERE report_id = :id ORDER BY position"),
            {"id": report_id},
        ).mappings()
        verifications = session.execute(
            text("SELECT * FROM report_verifications WHERE report_id = :id ORDER BY position"),
            {"id": report_id},
        ).mappings()
        relationships = session.execute(
            text(
                "SELECT * FROM report_relationships "
                "WHERE source_report_id = :id ORDER BY created_at, id"
            ),
            {"id": report_id},
        ).mappings()
        return Report(
            id=report_id,
            schema_version=row["schema_version"],
            revision=row["revision"],
            title=row["title"],
            objective=row["objective"],
            state=ReportState(row["state"]),
            status=ReportStatus(row["status"]),
            priority=ReportPriority(row["priority"]),
            activity=ReportActivity(row["activity"]) if row["activity"] else None,
            trigger=row["trigger"],
            summary=row["summary"],
            outcome=row["outcome"],
            created_at=_datetime(row["created_at"]),
            updated_at=_datetime(row["updated_at"]),
            closed_at=_datetime(row["closed_at"]) if row["closed_at"] else None,
            primary_chain_id=row["primary_chain_id"],
            purpose_tags={PurposeTag(value) for value in tags.get("purpose", set())},
            component_tags={ComponentTag(value) for value in tags.get("component", set())},
            observations=[
                ReportObservation(
                    kind=ObservationKind(item["kind"]),
                    statement=item["statement"],
                    source=item["source"],
                    observed_at=_datetime(item["observed_at"]),
                )
                for item in observations
            ],
            hypotheses=[
                ReportHypothesis(
                    statement=item["statement"],
                    status=HypothesisStatus(item["status"]),
                    rationale=item["rationale"],
                    created_at=_datetime(item["created_at"]),
                )
                for item in hypotheses
            ],
            evidence=[
                EvidenceReference(
                    id=item["id"],
                    evidence_type=item["evidence_type"],
                    source=item["source"],
                    summary=item["summary"],
                    reference=item["reference"],
                    sensitivity=item["sensitivity"],
                    captured_at=_datetime(item["captured_at"]),
                )
                for item in evidence
            ],
            confidence_history=[
                ConfidenceSnapshot(
                    checkpoint=item["checkpoint"],
                    diagnostic=item["diagnostic"],
                    research=item["research"],
                    execution=item["execution"],
                    safety=item["safety"],
                    overall=item["overall"],
                    rationale=item["rationale"],
                    recorded_at=_datetime(item["recorded_at"]),
                )
                for item in confidence
            ],
            verifications=[
                VerificationResult(
                    success_criteria=item["success_criteria"],
                    method=item["method"],
                    verdict=VerificationVerdict(item["verdict"]),
                    summary=item["summary"],
                    evidence_ids=json.loads(item["evidence_ids_json"]),
                    performed_at=_datetime(item["performed_at"]),
                )
                for item in verifications
            ],
            relationships=[
                ReportRelationship(
                    target_report_id=item["target_report_id"],
                    relationship_type=RelationshipType(item["relationship_type"]),
                    created_at=_datetime(item["created_at"]),
                )
                for item in relationships
            ],
        )

    @staticmethod
    def _load_tags(session: Session, report_ids: Sequence[str]) -> dict[str, dict[str, set[str]]]:
        if not report_ids:
            return {}
        parameters = {f"id_{index}": report_id for index, report_id in enumerate(report_ids)}
        placeholders = ", ".join(f":id_{index}" for index in range(len(report_ids)))
        rows = session.execute(
            text(
                f"SELECT report_id, category, value FROM report_tags "
                f"WHERE report_id IN ({placeholders})"
            ),
            parameters,
        ).mappings()
        tags: dict[str, dict[str, set[str]]] = {}
        for row in rows:
            tags.setdefault(row["report_id"], {}).setdefault(row["category"], set()).add(
                row["value"]
            )
        return tags

    @staticmethod
    def _summary_from_row(row: RowMapping, tags: Mapping[str, set[str]]) -> ReportSummary:
        return ReportSummary(
            id=row["id"],
            title=row["title"],
            objective=row["objective"],
            state=ReportState(row["state"]),
            status=ReportStatus(row["status"]),
            priority=ReportPriority(row["priority"]),
            updated_at=_datetime(row["updated_at"]),
            purpose_tags={PurposeTag(value) for value in tags.get("purpose", set())},
            component_tags={ComponentTag(value) for value in tags.get("component", set())},
            primary_chain_id=row["primary_chain_id"],
            outcome=row["outcome"],
        )
