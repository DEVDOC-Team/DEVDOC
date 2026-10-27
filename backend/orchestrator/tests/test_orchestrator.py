"""Comprehensive tests for DEVDOCOrchestrator.

Validates:
- Initialization and workflow discovery
- Deterministic sequential execution
- Stage failure handling and FAIL_FAST behavior
- Non-execution of downstream stages after critical failure
- Cooperative cancellation behavior
- Context validation and propagation
- Execution ID generation and tracking
- Mock agent integration and error propagation
- Zero external network requests (isolated execution)
- Zero AI provider credits or calls
- Clean sanitized logging without credentials
"""

from __future__ import annotations

import logging
import socket
import uuid
from typing import Any

import pytest

from orchestrator.agents.base import MockInvestigationAgent
from orchestrator.contracts.execution import FailurePolicy, WorkflowDefinition
from orchestrator.contracts.stage import BaseStage, StageIdentifier
from orchestrator.core.context import InvestigationContext
from orchestrator.core.errors import ContextValidationError
from orchestrator.core.orchestrator import DEVDOCOrchestrator
from orchestrator.core.result import ExecutionStatus, StageResult
from orchestrator.stages.investigation import (
    create_default_stage_registry,
    create_default_workflow,
)
from orchestrator.stages.registry import StageRegistry


class TrackingStage(BaseStage):
    """Stage that records execution order into a shared list."""

    def __init__(
        self,
        sid: str,
        execution_order: list[str],
        should_fail: bool = False,
        error_msg: str | None = None,
        raise_exc: Exception | None = None,
    ) -> None:
        self._sid = sid
        self.execution_order = execution_order
        self.should_fail = should_fail
        self.error_msg = error_msg or f"Failure in {sid}"
        self.raise_exc = raise_exc

    @property
    def stage_id(self) -> str:
        return self._sid

    @property
    def name(self) -> str:
        return f"Tracking Stage {self._sid}"

    async def execute(self, context: InvestigationContext) -> StageResult:
        self.execution_order.append(self._sid)
        if self.raise_exc:
            raise self.raise_exc
        if self.should_fail:
            return StageResult(
                stage_id=self._sid,
                status=ExecutionStatus.FAILED,
                error_message=self.error_msg,
            )
        return StageResult(
            stage_id=self._sid,
            status=ExecutionStatus.SUCCESS,
            output_metadata={"executed": self._sid},
        )


class AgentInvokingStage(BaseStage):
    """Stage that delegates work to a BaseAgent."""

    def __init__(self, sid: str, agent: MockInvestigationAgent) -> None:
        self._sid = sid
        self.agent = agent

    @property
    def stage_id(self) -> str:
        return self._sid

    @property
    def name(self) -> str:
        return f"Agent Stage {self._sid}"

    async def execute(self, context: InvestigationContext) -> StageResult:
        agent_res = await self.agent.execute(context)
        if agent_res.status == ExecutionStatus.FAILED:
            return StageResult(
                stage_id=self._sid,
                status=ExecutionStatus.FAILED,
                error_message=agent_res.error_message,
                agent_results=[agent_res],
            )
        return StageResult(
            stage_id=self._sid,
            status=ExecutionStatus.SUCCESS,
            output_metadata=agent_res.output_metadata,
            agent_results=[agent_res],
        )


@pytest.fixture
def valid_context() -> InvestigationContext:
    return InvestigationContext(
        investigation_id=uuid.uuid4(),
        incident_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        initiated_by_id=uuid.uuid4(),
    )


# 1. Orchestrator initializes
def test_orchestrator_initializes_with_defaults() -> None:
    orch = DEVDOCOrchestrator()
    assert orch.registry is not None
    assert len(orch.registry) == 8
    assert orch.workflow.workflow_id == "default_investigation"
    assert len(orch.workflow.stage_ids) == 8


