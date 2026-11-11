from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from sys_eden.json_contract import (
    EdenJsonEnvelope,
    JsonAssociations,
    JsonError,
    JsonProvenance,
)


def test_stable_json_envelope_keeps_versions_associations_and_provenance_separate():
    envelope = EdenJsonEnvelope[dict[str, object]](
        type="inspection.result",
        data_version=2,
        status="success",
        request_id="REQ-1",
        generated_at=datetime(2026, 9, 25, tzinfo=UTC),
        associations=JsonAssociations(conversation_id="TMP-1", task_id="TSK-1"),
        provenance=JsonProvenance(synthetic=False, source="local_windows"),
        data={"duration": {"value": 3, "unit": "seconds"}},
    )
    payload = envelope.model_dump(mode="json")
    assert payload["eden_json"] == 1
    assert payload["data_version"] == 2
    assert payload["associations"]["task_id"] == "TSK-1"
    assert payload["provenance"]["synthetic"] is False


def test_json_error_uses_same_envelope_and_requires_structured_error():
    envelope = EdenJsonEnvelope[dict[str, object]](
        type="core.status",
        status="error",
        request_id="REQ-2",
        generated_at=datetime(2026, 9, 25, tzinfo=UTC),
        error=JsonError(code="core.unavailable", message="Core is stopped.", retryable=True),
    )
    assert envelope.error is not None
    with pytest.raises(ValidationError, match="requires an error"):
        EdenJsonEnvelope[dict[str, object]](
            type="core.status",
            status="error",
            request_id="REQ-3",
            generated_at=datetime(2026, 9, 25, tzinfo=UTC),
        )
