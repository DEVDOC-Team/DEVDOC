"""Phase 18 approval lifecycle tests using isolated SQLite persistence."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.approval import Approval, ApprovalDecision, ApprovalStatus
from app.models.approval_artifact import ApprovalArtifact
from app.models.audit_log import AuditLog
from app.models.fix_proposal import FixProposal as StoredFixProposal
from app.models.incident import Incident
from app.models.investigation import Investigation
from app.models.project import Project
from app.models.user import User
from app.schemas.approval import ApprovalDecisionInput, ApprovalRequestCreate
from app.services.approval import ApprovalService
from orchestrator.core.context import InvestigationContext
from orchestrator.fixes.models import (
    FixChange,
    FixProposal,
    FixProposalStatus,
    FixRisk,
    FixRiskCategory,
    FixRiskSeverity,
    FixRollbackStep,
    FixVerificationStep,
)
from orchestrator.llm.contracts import LLMObservability
from orchestrator.rca.models import (
    CandidateRootCause,
    EvidenceClassification,
    RCACategory,
    RCAConfidence,
    RCAEvidenceReference,
    RCAStatus,
    RootCauseAnalysis,
)
from orchestrator.sandbox.models import (
    SandboxVerificationResult,
    VerificationStatus,
    VerificationStepResult,
    VerificationStepStatus,
)

DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def db() -> AsyncGenerator[AsyncSession]:
    engine = create_async_engine(DB_URL)
    async with engine.begin() as connection:
        await connection.execute(text("PRAGMA foreign_keys = ON"))
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def entities(
    db: AsyncSession,
) -> tuple[User, Project, Incident, Investigation]:
    user = User(email=f"{uuid.uuid4()}@example.test")
    db.add(user)
    await db.flush()
    project = Project(name="Approval project", slug=f"approval-{uuid.uuid4().hex[:8]}", owner_id=user.id)
    db.add(project)
    await db.flush()
    incident = Incident(project_id=project.id, title="Elevated API errors")
    db.add(incident)
    await db.flush()
    investigation = Investigation(
        project_id=project.id,
        incident_id=incident.id,
        initiated_by_id=user.id,
    )
    db.add(investigation)
    await db.flush()
    return user, project, incident, investigation


def make_context(investigation: Investigation, project: Project, incident: Incident) -> InvestigationContext:
    evidence_id = uuid.uuid4()
    evidence = RCAEvidenceReference(
        evidence_id=evidence_id,
        classification=EvidenceClassification.FACT,
        source="application-log",
        evidence_type="log",
        timestamp=datetime.now(UTC),
        title="Repeated timeout",
        summary="Requests timed out after the configured value.",
    )
    candidate = CandidateRootCause(
        candidate_id=uuid.uuid4(),
        statement="The request timeout is too short.",
        category=RCACategory.CONFIGURATION,
        confidence=RCAConfidence.HIGH,
        rank=1,
        supporting_evidence=[evidence],
        contradicting_evidence=[],
        contributing_factors=[],
        triggering_events=[],
        observed_symptoms=[],
        temporal_relationship_ids=[],
        uncertainty="The cause is strongly supported by the observed logs.",
        rationale="Repeated timeout errors coincide with a short configured timeout.",
        ranking_basis="Direct evidence and temporal alignment.",
    )
    root_cause = RootCauseAnalysis(
        analysis_id=uuid.uuid4(),
        investigation_id=investigation.id,
        execution_id=uuid.uuid4(),
        status=RCAStatus.ROOT_CAUSE_IDENTIFIED,
        candidates=[candidate],
        selected_root_cause=candidate,
        confidence=RCAConfidence.HIGH,
        observed_facts=[evidence],
        reasoning_summary_evidence=[evidence],
        evidence_references=[evidence],
        contradictions=[],
        uncertainties=[],
        missing_information=[],
        reasoning_summary="The timeout configuration explains the observed failures.",
        analyzed_at=datetime.now(UTC),
    )
    proposal = FixProposal(
        proposal_id=uuid.uuid4(),
        investigation_id=investigation.id,
        execution_id=uuid.uuid4(),
        root_cause_reference=candidate.candidate_id,
        status=FixProposalStatus.REQUIRES_HUMAN_REVIEW,
        summary="Increase the request timeout.",
        rationale="The evidence supports a modest timeout increase.",
        affected_components=["api"],
        change_type="configuration_change",
        changes=[
            FixChange(
                target="request timeout",
                target_path="app/settings.py",
                operation="increase timeout",
                current_state="timeout = 30",
                proposed_state="timeout = 60",
                reason="The current value is below observed request duration.",
                evidence_references=[evidence_id],
            )
        ],
        prerequisites=[],
        risks=[
            FixRisk(
                category=FixRiskCategory.PERFORMANCE,
                severity=FixRiskSeverity.LOW,
                description="Longer requests may hold connections for longer.",
                mitigation="Monitor connection utilization after deployment.",
            )
        ],
        verification_plan=[
            FixVerificationStep(
                description="Run API tests.",
                expected_result="CHECKS_OK",
                evidence_required=["test output"],
            )
        ],
        rollback_plan=[
            FixRollbackStep(
                description="Restore the previous timeout.",
                trigger="Request latency or connection usage regresses.",
                expected_result="The timeout is reset to 30 seconds.",
            )
        ],
        evidence_references=[evidence_id],
        external_knowledge_references=[],
        confidence=0.9,
        change_scope="One API setting.",
        generated_at=datetime.now(UTC),
        model_metadata=LLMObservability(
            model="test-model",
            duration_ms=1,
            attempts=1,
            input_tokens=0,
            output_tokens=0,
            estimated_cost_usd=0,
            budget_remaining_usd=1,
        ),
    )
    verification = SandboxVerificationResult(
        verification_id=uuid.uuid4(),
        investigation_id=investigation.id,
        proposal_id=proposal.proposal_id,
        status=VerificationStatus.PASSED,
        started_at=datetime.now(UTC) - timedelta(seconds=1),
        completed_at=datetime.now(UTC),
        verification_steps=[
            VerificationStepResult(
                step_id="step-0",
                description="Run API tests.",
                status=VerificationStepStatus.PASSED,
                exit_code=0,
                duration_ms=20,
                stdout="CHECKS_OK",
                expected_result="CHECKS_OK",
                observed_result="CHECKS_OK",
            )
        ],
        passed_steps=1,
        failed_steps=0,
        logs="CHECKS_OK",
        cleanup_status="complete",
        summary="All configured verification checks passed.",
    )
    return InvestigationContext(
        investigation_id=investigation.id,
        incident_id=incident.id,
        project_id=project.id,
        initiated_by_id=investigation.initiated_by_id,
        root_cause_analysis=root_cause,
        fix_proposal=proposal,
        sandbox_verification_result=verification,
    )


async def record_bundle(
    db: AsyncSession,
    entities: tuple[User, Project, Incident, Investigation],
    *,
    verification_status: VerificationStatus = VerificationStatus.PASSED,
    rca_status: RCAStatus = RCAStatus.ROOT_CAUSE_IDENTIFIED,
) -> tuple[InvestigationContext, uuid.UUID]:
    _, project, incident, investigation = entities
    context = make_context(investigation, project, incident)
    if context.sandbox_verification_result is not None:
        context.sandbox_verification_result = context.sandbox_verification_result.model_copy(
            update={"status": verification_status}
        )
    if context.root_cause_analysis is not None:
        context.root_cause_analysis = context.root_cause_analysis.model_copy(
            update={"status": rca_status}
        )
    artifact_id = await ApprovalService.record_verified_artifact(db, context)
    return context, artifact_id


@pytest.mark.asyncio
async def test_server_recorded_bundle_creates_reviewable_request_and_audit(
    db: AsyncSession,
    entities: tuple[User, Project, Incident, Investigation],
) -> None:
    user, project, _, investigation = entities
    context, artifact_id = await record_bundle(db, entities)
    proposal = context.fix_proposal
    assert proposal is not None

    request = await ApprovalService.create_request(
        db, project, investigation.id, proposal.proposal_id, user, "req-123"
    )

    assert request.status == ApprovalStatus.PENDING
    assert request.requested_by_id == user.id
    assert request.approver_id is None
    assert request.verification_id == artifact_id
    assert request.review is not None
    assert request.review.proposal.proposal_id == proposal.proposal_id
    assert request.review.verification.status == VerificationStatus.PASSED
    assert request.proposal_fingerprint is not None
    assert request.verification_fingerprint is not None
    assert request.expires_at is not None
    assert "stdout" not in request.review.verification.model_dump()
    assert "logs" not in request.review.verification.model_dump()
    events = list((await db.scalars(select(AuditLog))).all())
    assert [event.action for event in events] == ["approval.requested"]
    assert events[0].actor_id == user.id
    assert events[0].session_id == "req-123"


@pytest.mark.asyncio
async def test_only_passed_verification_and_supported_rca_can_be_requested(
    db: AsyncSession,
    entities: tuple[User, Project, Incident, Investigation],
) -> None:
    user, project, _, investigation = entities
    context, _ = await record_bundle(
        db, entities, verification_status=VerificationStatus.INCONCLUSIVE
    )
    proposal = context.fix_proposal
    assert proposal is not None
    with pytest.raises(HTTPException) as verification_error:
        await ApprovalService.create_request(
            db, project, investigation.id, proposal.proposal_id, user, None
        )
    assert verification_error.value.status_code == 409
    assert "must pass" in verification_error.value.detail

    context, _ = await record_bundle(
        db, entities, rca_status=RCAStatus.INSUFFICIENT_EVIDENCE
    )
    proposal = context.fix_proposal
    assert proposal is not None
    with pytest.raises(HTTPException) as rca_error:
        await ApprovalService.create_request(
            db, project, investigation.id, proposal.proposal_id, user, None
        )
    assert rca_error.value.status_code == 409
    assert "supported" in rca_error.value.detail


@pytest.mark.asyncio
async def test_approve_is_human_attributed_and_terminal_replay_is_rejected(
    db: AsyncSession,
    entities: tuple[User, Project, Incident, Investigation],
) -> None:
    user, project, _, investigation = entities
    context, _ = await record_bundle(db, entities)
    proposal = context.fix_proposal
    assert proposal is not None
    request = await ApprovalService.create_request(
        db, project, investigation.id, proposal.proposal_id, user, None
    )

    approved = await ApprovalService.approve(
        db,
        project,
        investigation.id,
        request.id,
        user,
        "Reviewed the exact patch and verification.",
        None,
    )
    assert approved.status == ApprovalStatus.APPROVED
    assert approved.approver_id == user.id
    assert approved.decision == ApprovalDecision.APPROVED
    assert approved.decided_at is not None
    events = list((await db.scalars(select(AuditLog))).all())
    assert [event.action for event in events] == ["approval.requested", "approval.approved"]

    with pytest.raises(HTTPException) as replay:
        await ApprovalService.reject(
            db, project, investigation.id, request.id, user, "Do not approve this.", None
        )
    assert replay.value.status_code == 409
    assert await db.scalar(select(Approval).where(Approval.id == request.id)) is not None


@pytest.mark.asyncio
async def test_rejection_requires_reason_and_cancel_is_pending_only(
    db: AsyncSession,
    entities: tuple[User, Project, Incident, Investigation],
) -> None:
    user, project, _, investigation = entities
    context, _ = await record_bundle(db, entities)
    proposal = context.fix_proposal
    assert proposal is not None
    request = await ApprovalService.create_request(
        db, project, investigation.id, proposal.proposal_id, user, None
    )
    rejected = await ApprovalService.reject(
        db, project, investigation.id, request.id, user, "Risk is too high; changes required.", None
    )
    assert rejected.status == ApprovalStatus.REJECTED
    assert rejected.decision == ApprovalDecision.REJECTED

    with pytest.raises(ValueError):
        ApprovalDecisionInput(reason=" no ")

    context, _ = await record_bundle(db, entities)
    next_proposal = context.fix_proposal
    assert next_proposal is not None
    pending = await ApprovalService.create_request(
        db, project, investigation.id, next_proposal.proposal_id, user, None
    )
    cancelled = await ApprovalService.cancel(
        db, project, investigation.id, pending.id, user, "Requester withdrew the review.", None
    )
    assert cancelled.status == ApprovalStatus.CANCELLED


@pytest.mark.asyncio
async def test_expired_request_and_modified_proposal_cannot_be_approved(
    db: AsyncSession,
    entities: tuple[User, Project, Incident, Investigation],
) -> None:
    user, project, _, investigation = entities
    context, _ = await record_bundle(db, entities)
    proposal = context.fix_proposal
    assert proposal is not None
    request = await ApprovalService.create_request(
        db, project, investigation.id, proposal.proposal_id, user, None
    )
    stored_request = await db.get(Approval, request.id)
    assert stored_request is not None
    stored_request.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    expired = await ApprovalService.approve(
        db, project, investigation.id, request.id, user, "Attempt to approve late.", None
    )
    assert expired.status == ApprovalStatus.EXPIRED
    assert expired.decision is None

    context, _ = await record_bundle(db, entities)
    changed_proposal = context.fix_proposal
    assert changed_proposal is not None
    fresh_request = await ApprovalService.create_request(
        db, project, investigation.id, changed_proposal.proposal_id, user, None
    )
    stored_proposal = await db.get(StoredFixProposal, changed_proposal.proposal_id)
    assert stored_proposal is not None
    stored_proposal.description = "Someone changed the proposal after verification."
    stale = await ApprovalService.approve(
        db,
        project,
        investigation.id,
        fresh_request.id,
        user,
        "Reviewed the original change.",
        None,
    )
    assert stale.status == ApprovalStatus.SUPERSEDED
    assert stale.decision is None


@pytest.mark.asyncio
async def test_client_cannot_supply_approval_actor_fields() -> None:
    with pytest.raises(ValueError):
        ApprovalRequestCreate.model_validate(
            {"proposal_id": str(uuid.uuid4()), "requested_by_id": str(uuid.uuid4())}
        )
    with pytest.raises(ValueError):
        ApprovalDecisionInput.model_validate(
            {"reason": "Approve the change.", "approver_id": str(uuid.uuid4())}
        )


@pytest.mark.asyncio
async def test_artifact_rows_are_immutable(
    db: AsyncSession,
    entities: tuple[User, Project, Incident, Investigation],
) -> None:
    _, artifact_id = await record_bundle(db, entities)
    artifact = await db.get(ApprovalArtifact, artifact_id)
    assert artifact is not None
    artifact.proposal_snapshot = "{}"
    with pytest.raises(ValueError, match="immutable"):
        await db.flush()


@pytest.mark.asyncio
async def test_audit_rows_are_immutable(db: AsyncSession) -> None:
    event = AuditLog(
        id=uuid.uuid4(),
        action="approval.test",
        entity_type="approval",
        entity_id=uuid.uuid4(),
        description="Test audit event",
        outcome="success",
    )
    db.add(event)
    await db.flush()
    event.description = "Attempted mutation"
    with pytest.raises(ValueError, match="immutable"):
        await db.flush()


@pytest.mark.asyncio
async def test_project_access_and_investigation_boundaries(
    db: AsyncSession,
    entities: tuple[User, Project, Incident, Investigation],
) -> None:
    user, project, _, investigation = entities
    other_user = User(email=f"{uuid.uuid4()}@example.test")
    db.add(other_user)
    await db.flush()
    context, _ = await record_bundle(db, entities)
    proposal = context.fix_proposal
    assert proposal is not None

    with pytest.raises(HTTPException) as forbidden:
        await ApprovalService.create_request(
            db, project, investigation.id, proposal.proposal_id, other_user, None
        )
    assert forbidden.value.status_code == 403

    with pytest.raises(HTTPException) as cross_investigation:
        await ApprovalService.create_request(
            db, project, uuid.uuid4(), proposal.proposal_id, user, None
        )
    assert cross_investigation.value.status_code == 404


@pytest.mark.asyncio
async def test_duplicate_pending_request_is_rejected_by_service_and_database(
    db: AsyncSession,
    entities: tuple[User, Project, Incident, Investigation],
) -> None:
    user, project, _, investigation = entities
    context, _ = await record_bundle(db, entities)
    proposal = context.fix_proposal
    assert proposal is not None
    await ApprovalService.create_request(db, project, investigation.id, proposal.proposal_id, user, None)

    with pytest.raises(HTTPException) as conflict:
        await ApprovalService.create_request(
            db, project, investigation.id, proposal.proposal_id, user, None
        )
    assert conflict.value.status_code == 409

    second_pending = Approval(
        id=uuid.uuid4(),
        fix_proposal_id=proposal.proposal_id,
        requested_by_id=user.id,
        verification_id=context.sandbox_verification_result.verification_id,
        status=ApprovalStatus.PENDING,
        proposal_fingerprint="a" * 64,
        verification_fingerprint="b" * 64,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db.add(second_pending)
    with pytest.raises(IntegrityError):
        await db.flush()