def test_orchestrator_initializes_with_custom_registry_and_workflow() -> None:
    reg = StageRegistry()
    dummy = TrackingStage("custom_stage", [])
    reg.register(dummy)
    wf = WorkflowDefinition(
        workflow_id="custom_pipeline",
        name="Custom Pipeline",
        stage_ids=["custom_stage"],
    )
    orch = DEVDOCOrchestrator(registry=reg, workflow=wf)
    assert orch.registry.contains("custom_stage")
    assert orch.workflow.workflow_id == "custom_pipeline"


# 2. Context validation works
@pytest.mark.asyncio
async def test_context_validation_failure_stops_orchestration() -> None:
    orch = DEVDOCOrchestrator()
    # Create context with valid fields, then corrupt one to test execute-time catch
    ctx = InvestigationContext(
        investigation_id=uuid.uuid4(),
        incident_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
    )
    ctx.execution_metadata["leaked_token"] = "raw_secret"

    result = await orch.execute(ctx)
    assert result.status == ExecutionStatus.FAILED
    assert "Context validation failed" in (result.error_message or "")
    assert len(result.stage_results) == 0


# 7 & 8 & 9. Workflow ordering, sequential execution, successful stage execution
@pytest.mark.asyncio
async def test_default_investigation_sequential_execution(
    valid_context: InvestigationContext,
) -> None:
    orch = DEVDOCOrchestrator()
    result = await orch.execute(valid_context)

    assert result.status == ExecutionStatus.SUCCESS
    assert result.is_successful
    assert result.execution_id == valid_context.execution_id
    assert result.investigation_id == valid_context.investigation_id
    assert result.incident_id == valid_context.incident_id
    assert result.project_id == valid_context.project_id
    assert result.workflow_id == "default_investigation"
    assert result.duration_ms >= 0.0
    assert result.started_at is not None
    assert result.completed_at is not None

    expected_stages = [
        StageIdentifier.INITIALIZE.value,
        StageIdentifier.COLLECT.value,
        StageIdentifier.ANALYZE.value,
        StageIdentifier.DIAGNOSE.value,
        StageIdentifier.PROPOSE.value,
        StageIdentifier.VERIFY.value,
        StageIdentifier.HUMAN_APPROVAL.value,
        StageIdentifier.COMPLETE.value,
    ]
    assert [s.stage_id for s in result.stage_results] == expected_stages
    for s in result.stage_results:
        if s.stage_id == StageIdentifier.HUMAN_APPROVAL.value:
            assert s.status == ExecutionStatus.SKIPPED
            continue
        assert s.status == ExecutionStatus.SUCCESS
        assert s.is_successful
        assert s.duration_ms >= 0.0

    # Verify context timestamps were recorded
    for sid in expected_stages:
        assert f"{sid}_start" in valid_context.execution_timestamps
        assert f"{sid}_end" in valid_context.execution_timestamps


# 6. Unknown stage detection works
@pytest.mark.asyncio
async def test_unknown_stage_in_workflow_rejected(
    valid_context: InvestigationContext,
) -> None:
    reg = StageRegistry()
    wf = WorkflowDefinition(
        workflow_id="broken_wf",
        name="Broken Workflow",
        stage_ids=["missing_stage_xyz"],
    )
    orch = DEVDOCOrchestrator(registry=reg, workflow=wf)
    result = await orch.execute(valid_context)

    assert result.status == ExecutionStatus.FAILED
    assert "references unregistered stage 'missing_stage_xyz'" in (result.error_message or "")
    assert len(result.stage_results) == 0


