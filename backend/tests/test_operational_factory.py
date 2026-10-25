"""Tests for the operational orchestrator factory (Batch 1)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.config import Settings
from orchestrator.agents.docker_inspector import FakeDockerInspector
from orchestrator.agents.monitoring_provider import FakeMonitoringProvider
from orchestrator.contracts.stage import StageIdentifier
from orchestrator.core.context import InvestigationContext
from orchestrator.core.factory import create_operational_orchestrator
from orchestrator.core.result import ExecutionStatus
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
from orchestrator.llm.contracts import LLMObservability, ReasoningResponse, StructuredReasoning
from orchestrator.llm.service import LLMService
from orchestrator.sandbox.fake import FakeSandboxProvider
from orchestrator.sandbox.models import (
    SandboxExecution,
    VerificationCommand,
)


def _make_test_context() -> InvestigationContext:
    return InvestigationContext(
        investigation_id=uuid.uuid4(),
        incident_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
    )


def _make_test_proposal(investigation_id: uuid.UUID) -> FixProposal:
    return FixProposal(
        proposal_id=uuid.uuid4(),
        investigation_id=investigation_id,
        execution_id=uuid.uuid4(),
        root_cause_reference=uuid.uuid4(),
        status=FixProposalStatus.REQUIRES_HUMAN_REVIEW,
        summary="Correct validated database connection pool settings.",
        rationale="Evidence demonstrates thread exhaustion on connection requests.",
        affected_components=["backend/db"],
        change_type="configuration_change",
        changes=[
            FixChange(
                target="application setting",
                target_path="app/settings.py",
                operation="replace setting",
                proposed_state="db_pool_size = 10\n",
                reason="Increase connection pool headroom.",
                evidence_references=[uuid.uuid4()],
            )
        ],
        prerequisites=[],
        risks=[
            FixRisk(
                category=FixRiskCategory.PERFORMANCE,
                severity=FixRiskSeverity.LOW,
                description="Higher pool size consumes additional database connections.",
                mitigation="Bounded within server max_connections.",
            )
        ],
        verification_plan=[
            FixVerificationStep(
                description="Run the test suite in sandbox.",
                expected_result="CHECKS_OK",
                evidence_required=["validation output"],
            )
        ],
        rollback_plan=[
            FixRollbackStep(
                description="Restore default pool size.",
                trigger="Database reports connection exhaustion.",
                expected_result="Original pool size restored.",
            )
        ],
        evidence_references=[uuid.uuid4()],
        external_knowledge_references=[],
        confidence=0.95,
        change_scope="backend configuration only",
        generated_at=datetime.now(UTC),
        model_metadata=LLMObservability(
            provider="mock",
            model="mock-nemotron",
            attempts=1,
            duration_ms=10.0,
            input_tokens=100,
            output_tokens=50,
            estimated_cost_usd=0.001,
            budget_remaining_usd=1.999,
        ),
    )


def test_factory_registers_all_canonical_stages() -> None:
    """The operational orchestrator factory must register all 8 canonical stages."""
    orchestrator = create_operational_orchestrator()
    registered = [s.stage_id for s in orchestrator.registry.list()]

    assert registered == [
        StageIdentifier.INITIALIZE.value,
        StageIdentifier.COLLECT.value,
        StageIdentifier.ANALYZE.value,
        StageIdentifier.DIAGNOSE.value,
        StageIdentifier.PROPOSE.value,
        StageIdentifier.VERIFY.value,
        StageIdentifier.HUMAN_APPROVAL.value,
        StageIdentifier.COMPLETE.value,
    ]


def test_factory_agent_wiring_conditional_on_credentials() -> None:
    """Agents must only be wired if credentials or providers are explicitly provided."""
    # Without credentials/providers:
    no_agents_orchestrator = create_operational_orchestrator()
    collect_stage = no_agents_orchestrator.registry.get(StageIdentifier.COLLECT.value)
    assert len(collect_stage.agents) == 0

    # With credentials/providers:
    docker_inspector = FakeDockerInspector()
    monitoring_provider = FakeMonitoringProvider()
    wired_orchestrator = create_operational_orchestrator(
        github_access_token="ghp_mock_token_for_test",
        docker_inspector=docker_inspector,
        monitoring_provider=monitoring_provider,
    )
    collect_stage_wired = wired_orchestrator.registry.get(StageIdentifier.COLLECT.value)
    assert len(collect_stage_wired.agents) == 3
    agent_ids = {a.identifier for a in collect_stage_wired.agents}
    assert agent_ids == {"github_agent", "docker_agent", "monitoring_agent"}


@pytest.mark.asyncio
async def test_factory_degraded_mode_when_services_disabled() -> None:
    """Disabled LLM and knowledge search must execute without network calls and report degraded statuses."""
    config = Settings(
        llm_enabled=False,
        knowledge_search_enabled=False,
    )
    orchestrator = create_operational_orchestrator(config=config)
    context = _make_test_context()

    result = await orchestrator.execute(context)

    assert result.status == ExecutionStatus.SUCCESS
    analyze_stage = result.get_stage_result(StageIdentifier.ANALYZE.value)
    assert analyze_stage is not None
    assert analyze_stage.output_metadata.get("analysis_status") == "reasoning_disabled"

    diagnose_stage = result.get_stage_result(StageIdentifier.DIAGNOSE.value)
    assert diagnose_stage is not None
    assert diagnose_stage.output_metadata.get("diagnosis_status") == "disabled"

    propose_stage = result.get_stage_result(StageIdentifier.PROPOSE.value)
    assert propose_stage is not None
    assert propose_stage.output_metadata.get("fix_proposal_status") == "disabled"


@pytest.mark.asyncio
async def test_factory_wires_rca_and_fixes_to_injected_llm() -> None:
    """When an LLMService is injected, RCA and FixGenerator services must be wired."""
    mock_llm = MagicMock(spec=LLMService)
    mock_llm.reason = AsyncMock(
        return_value=ReasoningResponse(
            reasoning=StructuredReasoning(
                summary="mock reasoning",
                observations=[],
                uncertainties=[],
                follow_up_questions=[],
            ),
            metadata=LLMObservability(
                provider="mock",
                model="mock-nemotron",
                duration_ms=10.0,
                attempts=1,
                input_tokens=100,
                output_tokens=50,
                estimated_cost_usd=0.001,
                budget_remaining_usd=1.999,
            ),
        )
    )

    orchestrator = create_operational_orchestrator(llm_service=mock_llm)
    diagnose_stage = orchestrator.registry.get(StageIdentifier.DIAGNOSE.value)
    assert diagnose_stage.rca_service is not None
    assert diagnose_stage.rca_service._llm is mock_llm

    propose_stage = orchestrator.registry.get(StageIdentifier.PROPOSE.value)
    assert propose_stage.fix_generator_service is not None
    assert propose_stage.fix_generator_service._llm is mock_llm


@pytest.mark.asyncio
async def test_factory_preserves_human_approval_gate_unautomated(tmp_path: Path) -> None:
    """Even with passing verification, the pipeline stops at the human approval gate without auto-deploying."""
    context = _make_test_context()
    proposal = _make_test_proposal(context.investigation_id)

    source = tmp_path / "source"
    source.mkdir()
    (source / "app").mkdir()
    (source / "app" / "settings.py").write_text("db_pool_size = 5\n")

    fake_sandbox = FakeSandboxProvider(
        [SandboxExecution(exit_code=0, stdout="CHECKS_OK", stderr="", duration_ms=1)]
    )
    artifact_id = uuid.uuid4()
    recorder = AsyncMock(return_value=artifact_id)

    async def resolve_workspace(_ctx: InvestigationContext, _prop: FixProposal) -> Path:
        return source

    orchestrator = create_operational_orchestrator(
        sandbox_provider=fake_sandbox,
        sandbox_workspace_resolver=resolve_workspace,
        approval_artifact_recorder=recorder,
        verification_commands=[VerificationCommand(step_index=0, argv=["pytest", "-q"])],
    )

    context.fix_proposal = proposal

    result = await orchestrator.execute(context)

    assert result.status == ExecutionStatus.SUCCESS
    gate_stage = result.get_stage_result(StageIdentifier.HUMAN_APPROVAL.value)
    assert gate_stage is not None
    assert gate_stage.output_metadata.get("approval_status") == "awaiting_human_review"
    assert gate_stage.output_metadata.get("human_decision_required") is True
    assert gate_stage.output_metadata.get("approval_artifact_id") == str(artifact_id)
