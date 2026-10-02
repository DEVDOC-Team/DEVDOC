"""Standard investigation stages.

Implements the default investigation lifecycle stages for DEVDOC:
INITIALIZE → COLLECT → ANALYZE → DIAGNOSE → PROPOSE → VERIFY → COMPLETE

Note: Phase 10 establishes the orchestration contracts only. Actual agent implementations,
LLM reasoning (Phase 13), Tavily search (Phase 14), root-cause engine (Phase 15),
fix generator (Phase 16), and sandbox verification (Phase 17) belong to future phases.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

from orchestrator.contracts.agent import BaseAgent
from orchestrator.contracts.execution import FailurePolicy, WorkflowDefinition
from orchestrator.contracts.stage import BaseStage, StageIdentifier
from orchestrator.core.context import InvestigationContext
from orchestrator.core.result import AgentResult, ExecutionStatus, StageResult
from orchestrator.stages.registry import StageRegistry


class InitializeStage(BaseStage):
    """Initializes the investigation run and validates the execution context."""

    @property
    def stage_id(self) -> str:
        return StageIdentifier.INITIALIZE.value

    @property
    def name(self) -> str:
        return "Initialize Investigation"

    @property
    def description(self) -> str:
        return "Validates investigation context and sets up initial execution metadata."

    async def execute(self, context: InvestigationContext) -> StageResult:
        start_time = time.perf_counter()
        started_at = datetime.now(UTC)
        context.record_stage_start(self.stage_id)

        try:
            context.validate()
            output_meta: dict[str, Any] = {
                "investigation_id": str(context.investigation_id),
                "incident_id": str(context.incident_id),
                "project_id": str(context.project_id),
                "execution_id": str(context.execution_id),
                "initialization_status": "initialized",
            }
            context.record_stage_complete(self.stage_id)
            duration_ms = (time.perf_counter() - start_time) * 1000.0

            return StageResult(
                stage_id=self.stage_id,
                status=ExecutionStatus.SUCCESS,
                output_metadata=output_meta,
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_ms=duration_ms,
            )
        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            return StageResult(
                stage_id=self.stage_id,
                status=ExecutionStatus.FAILED,
                error_message=str(exc),
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_ms=duration_ms,
            )


class CollectEvidenceStage(BaseStage):
    """Evidence collection stage coordinating operational investigation agents."""

    def __init__(self, agents: list[BaseAgent] | None = None) -> None:
        self.agents: list[BaseAgent] = agents or []

    @property
    def stage_id(self) -> str:
        return StageIdentifier.COLLECT.value

    @property
    def name(self) -> str:
        return "Collect Evidence"

    @property
    def description(self) -> str:
        return "Coordinates evidence collection from logs, telemetry, containers, and source control."

    async def execute(self, context: InvestigationContext) -> StageResult:
        start_time = time.perf_counter()
        started_at = datetime.now(UTC)
        context.record_stage_start(self.stage_id)

        agent_results: list[AgentResult] = []
        warnings: list[str] = []
        errors: list[str] = []
        has_failure = False

        for agent in self.agents:
            if context.is_cancelled():
                warnings.append(
                    f"Evidence collection cancelled before executing agent '{agent.identifier}'"
                )
                break

            agent_start = time.perf_counter()
            agent_started_at = datetime.now(UTC)
            try:
                res = await agent.execute(context)
            except Exception as exc:
                agent_duration = (time.perf_counter() - agent_start) * 1000.0
                err_text = f"Unhandled exception in agent '{agent.identifier}': {exc}"
                errors.append(err_text)
                res = AgentResult(
                    agent_id=agent.identifier,
                    status=ExecutionStatus.FAILED,
                    investigation_id=context.investigation_id,
                    execution_id=context.execution_id,
                    error_message=err_text,
                    errors=[err_text],
                    started_at=agent_started_at,
                    completed_at=datetime.now(UTC),
                    duration_ms=agent_duration,
                )

            agent_results.append(res)
            if res.status == ExecutionStatus.FAILED:
                has_failure = True
                if res.error_message:
                    errors.append(res.error_message)
            if res.warnings:
                warnings.extend(res.warnings)

        output_meta: dict[str, Any] = {
            "evidence_collection_status": "completed" if self.agents else "ready_for_phase11_agents",
            "evidence_reference_count": len(context.collected_evidence_references),
            "agents_executed": [a.agent_id for a in agent_results],
            "agents_count": len(agent_results),
            "successful_agents": len(
                [a for a in agent_results if a.status == ExecutionStatus.SUCCESS]
            ),
        }
        context.record_stage_complete(self.stage_id)
        duration_ms = (time.perf_counter() - start_time) * 1000.0

        stage_status = ExecutionStatus.FAILED if has_failure else ExecutionStatus.SUCCESS
        err_msg = "; ".join(errors) if errors else None

        return StageResult(
            stage_id=self.stage_id,
            status=stage_status,
            output_metadata=output_meta,
            agent_results=agent_results,
            warnings=warnings,
            error_message=err_msg,
            started_at=started_at,
            completed_at=datetime.now(UTC),
            duration_ms=duration_ms,
        )



class AnalyzeStage(BaseStage):
    """Reasoning and telemetry analysis contract stage (future Phase 13 & 14)."""

    @property
    def stage_id(self) -> str:
        return StageIdentifier.ANALYZE.value

    @property
    def name(self) -> str:
        return "Analyze Telemetry & Logs"

    @property
    def description(self) -> str:
        return "Performs multi-modal reasoning across collected evidence."

    async def execute(self, context: InvestigationContext) -> StageResult:
        start_time = time.perf_counter()
        started_at = datetime.now(UTC)
        context.record_stage_start(self.stage_id)

        output_meta: dict[str, Any] = {
            "analysis_status": "ready_for_phase13_reasoning",
        }
        context.record_stage_complete(self.stage_id)
        duration_ms = (time.perf_counter() - start_time) * 1000.0

        return StageResult(
            stage_id=self.stage_id,
            status=ExecutionStatus.SUCCESS,
            output_metadata=output_meta,
            started_at=started_at,
            completed_at=datetime.now(UTC),
            duration_ms=duration_ms,
        )


class DiagnoseStage(BaseStage):
    """Root cause diagnosis contract stage (future Phase 15)."""

    @property
    def stage_id(self) -> str:
        return StageIdentifier.DIAGNOSE.value

    @property
    def name(self) -> str:
        return "Diagnose Root Cause"

    @property
    def description(self) -> str:
        return "Synthesizes diagnostic hypotheses to pinpoint outage root cause."

    async def execute(self, context: InvestigationContext) -> StageResult:
        start_time = time.perf_counter()
        started_at = datetime.now(UTC)
        context.record_stage_start(self.stage_id)

        output_meta: dict[str, Any] = {
            "diagnosis_status": "ready_for_phase15_root_cause",
        }
        context.record_stage_complete(self.stage_id)
        duration_ms = (time.perf_counter() - start_time) * 1000.0

        return StageResult(
            stage_id=self.stage_id,
            status=ExecutionStatus.SUCCESS,
            output_metadata=output_meta,
            started_at=started_at,
            completed_at=datetime.now(UTC),
            duration_ms=duration_ms,
        )


class ProposeFixStage(BaseStage):
    """Fix proposal generation contract stage (future Phase 16)."""

    @property
    def stage_id(self) -> str:
        return StageIdentifier.PROPOSE.value

    @property
    def name(self) -> str:
        return "Propose Fix"

    @property
    def description(self) -> str:
        return "Generates prospective code or configuration fixes for the diagnosed fault."

    async def execute(self, context: InvestigationContext) -> StageResult:
        start_time = time.perf_counter()
        started_at = datetime.now(UTC)
        context.record_stage_start(self.stage_id)

        output_meta: dict[str, Any] = {
            "fix_proposal_status": "ready_for_phase16_fix_generator",
        }
        context.record_stage_complete(self.stage_id)
        duration_ms = (time.perf_counter() - start_time) * 1000.0

        return StageResult(
            stage_id=self.stage_id,
            status=ExecutionStatus.SUCCESS,
            output_metadata=output_meta,
            started_at=started_at,
            completed_at=datetime.now(UTC),
            duration_ms=duration_ms,
        )


class VerifyStage(BaseStage):
    """Sandbox verification contract stage (future Phase 17)."""

    @property
    def stage_id(self) -> str:
        return StageIdentifier.VERIFY.value

    @property
    def name(self) -> str:
        return "Verify in Sandbox"

    @property
    def description(self) -> str:
        return "Validates the proposed fix inside an isolated ephemeral sandbox environment."

    async def execute(self, context: InvestigationContext) -> StageResult:
        start_time = time.perf_counter()
        started_at = datetime.now(UTC)
        context.record_stage_start(self.stage_id)

        output_meta: dict[str, Any] = {
            "verification_status": "ready_for_phase17_sandbox",
        }
        context.record_stage_complete(self.stage_id)
        duration_ms = (time.perf_counter() - start_time) * 1000.0

        return StageResult(
            stage_id=self.stage_id,
            status=ExecutionStatus.SUCCESS,
            output_metadata=output_meta,
            started_at=started_at,
            completed_at=datetime.now(UTC),
            duration_ms=duration_ms,
        )


class CompleteStage(BaseStage):
    """Investigation completion and finalization stage."""

    @property
    def stage_id(self) -> str:
        return StageIdentifier.COMPLETE.value

    @property
    def name(self) -> str:
        return "Complete Investigation"

    @property
    def description(self) -> str:
        return "Finalizes investigation state and synthesizes summary metrics."

    async def execute(self, context: InvestigationContext) -> StageResult:
        start_time = time.perf_counter()
        started_at = datetime.now(UTC)
        context.record_stage_start(self.stage_id)

        output_meta: dict[str, Any] = {
            "completion_status": "finalized",
            "total_warnings": len(context.warnings),
            "total_errors": len(context.errors),
        }
        context.record_stage_complete(self.stage_id)
        duration_ms = (time.perf_counter() - start_time) * 1000.0

        return StageResult(
            stage_id=self.stage_id,
            status=ExecutionStatus.SUCCESS,
            output_metadata=output_meta,
            started_at=started_at,
            completed_at=datetime.now(UTC),
            duration_ms=duration_ms,
        )


def create_default_stage_registry() -> StageRegistry:
    """Build a StageRegistry pre-populated with all 7 canonical investigation stages."""
    registry = StageRegistry()
    registry.register(InitializeStage())
    registry.register(CollectEvidenceStage())
    registry.register(AnalyzeStage())
    registry.register(DiagnoseStage())
    registry.register(ProposeFixStage())
    registry.register(VerifyStage())
    registry.register(CompleteStage())
    return registry


def create_default_workflow() -> WorkflowDefinition:
    """Build the canonical default investigation workflow definition."""
    return WorkflowDefinition(
        workflow_id="default_investigation",
        name="Default Investigation Pipeline",
        description="Standard 7-stage DEVDOC root cause investigation workflow",
        stage_ids=[
            StageIdentifier.INITIALIZE.value,
            StageIdentifier.COLLECT.value,
            StageIdentifier.ANALYZE.value,
            StageIdentifier.DIAGNOSE.value,
            StageIdentifier.PROPOSE.value,
            StageIdentifier.VERIFY.value,
            StageIdentifier.COMPLETE.value,
        ],
        failure_policy=FailurePolicy.FAIL_FAST,
    )


def create_operational_stage_registry(
    github_agent: BaseAgent | None = None,
    docker_agent: BaseAgent | None = None,
    monitoring_agent: BaseAgent | None = None,
) -> StageRegistry:
    """Build a StageRegistry configured with operational investigation agents."""
    agents: list[BaseAgent] = []
    if github_agent is not None:
        agents.append(github_agent)
    if docker_agent is not None:
        agents.append(docker_agent)
    if monitoring_agent is not None:
        agents.append(monitoring_agent)

    registry = StageRegistry()
    registry.register(InitializeStage())
    registry.register(CollectEvidenceStage(agents=agents))
    registry.register(AnalyzeStage())
    registry.register(DiagnoseStage())
    registry.register(ProposeFixStage())
    registry.register(VerifyStage())
    registry.register(CompleteStage())
    return registry