# 10, 11 & 17. Failed stage execution, FAIL_FAST, and no downstream stages execute
@pytest.mark.asyncio
async def test_fail_fast_halts_downstream_stages(
    valid_context: InvestigationContext,
) -> None:
    execution_order: list[str] = []
    reg = StageRegistry()
    reg.register(TrackingStage("stage_1", execution_order))
    reg.register(TrackingStage("stage_2", execution_order, should_fail=True, error_msg="Database error"))
    reg.register(TrackingStage("stage_3", execution_order))

    wf = WorkflowDefinition(
        workflow_id="fail_fast_wf",
        name="Fail Fast Pipeline",
        stage_ids=["stage_1", "stage_2", "stage_3"],
        failure_policy=FailurePolicy.FAIL_FAST,
    )
    orch = DEVDOCOrchestrator(registry=reg, workflow=wf)
    result = await orch.execute(valid_context)

    assert result.status == ExecutionStatus.FAILED
    assert not result.is_successful
    assert "Database error" in (result.error_message or "")

    # Only stage_1 and stage_2 ran; stage_3 MUST NOT run
    assert execution_order == ["stage_1", "stage_2"]
    assert len(result.stage_results) == 2
    assert result.stage_results[0].status == ExecutionStatus.SUCCESS
    assert result.stage_results[1].status == ExecutionStatus.FAILED
    assert result.get_stage_result("stage_3") is None
    assert any("Database error" in err for err in valid_context.errors)


@pytest.mark.asyncio
async def test_unhandled_exception_in_stage_caught_gracefully(
    valid_context: InvestigationContext,
) -> None:
    execution_order: list[str] = []
    reg = StageRegistry()
    reg.register(TrackingStage("stage_1", execution_order))
    reg.register(TrackingStage("stage_2", execution_order, raise_exc=RuntimeError("Unexpected crash")))
    reg.register(TrackingStage("stage_3", execution_order))

    wf = WorkflowDefinition(
        workflow_id="crash_wf",
        name="Crash Pipeline",
        stage_ids=["stage_1", "stage_2", "stage_3"],
        failure_policy=FailurePolicy.FAIL_FAST,
    )
    orch = DEVDOCOrchestrator(registry=reg, workflow=wf)
    result = await orch.execute(valid_context)

    assert result.status == ExecutionStatus.FAILED
    assert "Unexpected crash" in (result.error_message or "")
    assert execution_order == ["stage_1", "stage_2"]
    assert len(result.stage_results) == 2


# 12. Cancellation behavior works
@pytest.mark.asyncio
async def test_cancellation_prior_to_execution(
    valid_context: InvestigationContext,
) -> None:
    orch = DEVDOCOrchestrator()
    valid_context.cancel("Operator aborted before start")

    result = await orch.execute(valid_context)
    assert result.status == ExecutionStatus.CANCELLED
    assert result.error_message == "Operator aborted before start"
    assert len(result.stage_results) == 0


@pytest.mark.asyncio
async def test_cancellation_mid_execution(
    valid_context: InvestigationContext,
) -> None:
    class CancellingStage(BaseStage):
        @property
        def stage_id(self) -> str:
            return "cancelling_stage"

        @property
        def name(self) -> str:
            return "Cancelling Stage"

        async def execute(self, context: InvestigationContext) -> StageResult:
            context.cancel("Aborted mid-investigation")
            return StageResult(stage_id=self.stage_id, status=ExecutionStatus.SUCCESS)

    order: list[str] = []
    reg = StageRegistry()
    reg.register(CancellingStage())
    reg.register(TrackingStage("downstream_stage", order))

    wf = WorkflowDefinition(
        workflow_id="cancel_wf",
        name="Cancellation Pipeline",
        stage_ids=["cancelling_stage", "downstream_stage"],
    )
    orch = DEVDOCOrchestrator(registry=reg, workflow=wf)
    result = await orch.execute(valid_context)

    assert result.status == ExecutionStatus.CANCELLED
    assert result.error_message == "Aborted mid-investigation"
    assert len(result.stage_results) == 1
    assert result.stage_results[0].stage_id == "cancelling_stage"
    # downstream stage MUST NOT run
    assert order == []


# 14. Execution ID is generated/propagated
def test_execution_id_propagates(valid_context: InvestigationContext) -> None:
    assert isinstance(valid_context.execution_id, uuid.UUID)


