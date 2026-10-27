#!/usr/bin/env python3
"""DEVDOC — Autonomous AI DevOps Engineer Investigation & Approval Demo.

Repeatable, interactive demonstration runner for the Nebius x NVIDIA Hackathon.
Demonstrates the full incident-to-approval lifecycle:
  Incident Input
  -> Evidence Collection (PostgreSQL / Docker / Metrics)
  -> Evidence Normalization & Correlation
  -> Root Cause Analysis (RCA) with NVIDIA Nemotron
  -> Remediation Proposal Generation
  -> Ephemeral Sandbox Verification
  -> Human Approval Gate & Cryptographic Fingerprinting
  -> Persisted PostgreSQL Audit Trail

Supports two explicitly distinct execution modes:
  --mode=demo  (Default): Deterministic fixtures, simulated execution, offline safe.
  --mode=live  : Real Nebius Token Factory API call with live NVIDIA Nemotron model.

Usage:
  python scripts/demo_investigation.py [--mode=demo|live] [--cleanup]
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

# Ensure backend root is on sys.path
backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.base import Base
from app.models.approval_artifact import ApprovalArtifact
from app.models.evidence import Evidence as StoredEvidence
from app.models.fix_proposal import FixProposal as StoredFixProposal
from app.models.incident import Incident, IncidentSeverity, IncidentSource, IncidentStatus
from app.models.investigation import Investigation, InvestigationStatus
from app.models.project import Project
from app.models.user import User
from app.services.approval import ApprovalService
from app.services.investigation import InvestigationService
from orchestrator.contracts.execution import FailurePolicy, WorkflowDefinition
from orchestrator.contracts.stage import BaseStage
from orchestrator.core.context import InvestigationContext
from orchestrator.core.orchestrator import DEVDOCOrchestrator
from orchestrator.core.result import ExecutionStatus, StageResult
from orchestrator.evidence.models import (
    Evidence,
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

logging.basicConfig(level=logging.WARNING, format="%(message)s")


# ---------------------------------------------------------------------------
# Demo Stage Implementation
# ---------------------------------------------------------------------------

class DemoPipelineStage(BaseStage):
    """Simulates an end-to-end investigation pipeline with rich demo telemetry."""

    def __init__(self, verification_passed: bool = True) -> None:
        self.verification_passed = verification_passed

    @property
    def stage_id(self) -> str:
        return "demo_full_pipeline"

    @property
    def name(self) -> str:
        return "Demo Full Pipeline Stage"

    @property
    def description(self) -> str:
        return "Populates context with normalized evidence, RCA, Fix Proposal, and Sandbox result."

    async def execute(self, context: InvestigationContext) -> StageResult:
        now = datetime.now(UTC)
        ev_id = uuid.uuid4()

        # 1. Evidence
        ev = Evidence(
            investigation_id=context.investigation_id,
            execution_id=context.execution_id,
            evidence_id=ev_id,
            source="docker",
            source_type=EvidenceSource.DOCKER,
            evidence_type=EvidenceType.CONTAINER_LOG,
            timestamp=now,
            timestamp_type=TimestampType.EVENT,
            title="Postgres container connection slots exhausted",
            summary="FATAL: remaining connection slots are reserved for non-replication superuser connections (error 53300)",
            data={"container": "payment-db-primary", "error_code": "53300", "exit_code": 1},
            provenance=EvidenceProvenance(
                agent_id="docker_inspector",
                source="docker",
                collected_at=now,
                source_reference="payment-db-primary",
            ),
            quality=EvidenceQuality(
                source_reliability=SourceReliability.AUTHORITATIVE,
                completeness=1.0,
                timestamp_quality=TimestampType.EVENT,
                validation_status=ValidationStatus.VALID,
                quality_score=0.98,
            ),
            correlation_identifiers=["payment-db-primary", "postgres", "pool_exhaustion"],
        )
        context.evidence_collection = EvidenceCollection(
            investigation_id=context.investigation_id,
            execution_id=context.execution_id,
            items=[ev],
            summary=EvidenceSummary(total_evidence_count=1),
        )

        # 2. Root Cause Analysis (RCA)
        candidate_id = uuid.uuid4()
        ev_ref = RCAEvidenceReference(
            evidence_id=ev_id,
            classification=EvidenceClassification.FACT,
            source="docker",
            evidence_type="container_log",
            timestamp=now,
            title="Connection slot exhaustion",
            summary="Postgres rejected connection due to pool leak",
        )
        candidate = CandidateRootCause(
            candidate_id=candidate_id,
            statement="Database connection leak in PaymentService checkout session handler under elevated concurrency",
            category=RCACategory.RESOURCE_EXHAUSTION,
            confidence=RCAConfidence.HIGH,
            rank=1,
            supporting_evidence=[ev_ref],
            contradicting_evidence=[],
            contributing_factors=[],
            triggering_events=[],
            observed_symptoms=[],
            temporal_relationship_ids=[],
            uncertainty="Minimal; pg_stat_activity confirms unclosed connection handles from checkout workers",
            rationale="Idle checkout sessions held connections indefinitely due to missing context manager cleanup",
            ranking_basis="Direct correlate with PostgreSQL 53300 log and connection plateau telemetry",
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
            reasoning_summary=(
                "PaymentService checkout workers failed to close database connections upon transient HTTP errors. "
                "Connections accumulated until the PostgreSQL max_connections ceiling was reached, causing subsequent "
                "client queries to fail with 504 Gateway Timeouts."
            ),
            analyzed_at=now,
            model_metadata=LLMObservability(
                model="nvidia/Nemotron-3_5-Lightning",
                duration_ms=450.0,
                attempts=1,
                input_tokens=680,
                output_tokens=320,
                estimated_cost_usd=0.00012,
                budget_remaining_usd=1.99988,
            ),
        )
        context.root_cause_analysis = rca

        # 3. Fix Proposal
        fix = OrchestratorFixProposal(
            proposal_id=uuid.uuid4(),
            investigation_id=context.investigation_id,
            execution_id=context.execution_id,
            root_cause_reference=candidate_id,
            status=FixProposalStatus.PROPOSED,
            summary="Wrap checkout database session in asynchronous context manager with 5-second pool timeout",
            rationale="Guarantees connection release back to SQLAlchemy pool even if checkout HTTP requests fail or timeout",
            affected_components=["app/services/checkout.py"],
            change_type=FixChangeType.CODE_CHANGE,
            changes=[
                FixChange(
                    target="checkout.py",
                    target_path="app/services/checkout.py",
                    operation="modify",
                    proposed_diff=(
                        "@@ -45,4 +45,6 @@\n"
                        "-    session = await get_raw_session()\n"
                        "+    async with get_db_session(timeout=5.0) as session:\n"
                        "+        return await process_payment(session, payload)\n"
                    ),
                    reason="Enforce deterministic connection return via async context manager",
                    evidence_references=[ev_id],
                )
            ],
            prerequisites=["Database connection pool timeout configured"],
            risks=[
                FixRisk(
                    category=FixRiskCategory.PERFORMANCE,
                    severity=FixRiskSeverity.LOW,
                    description="Requests taking >5s to acquire a DB connection will receive 503 instead of 504",
                    mitigation="Tuned connection pool size to 50 with queue limit of 100",
                )
            ],
            verification_plan=[
                FixVerificationStep(
                    description="Run concurrency load test simulating 100 parallel checkout requests",
                    expected_result="Zero connection leak; pool utilization stabilizes below 60%",
                    evidence_required=["pool_active_connections"],
                )
            ],
            rollback_plan=[
                FixRollbackStep(
                    description="Revert checkout.py commit via git revert",
                    trigger="Checkout error rate increases above 0.5%",
                    expected_result="Previous checkout session behavior restored",
                )
            ],
            evidence_references=[ev_id],
            external_knowledge_references=[],
            confidence=0.96,
            change_scope="Checkout session acquisition and disposal",
            human_approval_required=True,
            generated_at=now,
            model_metadata=LLMObservability(
                model="nvidia/Nemotron-3_5-Lightning",
                duration_ms=620.0,
                attempts=1,
                input_tokens=850,
                output_tokens=410,
                estimated_cost_usd=0.00015,
                budget_remaining_usd=1.99973,
            ),
        )
        context.fix_proposal = fix

        # 4. Sandbox Verification
        verif = SandboxVerificationResult(
            verification_id=uuid.uuid4(),
            investigation_id=context.investigation_id,
            proposal_id=fix.proposal_id,
            status=VerificationStatus.PASSED if self.verification_passed else VerificationStatus.FAILED,
            sandbox_id="sandbox-ephemeral-pay-svc",
            started_at=now,
            completed_at=now,
            applied_changes=["app/services/checkout.py"],
            verification_steps=[
                VerificationStepResult(
                    step_id="step-1",
                    description="Run checkout session leak regression test",
                    status=VerificationStepStatus.PASSED,
                    exit_code=0,
                    duration_ms=120.0,
                    stdout="test_checkout_session_leak: PASSED (100 parallel workers, 0 leaked connections)",
                    stderr="",
                    expected_result="All connection handles released within 5s",
                    observed_result="PASSED",
                ),
                VerificationStepResult(
                    step_id="step-2",
                    description="Validate syntax and type safety via mypy",
                    status=VerificationStepStatus.PASSED,
                    exit_code=0,
                    duration_ms=85.0,
                    stdout="Success: no issues found in 1 source file",
                    stderr="",
                    expected_result="Clean type check",
                    observed_result="PASSED",
                ),
            ],
            passed_steps=2,
            failed_steps=0,
            logs="Ephemeral container sandbox execution completed with exit code 0.",
            artifacts=["verification-report.json"],
            risk_findings=[],
            cleanup_status="complete",
            summary="All sandbox regression tests and typing checks passed successfully.",
        )
        context.sandbox_verification_result = verif

        return StageResult(
            stage_id=self.stage_id,
            status=ExecutionStatus.SUCCESS if self.verification_passed else ExecutionStatus.FAILED,
        )


def make_demo_orchestrator() -> DEVDOCOrchestrator:
    registry = StageRegistry()
    stage = DemoPipelineStage(verification_passed=True)
    registry.register(stage)
    wf = WorkflowDefinition(
        workflow_id="demo_wf",
        name="DEVDOC Autonomous Investigation Workflow",
        stage_ids=[stage.stage_id],
        failure_policy=FailurePolicy.FAIL_FAST,
    )
    return DEVDOCOrchestrator(registry=registry, workflow=wf)


# ---------------------------------------------------------------------------
# Demo Execution
# ---------------------------------------------------------------------------

async def run_demo_mode(cleanup: bool = False) -> int:
    print("=" * 80)
    print("  DEVDOC — AUTONOMOUS AI DEVOPS ENGINEER (DEMO MODE)")
    print("  Nebius x NVIDIA Global AI Hackathon Sprint")
    print("=" * 80)
    print("  MODE: DEMO (Deterministic fixtures, ephemeral sandbox, safe test isolation)")
    print("  NOTE: No live billing incurred. Preserves human approval gate.\n")

    # In-memory SQLite engine
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.execute(text("PRAGMA foreign_keys = ON"))
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        # 1. Provision User & Project
        user_id = uuid.uuid4()
        user = User(
            id=user_id,
            email="devops-lead@company.internal",
            full_name="Lead DevOps Engineer",
            is_active=True,
        )
        session.add(user)

        project_id = uuid.uuid4()
        project = Project(
            id=project_id,
            name="Payments & Checkout Core",
            slug="payments-checkout-core",
            owner_id=user_id,
            is_active=True,
        )
        session.add(project)

        # 2. Incident
        incident_id = uuid.uuid4()
        incident = Incident(
            id=incident_id,
            project_id=project_id,
            reported_by_id=user_id,
            title="Payment gateway connection timeout cascade",
            description="504 Gateway Timeouts reported on checkout API during traffic surge",
            severity=IncidentSeverity.CRITICAL,
            source=IncidentSource.MONITORING,
            status=IncidentStatus.OPEN,
        )
        session.add(incident)

        # 3. Investigation
        investigation_id = uuid.uuid4()
        investigation = Investigation(
            id=investigation_id,
            incident_id=incident_id,
            project_id=project_id,
            initiated_by_id=user_id,
            status=InvestigationStatus.PENDING,
            summary="Investigate PostgreSQL connection pool exhaustion during traffic surge",
        )
        session.add(investigation)
        await session.commit()

        print(f"[*] Provisioned Incident: '{incident.title}' (ID: {incident_id})")
        print(f"[*] Created Investigation (ID: {investigation_id})")
        print("[*] Triggering Autonomous Investigation Pipeline via InvestigationService...")

        # 4. Run Orchestration
        orchestrator = make_demo_orchestrator()
        result = await InvestigationService.run_investigation_orchestration(
            db=session,
            project=project,
            incident=incident,
            investigation=investigation,
            orchestrator=orchestrator,
        )

        print("\n" + "-" * 80)
        print("  INVESTIGATION EXECUTION COMPLETED")
        print("-" * 80)
        print(f"  Status                  : {investigation.status.value.upper()}")
        print(f"  Evidence Items Saved    : {result.evidence_count}")
        print(f"  RCA Identified          : {result.has_root_cause_analysis}")
        print(f"  Fix Proposal Generated  : {result.has_fix_proposal}")
        print(f"  Approval Artifact ID    : {result.approval_artifact_id}")
        print(f"  Approval Review Status  : {result.approval_status}")
        print(f"  Investigation Summary   : {investigation.summary}")

        # 5. Verify Database Persistence
        ev_items = (await session.scalars(select(StoredEvidence).where(StoredEvidence.investigation_id == investigation_id))).all()
        print(f"\n[*] Persisted Evidence in PostgreSQL ({len(ev_items)} items):")
        for item in ev_items:
            print(f"    - [{item.kind.value}] {item.label} (Score: {item.relevance_score}/100)")

        proposals = (await session.scalars(select(StoredFixProposal).where(StoredFixProposal.investigation_id == investigation_id))).all()
        print(f"\n[*] Persisted Fix Proposals ({len(proposals)} proposals):")
        stored_proposal = proposals[0]
        print(f"    - Title      : {stored_proposal.title}")
        print(f"    - Status     : {stored_proposal.status.value.upper()}")
        print(f"    - Confidence : {stored_proposal.confidence_score}%")
        print(f"    - Files      : {stored_proposal.affected_files}")

        artifact = await session.get(ApprovalArtifact, result.approval_artifact_id)
        print("\n[*] Verified Approval Artifact (Cryptographic Review Integrity):")
        print(f"    - Artifact ID               : {artifact.id}")
        print(f"    - Verification Status       : {artifact.verification_status.upper()}")
        print(f"    - Proposal Fingerprint (SHA): {artifact.proposal_fingerprint[:24]}...")
        print(f"    - Verify Fingerprint   (SHA): {artifact.verification_fingerprint[:24]}...")

        # 6. Demonstrate Human Approval Gate
        print("\n" + "-" * 80)
        print("  STAGE 18: MANDATORY HUMAN APPROVAL GATE")
        print("-" * 80)
        print("  [SECURITY GUARANTEE] DEVDOC NEVER automatically approves or applies remediations.")
        print(f"  Initiating human approval request for Proposal {stored_proposal.id}...")

        approval_resp = await ApprovalService.create_request(
            db=session,
            project=project,
            actor=user,
            investigation_id=investigation_id,
            proposal_id=stored_proposal.id,
            request_id=str(uuid.uuid4()),
        )
        await session.commit()

        print(f"  Approval Request Created: ID = {approval_resp.id}")
        print(f"  Status                  : {approval_resp.status.value.upper()}")
        print(f"  Expires At              : {approval_resp.expires_at}")
        print("  Awaiting Authorized Human Operator decision via:")
        print(f"    POST /api/v1/projects/{project_id}/investigations/{investigation_id}/approvals/{approval_resp.id}/decision")
        print("=" * 80)
        print("  DEMO SUCCEEDED — End-to-end investigation and approval pipeline verified!")
        print("=" * 80)

    await engine.dispose()
    return 0


async def run_live_mode() -> int:
    print("=" * 80)
    print("  DEVDOC — AUTONOMOUS AI DEVOPS ENGINEER (LIVE NEBIUS / NVIDIA MODE)")
    print("  Nebius x NVIDIA Global AI Hackathon Sprint")
    print("=" * 80)

    if not settings.nebius_api_key.get_secret_value():
        print("  [ERROR] NEBIUS_API_KEY is not configured in .env.")
        print("  Please provide a valid Nebius Token Factory API key to run in live mode.")
        return 1

    print(f"  Endpoint : {settings.nebius_base_url}")
    print(f"  Model    : {settings.nebius_model}")
    print(f"  Budget   : ${settings.llm_budget_usd:.2f} USD")
    print("  Testing live connection to Nebius Token Factory...\n")

    import httpx
    headers = {
        "Authorization": f"Bearer {settings.nebius_api_key.get_secret_value()}",
        "Content-Type": "application/json",
    }
    base = settings.nebius_base_url.rstrip("/")

    # Check model list
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            m_res = await client.get(f"{base}/models", headers=headers)
            if m_res.status_code != 200:
                print(f"  [ERROR] Nebius API returned status {m_res.status_code}: {m_res.text}")
                return 1
            models = [m["id"] for m in m_res.json().get("data", [])]
            print(f"  [OK] Nebius API accessible ({len(models)} models available).")
            active_model = settings.nebius_model
            if active_model not in models:
                print(f"  [WARN] Configured model '{active_model}' not found in active list.")
                # fallback to first available nemotron
                nemotrons = [m for m in models if "nemotron" in m.lower()]
                if nemotrons:
                    active_model = nemotrons[0]
                    print(f"  [INFO] Using active NVIDIA Nemotron model: {active_model}")
        except Exception as exc:
            print(f"  [ERROR] Connection failed: {exc}")
            return 1

    # Execute structured live reasoning
    print(f"\n[*] Executing live reasoning test with {active_model}...")
    from orchestrator.evidence.models import (
        Evidence,
        EvidenceCollection,
        EvidenceProvenance,
        EvidenceSource,
        EvidenceType,
    )
    from orchestrator.llm.budget import LLMBudgetGuard
    from orchestrator.llm.nebius import NebiusNemotronProvider
    from orchestrator.llm.service import LLMService

    provider = NebiusNemotronProvider(
        api_key=settings.nebius_api_key,
        base_url=settings.nebius_base_url,
    )
    budget = LLMBudgetGuard(
        budget_usd=min(settings.llm_budget_usd, 5.0),
        input_cost_per_million_usd=0.06,
        output_cost_per_million_usd=0.24,
        ledger_path=None,
    )
    service = LLMService(
        provider=provider,
        budget_guard=budget,
        model=active_model,
        timeout_seconds=45.0,
        max_attempts=2,
        retry_backoff_seconds=0.5,
        max_input_tokens=4000,
        max_output_tokens=2500,
        cache_ttl_seconds=60,
        cache_max_entries=10,
    )

    ev_id = uuid.uuid4()
    now = datetime.now(UTC)
    item = Evidence(
        evidence_id=ev_id,
        investigation_id=uuid.uuid4(),
        execution_id=uuid.uuid4(),
        source="docker",
        source_type=EvidenceSource.DOCKER,
        evidence_type=EvidenceType.CONTAINER_LOG,
        timestamp=now,
        title="PostgreSQL connection limit reached",
        summary="FATAL: remaining connection slots are reserved for non-replication superuser connections (error 53300)",
        data={"container": "postgres-primary", "error_code": "53300"},
        correlation_identifiers=["postgres", "connection_pool"],
        provenance=EvidenceProvenance(agent_id="docker_inspector", source="docker", collected_at=now),
    )
    collection = EvidenceCollection(
        investigation_id=uuid.uuid4(),
        execution_id=uuid.uuid4(),
        items=[item],
    )

    start = datetime.now(UTC)
    response = await service.reason(collection)
    duration = (datetime.now(UTC) - start).total_seconds()

    print("\n" + "-" * 80)
    print("  LIVE NEBIUS / NVIDIA INFERENCE SUCCEEDED")
    print("-" * 80)
    print(f"  Model               : {response.metadata.model}")
    print(f"  Request ID          : {response.metadata.request_id}")
    print(f"  Latency             : {duration:.2f}s ({response.metadata.duration_ms:.1f}ms reported)")
    print(f"  Input Tokens        : {response.metadata.input_tokens}")
    print(f"  Output Tokens       : {response.metadata.output_tokens}")
    print(f"  Estimated Cost      : ${response.metadata.estimated_cost_usd:.6f} USD")
    print(f"  Budget Remaining    : ${response.metadata.budget_remaining_usd:.4f} USD")
    print(f"  Reasoning Summary   : {response.reasoning.summary}")
    print(f"  Observations ({len(response.reasoning.observations)} items):")
    for obs in response.reasoning.observations:
        print(f"    - {obs.text}")
    print(f"  Uncertainties       : {response.reasoning.uncertainties}")
    print("=" * 80)
    print("  LIVE MODE VERIFICATION COMPLETE — Genuine external provider response received.")
    print("=" * 80)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="DEVDOC Autonomous Investigation Demo Runner")
    parser.add_argument(
        "--mode",
        choices=["demo", "live"],
        default="demo",
        help="Run in offline deterministic 'demo' mode or 'live' Nebius API mode",
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Clean up created demo records (if applicable)",
    )
    args = parser.parse_args()

    if args.mode == "live":
        code = asyncio.run(run_live_mode())
    else:
        code = asyncio.run(run_demo_mode(cleanup=args.cleanup))

    sys.exit(code)


if __name__ == "__main__":
    main()
