"""End-to-End Golden Path Test for DEVDOC Autonomous Investigation & Human Approval.

Verifies:
1. End-to-end investigation run lifecycle: PENDING -> RUNNING -> COMPLETED.
2. Persistence of normalized evidence, root cause analysis, fix proposal, and approval artifact.
3. Cryptographic review fingerprinting and integrity.
4. Seamless integration with Phase 18 Human Approval API.
5. Strict preservation of human approval boundary (never auto-approves or auto-deploys).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.db.base import Base
from app.dependencies import get_db
from app.main import app
from app.models.approval import Approval, ApprovalStatus
from app.models.approval_artifact import ApprovalArtifact
from app.models.evidence import Evidence as StoredEvidence
from app.models.evidence import EvidenceKind
from app.models.fix_proposal import FixProposal as StoredFixProposal
from app.models.fix_proposal import FixStatus
from app.models.investigation import Investigation, InvestigationStatus
from app.services.investigation import InvestigationService
from orchestrator.contracts.execution import FailurePolicy, WorkflowDefinition
from orchestrator.contracts.stage import BaseStage
from orchestrator.core.context import InvestigationContext
from orchestrator.core.orchestrator import DEVDOCOrchestrator
from orchestrator.core.result import ExecutionStatus, StageResult
from orchestrator.evidence.models import (
    Evidence as OrchestratorEvidence,
)
from orchestrator.evidence.models import (
    EvidenceCollection,
    EvidenceProvenance,
    EvidenceQuality,
    EvidenceSource,
    EvidenceSummary,
    EvidenceType,
    SourceReliability,
    TimestampType,
    ValidationStatus,
)
from orchestrator.fixes.models import (
    FixChange,
    FixChangeType,
    FixProposalStatus,
    FixRisk,
    FixRiskCategory,
    FixRiskSeverity,
    FixRollbackStep,
    FixVerificationStep,
)
from orchestrator.fixes.models import (
    FixProposal as OrchestratorFixProposal,
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
from orchestrator.stages.registry import StageRegistry

SQLITE_TEST_URL = "sqlite+aiosqlite:///:memory:"
TEST_SECRET = "devdoc-e2e-secret-key-32-chars-ok!!"
TEST_SETTINGS = Settings(
    _env_file=None,
    environment="test",
    supabase_jwt_secret=TEST_SECRET,
    supabase_jwt_algorithm="HS256",
    supabase_jwt_audience="authenticated",
    database_url=SQLITE_TEST_URL,
    direct_database_url=SQLITE_TEST_URL,
)


def make_test_token(sub: str, email: str | None = None) -> str:
    import jwt
    payload = {
        "sub": sub,
        "email": email or f"user-{sub}@devdoc.io",
        "aud": "authenticated",
        "exp": int(datetime.now(UTC).timestamp()) + 3600,
        "iat": int(datetime.now(UTC).timestamp()),
        "role": "authenticated",
        "user_metadata": {"full_name": "E2E Test User"},
    }
    return jwt.encode(payload, TEST_SECRET, algorithm="HS256")


class E2EFullStage(BaseStage):
    """Stage that generates complete pipeline outputs matching operational contracts."""

    @property
    def stage_id(self) -> str:
        return "e2e_full_stage"

    @property
    def name(self) -> str:
        return "E2E Full Pipeline Stage"

    @property
    def description(self) -> str:
        return "Populates context with verified evidence, RCA, Fix, and Sandbox result."

    async def execute(self, context: InvestigationContext) -> StageResult:
        now = datetime.now(UTC)
        ev_id = uuid.uuid4()
        ev = OrchestratorEvidence(
            investigation_id=context.investigation_id,
            execution_id=context.execution_id,
            evidence_id=ev_id,
            source="docker",
            source_type=EvidenceSource.DOCKER,
            evidence_type=EvidenceType.CONTAINER_LOG,
            timestamp=now,
            title="Postgres connection slot exhaustion",
            summary="FATAL: remaining connection slots are reserved (error 53300)",
            provenance=EvidenceProvenance(agent_id="docker_inspector", source="docker", collected_at=now),
            quality=EvidenceQuality(source_reliability=SourceReliability.HIGH, quality_score=0.95),
            correlation_identifiers=["postgres", "pool_leak"],
            data={"container": "payment-db", "error": "53300"},
        )
        context.evidence_collection = EvidenceCollection(
            investigation_id=context.investigation_id,
            execution_id=context.execution_id,
            items=[ev],
            summary=EvidenceSummary(total_evidence_count=1),
        )

        cand_id = uuid.uuid4()
        ev_ref = RCAEvidenceReference(
            evidence_id=ev_id,
            classification=EvidenceClassification.FACT,
            source="docker",
            evidence_type="container_log",
            timestamp=now,
            title="Connection slot exhaustion",
            summary="Postgres pool leak",
        )
        candidate = CandidateRootCause(
            candidate_id=cand_id,
            statement="Database connection leak in PaymentService checkout handler",
            category=RCACategory.RESOURCE_EXHAUSTION,
            confidence=RCAConfidence.HIGH,
            rank=1,
            supporting_evidence=[ev_ref],
            contradicting_evidence=[],
            contributing_factors=[],
            triggering_events=[],
            observed_symptoms=[],
            temporal_relationship_ids=[],
            uncertainty="Minimal",
            rationale="Idle checkout sessions held unreleased connections",
            ranking_basis="Direct correlate with PostgreSQL 53300 log",
        )
        rca = RootCauseAnalysis(
            analysis_id=uuid.uuid4(),
            investigation_id=context.investigation_id,
            execution_id=context.execution_id,
            status=RCAStatus.ROOT_CAUSE_IDENTIFIED,
            candidates=[candidate],
            selected_root_cause=candidate,
            confidence=RCAConfidence.HIGH,
            observed_facts=[ev_ref],
            reasoning_summary_evidence=[ev_ref],
            evidence_references=[ev_ref],
            contradictions=[],
            uncertainties=[],
            missing_information=[],
            reasoning_summary="Checkout workers leaked database connections upon HTTP errors.",
            analyzed_at=now,
            model_metadata=LLMObservability(
                model="nvidia/Nemotron-3_5-Lightning",
                duration_ms=250.0,
                attempts=1,
                input_tokens=350,
                output_tokens=180,
                estimated_cost_usd=0.0001,
                budget_remaining_usd=9.99,
            ),
        )
        context.root_cause_analysis = rca

        fix = OrchestratorFixProposal(
            proposal_id=uuid.uuid4(),
            investigation_id=context.investigation_id,
            execution_id=context.execution_id,
            root_cause_reference=cand_id,
            status=FixProposalStatus.PROPOSED,
            summary="Wrap checkout database session in asynchronous context manager",
            rationale="Guarantees connection release back to pool on request completion or failure",
            affected_components=["app/services/checkout.py"],
            change_type=FixChangeType.CODE_CHANGE,
            changes=[
                FixChange(
                    target="checkout.py",
                    target_path="app/services/checkout.py",
                    operation="modify",
                    proposed_diff="@@ -10,2 +10,4 @@\n+async with get_db() as session:\n",
                    reason="Deterministic pool return",
                    evidence_references=[ev_id],
                )
            ],
            prerequisites=[],
            risks=[
                FixRisk(
                    category=FixRiskCategory.PERFORMANCE,
                    severity=FixRiskSeverity.LOW,
                    description="Minor timeout overhead",
                    mitigation="Tuned pool timeout to 5.0s",
                )
            ],
            verification_plan=[
                FixVerificationStep(
                    description="Run concurrency regression benchmark",
                    expected_result="Zero connection leak",
                    evidence_required=["pool_active_connections"],
                )
            ],
            rollback_plan=[
                FixRollbackStep(
                    description="Revert commit",
                    trigger="Error rate spike",
                    expected_result="Original session handling restored",
                )
            ],
            evidence_references=[ev_id],
            external_knowledge_references=[],
            confidence=0.95,
            change_scope="Checkout handler",
            human_approval_required=True,
            generated_at=now,
            model_metadata=LLMObservability(
                model="nvidia/Nemotron-3_5-Lightning",
                duration_ms=300.0,
                attempts=1,
                input_tokens=450,
                output_tokens=220,
                estimated_cost_usd=0.00015,
                budget_remaining_usd=9.98,
            ),
        )
        context.fix_proposal = fix

        verif = SandboxVerificationResult(
            verification_id=uuid.uuid4(),
            investigation_id=context.investigation_id,
            proposal_id=fix.proposal_id,
            status=VerificationStatus.PASSED,
            sandbox_id="sandbox-e2e-1",
            started_at=now,
            completed_at=now,
            applied_changes=["app/services/checkout.py"],
            verification_steps=[
                VerificationStepResult(
                    step_id="step-1",
                    description="Run checkout concurrency tests",
                    status=VerificationStepStatus.PASSED,
                    exit_code=0,
                    duration_ms=50.0,
                    stdout="test_checkout: PASSED",
                    stderr="",
                    expected_result="All unit tests pass",
                    observed_result="PASSED",
                )
            ],
            passed_steps=1,
            failed_steps=0,
            logs="Sandbox verification completed successfully.",
            artifacts=[],
            risk_findings=[],
            cleanup_status="complete",
            summary="All verification checks passed in isolated ephemeral container.",
        )
        context.sandbox_verification_result = verif

        return StageResult(stage_id=self.stage_id, status=ExecutionStatus.SUCCESS)


@pytest_asyncio.fixture(scope="function")
async def e2e_engine():
    engine = create_async_engine(
        SQLITE_TEST_URL,
        echo=False,
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.execute(text("PRAGMA foreign_keys = ON"))
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def e2e_session_factory(e2e_engine):
    return async_sessionmaker(bind=e2e_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(scope="function")
def e2e_client(e2e_session_factory, monkeypatch):
    monkeypatch.setattr("app.core.security.settings", TEST_SETTINGS)
    monkeypatch.setattr("app.core.config.settings", TEST_SETTINGS)

    async def override_get_db():
        async with e2e_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_golden_path_investigation_to_approval(
    e2e_client: TestClient,
    e2e_session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-End Golden Path Test:
    1. Authenticate user.
    2. Create Project, Incident, and Investigation.
    3. Trigger Investigation via POST /run.
    4. Verify DB persistence of Evidence, RCA summary, Fix Proposal, and ApprovalArtifact.
    5. Request Human Approval via Phase 18 endpoint.
    6. Verify that proposal is PENDING human decision and NEVER auto-approved.
    """
    user_id = str(uuid.uuid4())
    token = make_test_token(user_id)
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Sync User Profile
    r = e2e_client.post("/api/v1/auth/sync", headers=headers)
    assert r.status_code == 200

    # 2. Create Project
    p_resp = e2e_client.post("/api/v1/projects", json={"name": "Checkout Core Service"}, headers=headers)
    assert p_resp.status_code == 201
    project_id = p_resp.json()["id"]

    # 3. Create Incident
    inc_resp = e2e_client.post(
        f"/api/v1/projects/{project_id}/incidents",
        json={"title": "Connection pool cascade timeout", "severity": "critical", "source": "monitoring"},
        headers=headers,
    )
    assert inc_resp.status_code == 201
    incident_id = inc_resp.json()["id"]

    # 4. Create Investigation
    inv_resp = e2e_client.post(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/investigations",
        json={"summary": "Investigate checkout connection leak"},
        headers=headers,
    )
    assert inv_resp.status_code == 201
    investigation_id = inv_resp.json()["id"]

    # 5. Wire orchestrator with E2E stage
    reg = StageRegistry()
    stage = E2EFullStage()
    reg.register(stage)
    wf = WorkflowDefinition(workflow_id="wf_e2e", name="E2E", stage_ids=[stage.stage_id], failure_policy=FailurePolicy.FAIL_FAST)
    test_orch = DEVDOCOrchestrator(registry=reg, workflow=wf)

    orig_run = InvestigationService.run_investigation_orchestration

    async def mock_run(*args, **kwargs):
        kwargs["orchestrator"] = test_orch
        return await orig_run(*args, **kwargs)

    monkeypatch.setattr(InvestigationService, "run_investigation_orchestration", mock_run)

    # 6. Trigger Investigation via Run Endpoint
    run_resp = e2e_client.post(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/investigations/{investigation_id}/run",
        headers=headers,
    )
    assert run_resp.status_code == 200, run_resp.text
    run_data = run_resp.json()

    assert run_data["status"] == "completed"
    assert run_data["evidence_count"] == 1
    assert run_data["has_root_cause_analysis"] is True
    assert run_data["has_fix_proposal"] is True
    artifact_id = run_data["approval_artifact_id"]
    assert artifact_id is not None
    assert run_data["approval_status"] == "awaiting_human_review"

    # 7. Verify Database Persistence directly
    async with e2e_session_factory() as session:
        # Evidence
        ev_items = (await session.scalars(select(StoredEvidence).where(StoredEvidence.investigation_id == uuid.UUID(investigation_id)))).all()
        assert len(ev_items) == 1
        assert ev_items[0].kind == EvidenceKind.CONTAINER_LOG

        # Fix Proposal
        proposals = (await session.scalars(select(StoredFixProposal).where(StoredFixProposal.investigation_id == uuid.UUID(investigation_id)))).all()
        assert len(proposals) == 1
        proposal = proposals[0]
        assert proposal.status == FixStatus.AWAITING_APPROVAL
        proposal_id = str(proposal.id)

        # Approval Artifact
        artifact = await session.get(ApprovalArtifact, uuid.UUID(artifact_id))
        assert artifact is not None
        assert artifact.verification_status == "passed"
        assert len(artifact.proposal_fingerprint) == 64
        assert len(artifact.verification_fingerprint) == 64

    # 8. Request Human Approval via Phase 18 Human Gate
    appr_resp = e2e_client.post(
        f"/api/v1/projects/{project_id}/investigations/{investigation_id}/approvals",
        json={"proposal_id": proposal_id},
        headers=headers,
    )
    assert appr_resp.status_code == 201, appr_resp.text
    appr_data = appr_resp.json()
    assert appr_data["status"] == "pending"
    assert appr_data["verification_id"] == artifact_id

    # 9. Verify that Proposal remains PENDING human decision (No auto-approval)
    async with e2e_session_factory() as session:
        approval_record = await session.get(Approval, uuid.UUID(appr_data["id"]))
        assert approval_record is not None
        assert approval_record.status == ApprovalStatus.PENDING
        assert approval_record.decision is None
