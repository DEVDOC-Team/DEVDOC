"""DEVDOC Batch 2 — Investigation Run API and Persistent Pipeline Results Test Suite.

Verifies:
1. Authorized request successfully triggers an investigation through REST API.
2. Unauthenticated request is rejected (401).
3. Unauthorized project access is rejected (403).
4. Mismatched project, incident, and investigation IDs are rejected (404).
5. Invalid lifecycle transitions (422) and duplicate concurrent runs (409) are handled safely.
6. Evidence is persisted and retrievable via database models.
7. RCA results are persisted into investigation summary and token metrics when available.
8. Fix proposals are persisted and retrievable with correct statuses.
9. Failed or disabled sandbox verification does not create a false passing approval artifact.
10. A genuine successful verification creates the expected artifact when supported by the provider.
11. Orchestrator failure does not falsely report completion and preserves valid evidence.
12. Existing approval APIs and review flows work with the persisted outputs.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import jwt
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

# ---------------------------------------------------------------------------
# Test Constants & Settings
# ---------------------------------------------------------------------------

TEST_JWT_SECRET = "devdoc-test-secret-key-32-chars-long-minimum!"
TEST_ISSUER = "https://test.supabase.co/auth/v1"
TEST_AUDIENCE = "authenticated"

TEST_SETTINGS = Settings(
    supabase_jwt_secret=TEST_JWT_SECRET,
    supabase_jwt_algorithm="HS256",
    supabase_jwt_issuer=TEST_ISSUER,
    supabase_jwt_audience=TEST_AUDIENCE,
)

SQLITE_TEST_URL = "sqlite+aiosqlite:///:memory:"


def make_test_token(
    sub: str | None = None,
    email: str | None = None,
    exp_offset_seconds: int = 3600,
    issuer: str = TEST_ISSUER,
    audience: str = TEST_AUDIENCE,
    secret: str = TEST_JWT_SECRET,
) -> str:
    """Generate a test Supabase HS256 JWT."""
    now = int(time.time())
    payload = {
        "sub": sub or str(uuid.uuid4()),
        "email": email or "user@devdoc.io",
        "aud": audience,
        "iss": issuer,
        "iat": now,
        "exp": now + exp_offset_seconds,
        "role": "authenticated",
        "user_metadata": {"full_name": "Test User"},
    }
    return jwt.encode(payload, secret, algorithm="HS256")


# ---------------------------------------------------------------------------
# Pipeline Mock Helper Functions
# ---------------------------------------------------------------------------


def make_mock_evidence(investigation_id: uuid.UUID) -> OrchestratorEvidence:
    now = datetime.now(UTC)
    ev_id = uuid.uuid4()
    return OrchestratorEvidence(
        evidence_id=ev_id,
        investigation_id=investigation_id,
        execution_id=uuid.uuid4(),
        source="docker",
        source_type=EvidenceSource.DOCKER,
        evidence_type=EvidenceType.CONTAINER_LOG,
        timestamp=now,
        title="OOM killer invocation detected in api-service container",
        summary="Container logs show exit code 137 due to Out Of Memory condition",
        data={"container_id": "api-srv-1", "exit_code": 137, "reason": "OOMKilled"},
        provenance=EvidenceProvenance(
            agent_id="docker_agent",
            source="docker",
            collected_at=now,
            source_reference="docker://local/containers/api-srv-1",
        ),
        quality=EvidenceQuality(quality_score=0.95),
    )


def make_mock_rca(investigation_id: uuid.UUID, evidence_id: uuid.UUID) -> RootCauseAnalysis:
    now = datetime.now(UTC)
    candidate_id = uuid.uuid4()
    ev_ref = RCAEvidenceReference(
        evidence_id=evidence_id,
        classification=EvidenceClassification.FACT,
        source="docker",
        evidence_type="container_log",
        timestamp=now,
        title="OOM killer invocation",
        summary="OOM killed container",
    )
    candidate = CandidateRootCause(
        candidate_id=candidate_id,
        statement="Memory leak in query cache buffer leading to OOM crash",
        category=RCACategory.RESOURCE_EXHAUSTION,
        confidence=RCAConfidence.HIGH,
        rank=1,
        supporting_evidence=[ev_ref],
        contradicting_evidence=[],
        contributing_factors=[],
        triggering_events=[],
        observed_symptoms=[],
        temporal_relationship_ids=[],
        uncertainty="Minimal; dump shows unreleased cache pointers",
        rationale="Cache entries lack TTL eviction",
        ranking_basis="Direct correlate with spike in memory RSS",
    )
    return RootCauseAnalysis(
        analysis_id=uuid.uuid4(),
        investigation_id=investigation_id,
        execution_id=uuid.uuid4(),
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
        reasoning_summary="The query cache failed to evict stale entries under high load, causing container OOM.",
        analyzed_at=now,
        model_metadata=LLMObservability(
            model="meta-llama/Llama-3.3-70B-Instruct",
            duration_ms=150.0,
            attempts=1,
            input_tokens=150,
            output_tokens=75,
            estimated_cost_usd=0.002,
            budget_remaining_usd=9.99,
        ),
    )


def make_mock_fix(investigation_id: uuid.UUID, rca_id: uuid.UUID, evidence_id: uuid.UUID) -> OrchestratorFixProposal:
    now = datetime.now(UTC)
    return OrchestratorFixProposal(
        proposal_id=uuid.uuid4(),
        investigation_id=investigation_id,
        execution_id=uuid.uuid4(),
        root_cause_reference=rca_id,
        status=FixProposalStatus.PROPOSED,
        summary="Set maximum cache size and 5-minute TTL eviction on QueryCache",
        rationale="Bounds cache memory consumption and ensures deterministic memory usage",
        affected_components=["cache_manager.py"],
        change_type=FixChangeType.CODE_CHANGE,
        changes=[
            FixChange(
                target="cache_manager.py",
                target_path="app/cache/cache_manager.py",
                operation="modify",
                proposed_diff="@@ -10,3 +10,5 @@\n+MAX_ENTRIES = 1000\n+TTL = 300\n",
                reason="Enforce bounding limit",
                evidence_references=[evidence_id],
            )
        ],
        prerequisites=[],
        risks=[
            FixRisk(
                category=FixRiskCategory.PERFORMANCE,
                severity=FixRiskSeverity.LOW,
                description="Slight increase in cache misses under extreme key cardinality",
                mitigation="Tuned maximum capacity to 10k items",
            )
        ],
        verification_plan=[
            FixVerificationStep(
                description="Run cache memory benchmark under simulated load",
                expected_result="Memory usage plateau below 256MB",
                evidence_required=["memory_telemetry"],
            )
        ],
        rollback_plan=[
            FixRollbackStep(
                description="Revert cache_manager.py commit",
                trigger="Cache hit ratio drops below 80%",
                expected_result="Previous cache implementation restored",
            )
        ],
        evidence_references=[evidence_id],
        external_knowledge_references=[],
        confidence=0.92,
        change_scope="Application-level cache bounds",
        human_approval_required=True,
        generated_at=now,
        model_metadata=LLMObservability(
            model="meta-llama/Llama-3.3-70B-Instruct",
            duration_ms=200.0,
            attempts=1,
            input_tokens=200,
            output_tokens=120,
            estimated_cost_usd=0.004,
            budget_remaining_usd=9.98,
        ),
    )


def make_mock_verification(
    investigation_id: uuid.UUID,
    proposal_id: uuid.UUID,
    passed: bool = True,
) -> SandboxVerificationResult:
    now = datetime.now(UTC)
    status_val = VerificationStatus.PASSED if passed else VerificationStatus.FAILED
    step_status = VerificationStepStatus.PASSED if passed else VerificationStepStatus.FAILED
    return SandboxVerificationResult(
        verification_id=uuid.uuid4(),
        investigation_id=investigation_id,
        proposal_id=proposal_id,
        status=status_val,
        sandbox_id="sandbox-ephemeral-1",
        started_at=now,
        completed_at=now,
        applied_changes=["app/cache/cache_manager.py"],
        verification_steps=[
            VerificationStepResult(
                step_id="step-1",
                description="Run cache eviction unit tests",
                status=step_status,
                exit_code=0 if passed else 1,
                duration_ms=45.0,
                stdout="test_cache_eviction: PASSED" if passed else "test_cache_eviction: FAILED",
                stderr="" if passed else "AssertionError: memory did not plateau",
                expected_result="All unit tests pass",
                observed_result="PASSED" if passed else "FAILED",
            )
        ],
        passed_steps=1 if passed else 0,
        failed_steps=0 if passed else 1,
        logs="Sandbox test execution completed." if passed else "Sandbox test execution failed.",
        artifacts=[],
        risk_findings=[],
        cleanup_status="complete",
        summary="All verification checks passed in isolated ephemeral container"
        if passed
        else "Verification test suite failed with exit code 1",
    )


# ---------------------------------------------------------------------------
# Custom Mock Stage Implementations for Test Orchestration
# ---------------------------------------------------------------------------


class MockFullPipelineStage(BaseStage):
    """Simulates a complete, passing or failing investigation run."""

    def __init__(self, verification_passed: bool = True) -> None:
        self.verification_passed = verification_passed

    @property
    def stage_id(self) -> str:
        return "mock_full_stage"

    @property
    def name(self) -> str:
        return "Mock Full Pipeline Stage"

    @property
    def description(self) -> str:
        return "Populates context with evidence, RCA, Fix, and Sandbox result."

    async def execute(self, context: InvestigationContext) -> StageResult:
        ev = make_mock_evidence(context.investigation_id)
        collection = EvidenceCollection(
            investigation_id=context.investigation_id,
            execution_id=context.execution_id,
            items=[ev],
            summary=EvidenceSummary(total_evidence_count=1),
        )
        context.evidence_collection = collection
        rca = make_mock_rca(context.investigation_id, ev.evidence_id)
        context.root_cause_analysis = rca
        candidate_ref = (
            rca.selected_root_cause.candidate_id
            if rca.selected_root_cause is not None
            else rca.analysis_id
        )
        fix = make_mock_fix(context.investigation_id, candidate_ref, ev.evidence_id)
        context.fix_proposal = fix
        verif = make_mock_verification(
            context.investigation_id, fix.proposal_id, passed=self.verification_passed
        )
        context.sandbox_verification_result = verif

        return StageResult(
            stage_id=self.stage_id,
            status=ExecutionStatus.SUCCESS if self.verification_passed else ExecutionStatus.FAILED,
            error_message=None if self.verification_passed else "Sandbox verification failed",
        )


class MockFailingAfterEvidenceStage(BaseStage):
    """Populates evidence, then fails the stage."""

    @property
    def stage_id(self) -> str:
        return "mock_failing_stage"

    @property
    def name(self) -> str:
        return "Mock Failing Stage"

    @property
    def description(self) -> str:
        return "Simulates an orchestrator failure after collecting evidence."

    async def execute(self, context: InvestigationContext) -> StageResult:
        ev = make_mock_evidence(context.investigation_id)
        context.evidence_collection = EvidenceCollection(
            investigation_id=context.investigation_id,
            execution_id=context.execution_id,
            items=[ev],
            summary=EvidenceSummary(total_evidence_count=1),
        )
        return StageResult(
            stage_id=self.stage_id,
            status=ExecutionStatus.FAILED,
            error_message="Simulated analysis engine failure after evidence collection",
        )


def make_test_orchestrator(stage: BaseStage) -> DEVDOCOrchestrator:
    registry = StageRegistry()
    registry.register(stage)
    wf = WorkflowDefinition(
        workflow_id="test_wf",
        name="Test Workflow",
        stage_ids=[stage.stage_id],
        failure_policy=FailurePolicy.FAIL_FAST,
    )
    return DEVDOCOrchestrator(registry=registry, workflow=wf)


# ---------------------------------------------------------------------------
# Test Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="function")
async def sqlite_engine():
    """Create in-memory SQLite engine with static pool to share connection across sessions."""
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
async def sqlite_session_factory(sqlite_engine):
    return async_sessionmaker(
        bind=sqlite_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


@pytest.fixture(scope="function")
def client(sqlite_session_factory, monkeypatch):
    """FastAPI TestClient with overridden get_db and test security settings."""
    monkeypatch.setattr("app.core.security.settings", TEST_SETTINGS)
    monkeypatch.setattr("app.core.config.settings", TEST_SETTINGS)

    async def override_get_db() -> AsyncGenerator[AsyncSession]:
        async with sqlite_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def setup_incident_and_investigation(
    client: TestClient,
    status: str = "pending",
) -> tuple[str, str, str, str]:
    """Helper to provision a user, project, incident, and investigation via the test client."""
    uid = str(uuid.uuid4())
    token = make_test_token(sub=uid, email=f"user-{uid}@devdoc.io")
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token}"})

    p_resp = client.post(
        "/api/v1/projects",
        json={"name": "Payments Service"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert p_resp.status_code == 201
    project_id = p_resp.json()["id"]

    inc_resp = client.post(
        f"/api/v1/projects/{project_id}/incidents",
        json={"title": "Payment gateway 504 timeouts", "severity": "critical", "source": "monitoring"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert inc_resp.status_code == 201
    incident_id = inc_resp.json()["id"]

    inv_resp = client.post(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/investigations",
        json={"summary": "Analyze payment gateway timeouts", "status": status},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert inv_resp.status_code == 201
    investigation_id = inv_resp.json()["id"]

    return token, project_id, incident_id, investigation_id


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------


def test_01_authorized_request_triggers_investigation_and_persists_results(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """1. Authorized request successfully triggers an investigation and returns persisted results."""
    token, project_id, incident_id, investigation_id = setup_incident_and_investigation(client)

    test_orch = make_test_orchestrator(MockFullPipelineStage(verification_passed=True))
    orig_run = InvestigationService.run_investigation_orchestration

    async def mock_run_orch(*args, **kwargs):
        kwargs["orchestrator"] = test_orch
        return await orig_run(*args, **kwargs)

    monkeypatch.setattr(InvestigationService, "run_investigation_orchestration", mock_run_orch)

    response = client.post(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/investigations/{investigation_id}/run",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200, response.text
    data = response.json()

    assert data["id"] == investigation_id
    assert data["status"] == "completed"
    assert data["evidence_count"] == 1
    assert data["has_root_cause_analysis"] is True
    assert data["has_fix_proposal"] is True
    assert data["approval_artifact_id"] is not None
    assert data["approval_status"] == "awaiting_human_review"
    assert "Root Cause Identified" in (data["summary"] or "")


def test_02_unauthenticated_request_is_rejected(client: TestClient) -> None:
    """2. Unauthenticated request without Bearer token is rejected with 401."""
    token, project_id, incident_id, investigation_id = setup_incident_and_investigation(client)

    response = client.post(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/investigations/{investigation_id}/run"
    )
    assert response.status_code == 401


def test_03_unauthorized_project_access_is_rejected(client: TestClient) -> None:
    """3. Another authenticated user cannot trigger an investigation in a project they do not own (403)."""
    _, project_id, incident_id, investigation_id = setup_incident_and_investigation(client)

    other_uid = str(uuid.uuid4())
    other_token = make_test_token(sub=other_uid, email=f"other-{other_uid}@devdoc.io")
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {other_token}"})

    response = client.post(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/investigations/{investigation_id}/run",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert response.status_code == 403


def test_04_mismatched_resource_ids_are_rejected(client: TestClient) -> None:
    """4. Mismatched project, incident, and investigation IDs return 404 without leaking internal state."""
    token, project_id, incident_id, investigation_id = setup_incident_and_investigation(client)
    random_id = str(uuid.uuid4())

    # Mismatched incident ID
    res1 = client.post(
        f"/api/v1/projects/{project_id}/incidents/{random_id}/investigations/{investigation_id}/run",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res1.status_code == 404

    # Mismatched investigation ID
    res2 = client.post(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/investigations/{random_id}/run",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res2.status_code == 404


def test_05_lifecycle_and_concurrent_run_prevention(client: TestClient) -> None:
    """5. Running an already RUNNING investigation returns 409; running a COMPLETED investigation returns 422."""
    # Case A: Already RUNNING
    token_a, proj_a, inc_a, inv_a = setup_incident_and_investigation(client, status="running")
    res_running = client.post(
        f"/api/v1/projects/{proj_a}/incidents/{inc_a}/investigations/{inv_a}/run",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert res_running.status_code == 409
    assert "already running" in res_running.text.lower()

    # Case B: Terminal status
    token_b, proj_b, inc_b, inv_b = setup_incident_and_investigation(client, status="pending")
    # Transition to COMPLETED
    client.patch(
        f"/api/v1/projects/{proj_b}/incidents/{inc_b}/investigations/{inv_b}/status",
        json={"status": "running"},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    client.patch(
        f"/api/v1/projects/{proj_b}/incidents/{inc_b}/investigations/{inv_b}/status",
        json={"status": "completed"},
        headers={"Authorization": f"Bearer {token_b}"},
    )

    res_completed = client.post(
        f"/api/v1/projects/{proj_b}/incidents/{inc_b}/investigations/{inv_b}/run",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert res_completed.status_code == 422
    assert "terminal status" in res_completed.text.lower()


@pytest.mark.asyncio
async def test_06_evidence_persisted_and_retrievable(
    client: TestClient,
    sqlite_session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """6. Evidence items from the pipeline are persisted to PostgreSQL evidence table and retrievable."""
    token, project_id, incident_id, investigation_id = setup_incident_and_investigation(client)
    test_orch = make_test_orchestrator(MockFullPipelineStage(verification_passed=True))

    orig_run = InvestigationService.run_investigation_orchestration

    async def mock_run_orch(*args, **kwargs):
        kwargs["orchestrator"] = test_orch
        return await orig_run(*args, **kwargs)

    monkeypatch.setattr(InvestigationService, "run_investigation_orchestration", mock_run_orch)

    res = client.post(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/investigations/{investigation_id}/run",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200

    # Query DB directly to verify evidence
    async with sqlite_session_factory() as session:
        ev_stmt = select(StoredEvidence).where(StoredEvidence.investigation_id == uuid.UUID(investigation_id))
        items = (await session.scalars(ev_stmt)).all()
        assert len(items) == 1
        ev_item = items[0]
        assert ev_item.kind == EvidenceKind.CONTAINER_LOG
        assert "OOM killer invocation" in ev_item.label
        assert ev_item.relevance_score == 95
        assert "api-srv-1" in (ev_item.raw_content or "")


@pytest.mark.asyncio
async def test_07_rca_persisted_to_investigation_summary(
    client: TestClient,
    sqlite_session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """7. RCA reasoning summary, confidence, and token metrics are persisted to the investigation."""
    token, project_id, incident_id, investigation_id = setup_incident_and_investigation(client)
    test_orch = make_test_orchestrator(MockFullPipelineStage(verification_passed=True))

    orig_run = InvestigationService.run_investigation_orchestration

    async def mock_run_orch(*args, **kwargs):
        kwargs["orchestrator"] = test_orch
        return await orig_run(*args, **kwargs)

    monkeypatch.setattr(InvestigationService, "run_investigation_orchestration", mock_run_orch)

    res = client.post(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/investigations/{investigation_id}/run",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200

    async with sqlite_session_factory() as session:
        inv = await session.get(Investigation, uuid.UUID(investigation_id))
        assert inv is not None
        assert inv.status == InvestigationStatus.COMPLETED
        assert "Root Cause Identified: Memory leak in query cache buffer" in (inv.summary or "")
        assert "Confidence: HIGH" in (inv.summary or "")
        assert inv.tokens_used > 0
        assert inv.estimated_cost_usd > 0


@pytest.mark.asyncio
async def test_08_fix_proposals_persisted_and_retrievable(
    client: TestClient,
    sqlite_session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """8. Fix proposals are persisted into the fix_proposals table with correct fields and status."""
    token, project_id, incident_id, investigation_id = setup_incident_and_investigation(client)
    test_orch = make_test_orchestrator(MockFullPipelineStage(verification_passed=True))

    orig_run = InvestigationService.run_investigation_orchestration

    async def mock_run_orch(*args, **kwargs):
        kwargs["orchestrator"] = test_orch
        return await orig_run(*args, **kwargs)

    monkeypatch.setattr(InvestigationService, "run_investigation_orchestration", mock_run_orch)

    res = client.post(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/investigations/{investigation_id}/run",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200

    async with sqlite_session_factory() as session:
        prop_stmt = select(StoredFixProposal).where(
            StoredFixProposal.investigation_id == uuid.UUID(investigation_id)
        )
        proposals = (await session.scalars(prop_stmt)).all()
        assert len(proposals) == 1
        proposal = proposals[0]
        assert proposal.status == FixStatus.AWAITING_APPROVAL
        assert "QueryCache" in proposal.title
        assert proposal.confidence_score == 92
        assert "app/cache/cache_manager.py" in (proposal.affected_files or "")


@pytest.mark.asyncio
async def test_09_failed_sandbox_verification_does_not_create_approval_artifact(
    client: TestClient,
    sqlite_session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """9. Failed sandbox verification records fix as SANDBOX_FAILED and does NOT create a passing approval artifact."""
    token, project_id, incident_id, investigation_id = setup_incident_and_investigation(client)
    test_orch = make_test_orchestrator(MockFullPipelineStage(verification_passed=False))

    orig_run = InvestigationService.run_investigation_orchestration

    async def mock_run_orch(*args, **kwargs):
        kwargs["orchestrator"] = test_orch
        return await orig_run(*args, **kwargs)

    monkeypatch.setattr(InvestigationService, "run_investigation_orchestration", mock_run_orch)

    res = client.post(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/investigations/{investigation_id}/run",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "failed"
    assert data["approval_artifact_id"] is None

    async with sqlite_session_factory() as session:
        # Check FixProposal status in DB
        prop_stmt = select(StoredFixProposal).where(
            StoredFixProposal.investigation_id == uuid.UUID(investigation_id)
        )
        proposal = (await session.scalars(prop_stmt)).first()
        assert proposal is not None
        assert proposal.status == FixStatus.SANDBOX_FAILED

        # Check that no approval artifacts exist
        art_stmt = select(ApprovalArtifact).where(
            ApprovalArtifact.investigation_id == uuid.UUID(investigation_id)
        )
        artifacts = (await session.scalars(art_stmt)).all()
        assert len(artifacts) == 0


@pytest.mark.asyncio
async def test_10_passing_verification_creates_expected_approval_artifact(
    client: TestClient,
    sqlite_session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """10. Genuine successful verification creates the expected ApprovalArtifact and awaits human review."""
    token, project_id, incident_id, investigation_id = setup_incident_and_investigation(client)
    test_orch = make_test_orchestrator(MockFullPipelineStage(verification_passed=True))

    orig_run = InvestigationService.run_investigation_orchestration

    async def mock_run_orch(*args, **kwargs):
        kwargs["orchestrator"] = test_orch
        return await orig_run(*args, **kwargs)

    monkeypatch.setattr(InvestigationService, "run_investigation_orchestration", mock_run_orch)

    res = client.post(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/investigations/{investigation_id}/run",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["approval_artifact_id"] is not None

    art_id = uuid.UUID(data["approval_artifact_id"])
    async with sqlite_session_factory() as session:
        artifact = await session.get(ApprovalArtifact, art_id)
        assert artifact is not None
        assert artifact.project_id == uuid.UUID(project_id)
        assert artifact.investigation_id == uuid.UUID(investigation_id)
        assert artifact.verification_status == "passed"
        assert len(artifact.proposal_fingerprint) == 64
        assert len(artifact.verification_fingerprint) == 64


@pytest.mark.asyncio
async def test_11_orchestrator_failure_preserves_valid_evidence(
    client: TestClient,
    sqlite_session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """11. An orchestrator stage failure marks investigation FAILED and preserves valid collected evidence."""
    token, project_id, incident_id, investigation_id = setup_incident_and_investigation(client)
    test_orch = make_test_orchestrator(MockFailingAfterEvidenceStage())

    orig_run = InvestigationService.run_investigation_orchestration

    async def mock_run_orch(*args, **kwargs):
        kwargs["orchestrator"] = test_orch
        return await orig_run(*args, **kwargs)

    monkeypatch.setattr(InvestigationService, "run_investigation_orchestration", mock_run_orch)

    res = client.post(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/investigations/{investigation_id}/run",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "failed"
    assert data["evidence_count"] == 1
    assert "Simulated analysis engine failure" in (data["error_message"] or "")

    async with sqlite_session_factory() as session:
        inv = await session.get(Investigation, uuid.UUID(investigation_id))
        assert inv is not None
        assert inv.status == InvestigationStatus.FAILED
        assert inv.completed_at is not None

        # Evidence must be saved despite the pipeline failure
        ev_stmt = select(StoredEvidence).where(StoredEvidence.investigation_id == uuid.UUID(investigation_id))
        evidence_items = (await session.scalars(ev_stmt)).all()
        assert len(evidence_items) == 1


@pytest.mark.asyncio
async def test_12_persisted_outputs_integrate_with_approvals_api(
    client: TestClient,
    sqlite_session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """12. Verified approval artifact integrates seamlessly with existing human approval endpoints."""
    token, project_id, incident_id, investigation_id = setup_incident_and_investigation(client)
    test_orch = make_test_orchestrator(MockFullPipelineStage(verification_passed=True))

    orig_run = InvestigationService.run_investigation_orchestration

    async def mock_run_orch(*args, **kwargs):
        kwargs["orchestrator"] = test_orch
        return await orig_run(*args, **kwargs)

    monkeypatch.setattr(InvestigationService, "run_investigation_orchestration", mock_run_orch)

    # 1. Trigger investigation run
    run_res = client.post(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/investigations/{investigation_id}/run",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert run_res.status_code == 200
    artifact_id = run_res.json()["approval_artifact_id"]
    assert artifact_id is not None

    # 2. Retrieve proposal ID from DB
    async with sqlite_session_factory() as session:
        prop_stmt = select(StoredFixProposal).where(
            StoredFixProposal.investigation_id == uuid.UUID(investigation_id)
        )
        proposal = (await session.scalars(prop_stmt)).first()
        assert proposal is not None
        proposal_id = str(proposal.id)

    # 3. Request human approval via Phase 18 endpoint
    appr_res = client.post(
        f"/api/v1/projects/{project_id}/investigations/{investigation_id}/approvals",
        json={"proposal_id": proposal_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert appr_res.status_code == 201, appr_res.text
    appr_data = appr_res.json()
    assert appr_data["status"] == "pending"
    assert appr_data["verification_id"] == artifact_id
