import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from sys_eden.cli import app
from sys_eden.report_models import (
    ComponentTag,
    ConfidenceSnapshot,
    EvidenceReference,
    HypothesisStatus,
    ObservationKind,
    PurposeTag,
    RelationshipType,
    Report,
    ReportChain,
    ReportHypothesis,
    ReportObservation,
    ReportPriority,
    ReportRelationship,
    ReportSearch,
    ReportState,
    ReportStatus,
    VerificationResult,
    VerificationVerdict,
)
from sys_eden.report_repository import ReportConflict, ReportNotFound, ReportRepository
from sys_eden.report_views import build_capsule, render_report
from sys_eden.storage import Database


@pytest.fixture
def report_store(tmp_path: Path):
    database = Database(tmp_path / "eden.db")
    database.initialize()
    try:
        yield database, ReportRepository(database)
    finally:
        database.close()


def sample_report(*, report_id: str = "rpt-synthetic", chain_id: str | None = None) -> Report:
    evidence = EvidenceReference(
        id=f"evd-{report_id}",
        evidence_type="event_log",
        source="local fixture",
        summary="The application crashed three times after the configuration change.",
        reference="fixture://events/1",
    )
    return Report(
        id=report_id,
        title="Synthetic Application Crash Investigation",
        objective="Determine why the fixture application repeatedly crashes.",
        trigger="Synthetic troubleshooting acceptance test.",
        summary="A configuration mismatch is the leading explanation.",
        priority=ReportPriority.HIGH,
        primary_chain_id=chain_id,
        purpose_tags={PurposeTag.PROBLEM},
        component_tags={ComponentTag.SOFTWARE, ComponentTag.OS},
        observations=[
            ReportObservation(
                kind=ObservationKind.OBSERVED_FACT,
                statement="Three crash events share the same fault signature.",
                source="fixture event log",
            ),
            ReportObservation(
                kind=ObservationKind.UNKNOWN,
                statement="Long-term stability has not yet been observed.",
            ),
        ],
        hypotheses=[
            ReportHypothesis(
                statement="The application configuration is incompatible with the new version.",
                status=HypothesisStatus.SUPPORTED,
                rationale="The crash began after the version and configuration changed together.",
            )
        ],
        evidence=[evidence],
        confidence_history=[
            ConfidenceSnapshot(
                checkpoint="pre_plan",
                diagnostic=0.82,
                research=0.60,
                execution=0.95,
                safety=0.98,
                overall=0.80,
                rationale="The fixture evidence is consistent but deliberately limited.",
            )
        ],
    )


def close_resolved(report: Report) -> Report:
    values = report.model_dump(mode="python")
    values.update(
        {
            "state": ReportState.CLOSED,
            "status": ReportStatus.RESOLVED,
            "activity": None,
            "outcome": "The fixture configuration was corrected and the crash no longer reproduces.",
            "closed_at": datetime.now(UTC),
            "verifications": [
                VerificationResult(
                    success_criteria="The fixture application completes three launches without a crash.",
                    method="Deterministic fixture launch check",
                    verdict=VerificationVerdict.PASSED,
                    summary="Three launches completed successfully.",
                    evidence_ids=[report.evidence[0].id],
                )
            ],
        }
    )
    return Report.model_validate(values)


def test_report_round_trip_close_capsule_and_human_view(report_store):
    _, repository = report_store
    chain = repository.create_chain(ReportChain(id="chn-crashes", title="Recurring crashes"))
    created = repository.create(sample_report(chain_id=chain.id))
    closed = repository.update(close_resolved(created))

    loaded = repository.get(created.id)
    assert loaded == closed
    assert loaded.revision == 2
    assert loaded.status is ReportStatus.RESOLVED
    assert loaded.primary_chain_id == chain.id
    assert loaded.verifications[0].verdict is VerificationVerdict.PASSED
    assert loaded.evidence[0].reference == "fixture://events/1"

    capsule = build_capsule(loaded)
    assert capsule.conclusion == loaded.outcome
    assert capsule.latest_confidence is not None
    assert capsule.verification is not None
    assert "Synthetic Application Crash Investigation" in render_report(loaded)
    assert "Three launches completed successfully" in render_report(loaded)


