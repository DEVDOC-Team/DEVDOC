"""Tests for InvestigationContext and CancellationToken."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from orchestrator.core.context import CancellationToken, InvestigationContext
from orchestrator.core.errors import ContextValidationError


def test_valid_context_initialization() -> None:
    inv_id = uuid.uuid4()
    inc_id = uuid.uuid4()
    proj_id = uuid.uuid4()
    user_id = uuid.uuid4()

    ctx = InvestigationContext(
        investigation_id=inv_id,
        incident_id=inc_id,
        project_id=proj_id,
        initiated_by_id=user_id,
    )

    assert ctx.investigation_id == inv_id
    assert ctx.incident_id == inc_id
    assert ctx.project_id == proj_id
    assert ctx.initiated_by_id == user_id
    assert isinstance(ctx.execution_id, uuid.UUID)
    assert ctx.current_stage is None
    assert ctx.warnings == []
    assert ctx.errors == []
    assert not ctx.is_cancelled()


def test_context_without_initiated_by_id() -> None:
    ctx = InvestigationContext(
        investigation_id=uuid.uuid4(),
        incident_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        initiated_by_id=None,
    )
    assert ctx.initiated_by_id is None


def test_invalid_investigation_id_rejected() -> None:
    with pytest.raises(ContextValidationError) as exc:
        InvestigationContext(
            investigation_id="not-a-uuid",  # type: ignore[arg-type]
            incident_id=uuid.uuid4(),
            project_id=uuid.uuid4(),
        )
    assert "investigation_id must be a valid UUID" in str(exc.value)


def test_invalid_incident_id_rejected() -> None:
    with pytest.raises(ContextValidationError) as exc:
        InvestigationContext(
            investigation_id=uuid.uuid4(),
            incident_id="not-a-uuid",  # type: ignore[arg-type]
            project_id=uuid.uuid4(),
        )
    assert "incident_id must be a valid UUID" in str(exc.value)


def test_invalid_project_id_rejected() -> None:
    with pytest.raises(ContextValidationError) as exc:
        InvestigationContext(
            investigation_id=uuid.uuid4(),
            incident_id=uuid.uuid4(),
            project_id="not-a-uuid",  # type: ignore[arg-type]
        )
    assert "project_id must be a valid UUID" in str(exc.value)


def test_secret_prevention_in_metadata() -> None:
    forbidden_keys = [
        "auth_token",
        "api_key",
        "password",
        "client_secret",
        "bearer_token",
        "private_key",
    ]
    for key in forbidden_keys:
        with pytest.raises(ContextValidationError) as exc:
            InvestigationContext(
                investigation_id=uuid.uuid4(),
                incident_id=uuid.uuid4(),
                project_id=uuid.uuid4(),
                execution_metadata={key: "sensitive_value_123"},
            )
        assert "Sensitive key" in str(exc.value)


def test_secret_prevention_in_nested_metadata() -> None:
    with pytest.raises(ContextValidationError) as exc:
        InvestigationContext(
            investigation_id=uuid.uuid4(),
            incident_id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            execution_metadata={"env": {"db": {"password": "root"}}},
        )
    assert "password" in str(exc.value).lower()


def test_secret_prevention_in_evidence_reference() -> None:
    ctx = InvestigationContext(
        investigation_id=uuid.uuid4(),
        incident_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
    )
    with pytest.raises(ContextValidationError):
        ctx.add_evidence_reference({"token": "secret_oauth_token"})


def test_secret_prevention_in_agent_output() -> None:
    ctx = InvestigationContext(
        investigation_id=uuid.uuid4(),
        incident_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
    )
    with pytest.raises(ContextValidationError):
        ctx.record_agent_output("agent_1", {"api_key": "my-secret-key"})


def test_stage_start_and_complete_lifecycle() -> None:
    ctx = InvestigationContext(
        investigation_id=uuid.uuid4(),
        incident_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
    )
    ctx.record_stage_start("initialize")
    assert ctx.current_stage == "initialize"
    assert "initialize_start" in ctx.execution_timestamps

    ctx.record_stage_complete("initialize")
    assert "initialize_end" in ctx.execution_timestamps


def test_warning_and_error_accumulation() -> None:
    ctx = InvestigationContext(
        investigation_id=uuid.uuid4(),
        incident_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
    )
    ctx.add_warning("High latency observed")
    ctx.add_warning("High latency observed")  # Duplicate ignored
    assert len(ctx.warnings) == 1
    assert ctx.warnings[0] == "High latency observed"

    ctx.add_error("Network timeout")
    ctx.add_error("Network timeout")  # Duplicate ignored
    assert len(ctx.errors) == 1
    assert ctx.errors[0] == "Network timeout"


def test_cancellation_token() -> None:
    token = CancellationToken()
    assert not token.is_cancelled
    assert token.reason is None

    token.cancel("User aborted investigation")
    assert token.is_cancelled
    assert token.reason == "User aborted investigation"


def test_context_cancellation_integration() -> None:
    ctx = InvestigationContext(
        investigation_id=uuid.uuid4(),
        incident_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
    )
    assert not ctx.is_cancelled()
    ctx.cancel("Emergency halt")
    assert ctx.is_cancelled()
    assert ctx.cancellation_token.reason == "Emergency halt"


def test_context_to_dict_serialization() -> None:
    inv_id = uuid.uuid4()
    inc_id = uuid.uuid4()
    proj_id = uuid.uuid4()
    ctx = InvestigationContext(
        investigation_id=inv_id,
        incident_id=inc_id,
        project_id=proj_id,
        execution_metadata={"env": "production_read_only"},
    )
    ctx.add_warning("Minor lag")
    ctx.add_evidence_reference("log_ref_001")
    ctx.record_agent_output("mock_agent", {"status": "ok"})

    data = ctx.to_dict()
    assert data["investigation_id"] == str(inv_id)
    assert data["incident_id"] == str(inc_id)
    assert data["project_id"] == str(proj_id)
    assert data["execution_metadata"]["env"] == "production_read_only"
    assert data["warnings"] == ["Minor lag"]
    assert data["collected_evidence_references"] == [{"reference_id": "log_ref_001"}]
    assert data["agent_outputs"]["mock_agent"] == {"status": "ok"}
    assert not data["is_cancelled"]
