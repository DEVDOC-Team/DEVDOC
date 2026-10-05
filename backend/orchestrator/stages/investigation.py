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
from orchestrator.evidence.engine import EvidenceEngine
from orchestrator.knowledge.service import KnowledgeSearchError, KnowledgeSearchService
from orchestrator.llm.service import LLMService, LLMServiceError
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
        self.evidence_engine = EvidenceEngine()

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
            "evidence_collection_status": "completed" if self.agents else "completed_without_agents",
            "evidence_reference_count": len(context.collected_evidence_references),
            "agents_executed": [a.agent_id for a in agent_results],
            "agents_count": len(agent_results),
            "successful_agents": len(
                [a for a in agent_results if a.status == ExecutionStatus.SUCCESS]
            ),
        }
        evidence_collection = self.evidence_engine.process(agent_results, context)
        context.evidence_collection = evidence_collection
        output_meta["evidence_item_count"] = evidence_collection.summary.total_evidence_count
        output_meta["evidence_timeline_count"] = len(evidence_collection.timeline)
        output_meta["evidence_correlation_count"] = len(evidence_collection.correlations)
        output_meta["evidence_duplicate_count"] = evidence_collection.summary.duplicate_count
        for warning in evidence_collection.warnings:
            context.add_warning(warning)
            if warning not in warnings:
                warnings.append(warning)
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
            evidence_collection=evidence_collection.to_dict(),
            started_at=started_at,
            completed_at=datetime.now(UTC),
            duration_ms=duration_ms,
        )



class AnalyzeStage(BaseStage):
    """Evidence reasoning stage; provider use requires explicit service injection."""

    def __init__(
        self,
        llm_service: LLMService | None = None,
        knowledge_search_service: KnowledgeSearchService | None = None,
    ) -> None:
        self.llm_service = llm_service
        self.knowledge_search_service = knowledge_search_service

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
            "analysis_status": "reasoning_disabled",
            "knowledge_search_status": (
                "disabled" if self.knowledge_search_service is None else "pending"
            ),
        }
        status = ExecutionStatus.SUCCESS
        error_message: str | None = None
        if (
            self.knowledge_search_service is not None
            and context.evidence_collection is not None
            and context.evidence_collection.items
        ):
            try:
                search_result, updated_evidence = (
                    await self.knowledge_search_service.search_investigation(
                        context,
                        context.evidence_collection,
                    )
                )
            except KnowledgeSearchError as exc:
                status = ExecutionStatus.FAILED
                error_message = str(exc)
                output_meta["knowledge_search_status"] = "unavailable"
                context.add_warning("External knowledge search was unavailable")
            else:
                output_meta["knowledge_search_status"] = (
                    "completed" if search_result.results else "completed_no_results"
                )
                output_meta["knowledge_search"] = {
                    "provider": search_result.provider,
                    "query": search_result.query,
                    "result_count": search_result.total_results,
                    "evidence_ids": [
                        str(item.evidence_id)
                        for item in updated_evidence.items
                        if item.evidence_type.value == "external_knowledge"
                    ],
                    "duration_ms": search_result.metadata.duration_ms,
                    "attempts": search_result.metadata.attempts,
                    "cache_hit": search_result.metadata.cache_hit,
                }
        elif self.knowledge_search_service is not None:
            output_meta["knowledge_search_status"] = "skipped_no_evidence"

        if (
            self.llm_service is not None
            and context.evidence_collection is not None
            and context.evidence_collection.items
            and output_meta["knowledge_search_status"] not in {"pending", "unavailable"}
        ):
            try:
                response = await self.llm_service.reason(context.evidence_collection)
            except LLMServiceError as exc:
                status = ExecutionStatus.FAILED
                error_message = str(exc)
                output_meta["analysis_status"] = "failed"
            else:
                output_meta["analysis_status"] = "completed"
                output_meta["reasoning"] = response.reasoning.model_dump(mode="json")
                output_meta["llm_metadata"] = response.metadata.model_dump(mode="json")
        elif self.llm_service is not None:
            output_meta["analysis_status"] = (
                "skipped_knowledge_search_failure"
                if output_meta["knowledge_search_status"] == "unavailable"
                else "skipped_no_evidence"
            )
        context.record_stage_complete(self.stage_id)
        duration_ms = (time.perf_counter() - start_time) * 1000.0

        return StageResult(
            stage_id=self.stage_id,
            status=status,
            output_metadata=output_meta,
            error_message=error_message,
            evidence_collection=(
                context.evidence_collection.to_dict()
                if self.knowledge_search_service is not None
                and context.evidence_collection is not None
                else None
            ),
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


def create_default_stage_registry(
    llm_service: LLMService | None = None,
    knowledge_search_service: KnowledgeSearchService | None = None,
) -> StageRegistry:
    """Build a StageRegistry pre-populated with all 7 canonical investigation stages."""
    registry = StageRegistry()
    registry.register(InitializeStage())
    registry.register(CollectEvidenceStage())
    registry.register(
        AnalyzeStage(
            llm_service=llm_service,
            knowledge_search_service=knowledge_search_service,
        )
    )
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
    llm_service: LLMService | None = None,
    knowledge_search_service: KnowledgeSearchService | None = None,
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
    registry.register(
        AnalyzeStage(
            llm_service=llm_service,
            knowledge_search_service=knowledge_search_service,
        )
    )
    registry.register(DiagnoseStage())
    registry.register(ProposeFixStage())
    registry.register(VerifyStage())
    registry.register(CompleteStage())
    return registry