# 15 & 16. Mock agent works and agent failure is propagated correctly
@pytest.mark.asyncio
async def test_mock_agent_success_in_orchestration(
    valid_context: InvestigationContext,
) -> None:
    agent = MockInvestigationAgent(
        identifier="agent_metrics",
        output_metadata={"cpu_spike": True},
    )
    reg = StageRegistry()
    reg.register(AgentInvokingStage("collect_metrics", agent))

    wf = WorkflowDefinition(
        workflow_id="agent_wf",
        name="Agent Workflow",
        stage_ids=["collect_metrics"],
    )
    orch = DEVDOCOrchestrator(registry=reg, workflow=wf)
    result = await orch.execute(valid_context)

    assert result.status == ExecutionStatus.SUCCESS
    assert agent.execution_count == 1
    assert valid_context.agent_outputs["agent_metrics"] == {"cpu_spike": True}


@pytest.mark.asyncio
async def test_mock_agent_failure_propagates_to_orchestrator(
    valid_context: InvestigationContext,
) -> None:
    agent = MockInvestigationAgent(
        identifier="agent_logs",
        should_fail=True,
        error_message="Log endpoint unavailable",
    )
    reg = StageRegistry()
    reg.register(AgentInvokingStage("collect_logs", agent))

    wf = WorkflowDefinition(
        workflow_id="agent_fail_wf",
        name="Agent Failure Workflow",
        stage_ids=["collect_logs"],
        failure_policy=FailurePolicy.FAIL_FAST,
    )
    orch = DEVDOCOrchestrator(registry=reg, workflow=wf)
    result = await orch.execute(valid_context)

    assert result.status == ExecutionStatus.FAILED
    assert "Log endpoint unavailable" in (result.error_message or "")
    stage_res = result.get_stage_result("collect_logs")
    assert stage_res is not None
    assert stage_res.status == ExecutionStatus.FAILED
    assert len(stage_res.agent_results) == 1
    assert stage_res.agent_results[0].status == ExecutionStatus.FAILED


# 18. Deterministic execution works
@pytest.mark.asyncio
async def test_deterministic_execution_order() -> None:
    orch = DEVDOCOrchestrator()
    for _ in range(3):
        ctx = InvestigationContext(
            investigation_id=uuid.uuid4(),
            incident_id=uuid.uuid4(),
            project_id=uuid.uuid4(),
        )
        res = await orch.execute(ctx)
        stages = [s.stage_id for s in res.stage_results]
        assert stages == [
            "initialize",
            "collect",
            "analyze",
            "diagnose",
            "propose",
            "verify",
            "human_approval",
            "complete",
        ]


# 19 & 20. No external network calls occur; No AI provider is contacted ($0 cost)
@pytest.mark.asyncio
async def test_no_external_network_calls_during_orchestration(
    valid_context: InvestigationContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Guarantee that external socket connections are strictly prevented during execution."""
    original_connect = socket.socket.connect

    def disallowed_connect(sock_self: Any, address: Any, *args: Any, **kwargs: Any) -> Any:
        # Allow internal loopback used by Windows asyncio ProactorEventLoop self-pipe
        if isinstance(address, tuple) and len(address) >= 1:
            host = address[0]
            if host in ("127.0.0.1", "::1", "localhost"):
                return original_connect(sock_self, address, *args, **kwargs)
        raise AssertionError(f"Unexpected outbound network call attempted to {address} during orchestration!")

    monkeypatch.setattr(socket.socket, "connect", disallowed_connect)

    orch = DEVDOCOrchestrator()
    result = await orch.execute(valid_context)
    assert result.status == ExecutionStatus.SUCCESS



# 21. No secrets are logged
@pytest.mark.asyncio
async def test_no_secrets_in_logs(
    valid_context: InvestigationContext,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    orch = DEVDOCOrchestrator()
    await orch.execute(valid_context)

    forbidden = ["token", "password", "secret", "bearer", "api_key"]
    for record in caplog.records:
        msg = record.getMessage().lower()
        for f in forbidden:
            assert f not in msg, f"Potential credential leak '{f}' found in log: {msg}"