def test_resolved_report_requires_passing_verification():
    report = sample_report()
    values = report.model_dump(mode="python")
    values.update(
        {
            "state": ReportState.CLOSED,
            "status": ReportStatus.RESOLVED,
            "activity": None,
            "outcome": "Claimed success without evidence.",
            "closed_at": datetime.now(UTC),
        }
    )
    with pytest.raises(ValidationError, match="passing verification"):
        Report.model_validate(values)


def test_search_filters_metadata_without_loading_full_report(report_store):
    _, repository = report_store
    repository.create(sample_report(report_id="rpt-match"))
    repository.create(
        Report(
            id="rpt-other",
            title="Storage Research",
            objective="Compare storage options.",
            purpose_tags={PurposeTag.RESEARCH},
            component_tags={ComponentTag.STORAGE},
        )
    )

    result = repository.search(
        ReportSearch(
            query="crash",
            state=ReportState.OPEN,
            purpose_tag=PurposeTag.PROBLEM,
            component_tag=ComponentTag.SOFTWARE,
        )
    )
    assert [item.id for item in result] == ["rpt-match"]
    assert result[0].priority is ReportPriority.HIGH
    assert result[0].purpose_tags == {PurposeTag.PROBLEM}


def test_relationships_require_real_reports_and_round_trip(report_store):
    _, repository = report_store
    repository.create(sample_report(report_id="rpt-earlier"))
    later = sample_report(report_id="rpt-later")
    values = later.model_dump(mode="python")
    values["relationships"] = [
        ReportRelationship(
            target_report_id="rpt-earlier",
            relationship_type=RelationshipType.PREVIOUS_ATTEMPT,
        )
    ]
    repository.create(Report.model_validate(values))
    loaded = repository.get("rpt-later")
    assert loaded.relationships[0].target_report_id == "rpt-earlier"

    invalid = sample_report(report_id="rpt-invalid")
    invalid_values = invalid.model_dump(mode="python")
    invalid_values["relationships"] = [
        ReportRelationship(
            target_report_id="rpt-missing",
            relationship_type=RelationshipType.RELATED_TO,
        )
    ]
    with pytest.raises(ReportConflict):
        repository.create(Report.model_validate(invalid_values))
    with pytest.raises(ReportNotFound):
        repository.get("rpt-invalid")


def test_optimistic_revision_conflict_preserves_newer_report(report_store):
    _, repository = report_store
    stale = repository.create(sample_report())
    first_values = stale.model_dump(mode="python")
    first_values["summary"] = "First update wins."
    first = repository.update(Report.model_validate(first_values))

    stale_values = stale.model_dump(mode="python")
    stale_values["summary"] = "Stale update must not overwrite."
    with pytest.raises(ReportConflict):
        repository.update(Report.model_validate(stale_values))
    assert repository.get(stale.id).summary == first.summary


def test_report_cli_list_show_capsule_and_export(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    data_directory = tmp_path / "data"
    monkeypatch.setenv("EDEN_DATA_DIRECTORY", str(data_directory))
    database = Database(data_directory / "eden.db")
    database.initialize()
    try:
        ReportRepository(database).create(sample_report())
    finally:
        database.close()

    runner = CliRunner()
    listed = runner.invoke(app, ["report", "list", "--component", "software", "--json"])
    assert listed.exit_code == 0, listed.output
    assert json.loads(listed.stdout)[0]["id"] == "rpt-synthetic"

    shown = runner.invoke(app, ["report", "show", "rpt-synthetic"])
    assert shown.exit_code == 0, shown.output
    assert "Synthetic Application Crash Investigation" in shown.stdout

    capsule = runner.invoke(app, ["report", "show", "rpt-synthetic", "--capsule"])
    assert capsule.exit_code == 0, capsule.output
    assert json.loads(capsule.stdout)["id"] == "rpt-synthetic"

    export_path = tmp_path / "report.json"
    exported = runner.invoke(
        app, ["report", "export", "rpt-synthetic", "--output", str(export_path)]
    )
    assert exported.exit_code == 0, exported.output
    assert json.loads(export_path.read_text(encoding="utf-8"))["id"] == "rpt-synthetic"
    refused = runner.invoke(
        app, ["report", "export", "rpt-synthetic", "--output", str(export_path)]
    )
    assert refused.exit_code == 1
    assert "Refusing to overwrite" in refused.output
