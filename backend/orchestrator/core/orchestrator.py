"""DEVDOC Orchestrator.

Central engine coordinating investigation stages, contexts, and workflow policies
in a deterministic, auditable, and secure manner.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import Any

from orchestrator.contracts.execution import FailurePolicy, WorkflowDefinition
from orchestrator.core.context import InvestigationContext
from orchestrator.core.errors import ContextValidationError
from orchestrator.core.result import (
    ExecutionStatus,
    OrchestrationResult,
    StageResult,
)
from orchestrator.llm.service import LLMService
from orchestrator.stages.investigation import (
    create_default_stage_registry,
    create_default_workflow,
)
from orchestrator.stages.registry import StageRegistry

logger = logging.getLogger("devdoc.orchestrator")


class DEVDOCOrchestrator:
    """Foundational orchestrator coordinating DEVDOC AI investigations.

    Guarantees:
    1. Deterministic sequential stage execution.
    2. Strict context validation before any stage runs.
    3. FAIL_FAST stopping of downstream stages on critical failure.
    4. Cooperative non-destructive cancellation support.
    5. Zero production access, shell execution, or external AI/LLM network calls in Phase 10.
    """

    def __init__(
        self,
        registry: StageRegistry | None = None,
        workflow: WorkflowDefinition | None = None,
        *,
        llm_service: LLMService | None = None,
    ) -> None:
        self.registry = (
            registry
            if registry is not None
            else create_default_stage_registry(llm_service=llm_service)
        )
        self.workflow = workflow if workflow is not None else create_default_workflow()

    async def execute(self, context: InvestigationContext) -> OrchestrationResult:
        """Execute the configured investigation workflow against the provided context.

        Args:
            context: Validated investigation context containing investigation/incident/project IDs.

        Returns:
            OrchestrationResult containing stage results, status, warnings, and duration.
        """
        start_time = time.perf_counter()
        started_at = datetime.now(UTC)

        # 1. Context validation
        try:
            context.validate()
        except ContextValidationError as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            logger.error(
                "Investigation context validation failed",
                extra={
                    "investigation_id": str(getattr(context, "investigation_id", "unknown")),
                    "error": str(exc),
                },
            )
            return OrchestrationResult(
                execution_id=getattr(context, "execution_id", None) or context.execution_id,
                investigation_id=getattr(context, "investigation_id", None) or context.investigation_id,
                incident_id=getattr(context, "incident_id", None) or context.incident_id,
                project_id=getattr(context, "project_id", None) or context.project_id,
                workflow_id=self.workflow.workflow_id,
                status=ExecutionStatus.FAILED,
                error_message=f"Context validation failed: {exc}",
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_ms=duration_ms,
            )

        # 2. Check initial cancellation
        if context.is_cancelled():
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            return OrchestrationResult(
                execution_id=context.execution_id,
                investigation_id=context.investigation_id,
                incident_id=context.incident_id,
                project_id=context.project_id,
                workflow_id=self.workflow.workflow_id,
                status=ExecutionStatus.CANCELLED,
                error_message=context.cancellation_token.reason or "Investigation cancelled prior to execution",
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_ms=duration_ms,
            )

        # 3. Validate that all workflow stages exist in registry
        for sid in self.workflow.stage_ids:
            if not self.registry.contains(sid):
                duration_ms = (time.perf_counter() - start_time) * 1000.0
                err_msg = f"Workflow '{self.workflow.workflow_id}' references unregistered stage '{sid}'"
                logger.error(err_msg)
                return OrchestrationResult(
                    execution_id=context.execution_id,
                    investigation_id=context.investigation_id,
                    incident_id=context.incident_id,
                    project_id=context.project_id,
                    workflow_id=self.workflow.workflow_id,
                    status=ExecutionStatus.FAILED,
                    error_message=err_msg,
                    started_at=started_at,
                    completed_at=datetime.now(UTC),
                    duration_ms=duration_ms,
                )

        stage_results: list[StageResult] = []
        overall_status = ExecutionStatus.SUCCESS
        final_error_message: str | None = None

        logger.info(
            "Starting investigation workflow",
            extra={
                "execution_id": str(context.execution_id),
                "investigation_id": str(context.investigation_id),
                "workflow_id": self.workflow.workflow_id,
                "stages_count": len(self.workflow.stage_ids),
            },
        )

        # 4. Sequential stage execution
        for stage_id in self.workflow.stage_ids:
            # Check for cancellation before executing each stage
            if context.is_cancelled():
                overall_status = ExecutionStatus.CANCELLED
                final_error_message = (
                    context.cancellation_token.reason
                    or f"Investigation cancelled before stage '{stage_id}'"
                )
                logger.info(
                    "Investigation execution cancelled",
                    extra={
                        "execution_id": str(context.execution_id),
                        "stage_id": stage_id,
                    },
                )
                break

            stage = self.registry.get(stage_id)
            stage_start = time.perf_counter()
            stage_started_at = datetime.now(UTC)

            try:
                stage_result = await stage.execute(context)
            except Exception as exc:
                stage_duration_ms = (time.perf_counter() - stage_start) * 1000.0
                err_text = f"Unhandled exception in stage '{stage_id}': {exc}"
                logger.exception(
                    "Stage execution raised an unhandled exception",
                    extra={
                        "execution_id": str(context.execution_id),
                        "stage_id": stage_id,
                    },
                )
                stage_result = StageResult(
                    stage_id=stage_id,
                    status=ExecutionStatus.FAILED,
                    error_message=err_text,
                    started_at=stage_started_at,
                    completed_at=datetime.now(UTC),
                    duration_ms=stage_duration_ms,
                )

            stage_results.append(stage_result)

            if stage_result.status == ExecutionStatus.FAILED:
                context.add_error(f"Stage '{stage_id}' failed: {stage_result.error_message}")
                if self.workflow.failure_policy == FailurePolicy.FAIL_FAST:
                    overall_status = ExecutionStatus.FAILED
                    final_error_message = (
                        f"Stage '{stage_id}' failed: {stage_result.error_message}"
                    )
                    logger.warning(
                        "Fail-fast triggered; halting subsequent stages",
                        extra={
                            "execution_id": str(context.execution_id),
                            "failed_stage": stage_id,
                        },
                    )
                    break

        duration_ms = (time.perf_counter() - start_time) * 1000.0
        completed_at = datetime.now(UTC)

        execution_meta: dict[str, Any] = {
            "executed_stages": [s.stage_id for s in stage_results],
            "total_stages_in_workflow": len(self.workflow.stage_ids),
            "stages_completed": len([s for s in stage_results if s.status == ExecutionStatus.SUCCESS]),
            "failure_policy": self.workflow.failure_policy.value,
        }

        logger.info(
            "Investigation workflow completed",
            extra={
                "execution_id": str(context.execution_id),
                "investigation_id": str(context.investigation_id),
                "status": overall_status.value,
                "duration_ms": duration_ms,
            },
        )

        return OrchestrationResult(
            execution_id=context.execution_id,
            investigation_id=context.investigation_id,
            incident_id=context.incident_id,
            project_id=context.project_id,
            workflow_id=self.workflow.workflow_id,
            status=overall_status,
            stage_results=stage_results,
            metadata=execution_meta,
            warnings=list(context.warnings),
            error_message=final_error_message,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=duration_ms,
        )
