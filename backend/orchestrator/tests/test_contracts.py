"""Tests for stage, agent, workflow, and provider contracts."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from orchestrator.agents.base import MockInvestigationAgent
from orchestrator.contracts.agent import BaseAgent, LLMProvider
from orchestrator.contracts.execution import FailurePolicy, WorkflowDefinition
from orchestrator.contracts.stage import BaseStage
from orchestrator.core.context import InvestigationContext
from orchestrator.core.errors import WorkflowValidationError
from orchestrator.core.result import AgentResult, ExecutionStatus, StageResult


class ConcreteStage(BaseStage):
    @property
    def stage_id(self) -> str:
        return "concrete_stage"

    @property
    def name(self) -> str:
        return "Concrete Stage"

    async def execute(self, context: InvestigationContext) -> StageResult:
        return StageResult(stage_id=self.stage_id, status=ExecutionStatus.SUCCESS)


class ConcreteAgent(BaseAgent):
    @property
    def identifier(self) -> str:
        return "concrete_agent"

    @property
    def name(self) -> str:
        return "Concrete Agent"

    @property
    def capabilities(self) -> set[str]:
        return {"inspection"}

    async def execute(self, context: InvestigationContext) -> AgentResult:
        return AgentResult(agent_id=self.identifier, status=ExecutionStatus.SUCCESS)


class MockLLMProvider(LLMProvider):
    @property
    def provider_name(self) -> str:
        return "mock_nemotron_provider"

    async def complete(self, prompt: str, **kwargs: Any) -> str:
        return f"Mock response to: {prompt}"


@pytest.mark.asyncio
async def test_base_stage_contract() -> None:
    stage = ConcreteStage()
    assert stage.stage_id == "concrete_stage"
    assert stage.name == "Concrete Stage"
    assert stage.description == ""

    ctx = InvestigationContext(
        investigation_id=uuid.uuid4(),
        incident_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
    )
    result = await stage.execute(ctx)
    assert result.stage_id == "concrete_stage"
    assert result.status == ExecutionStatus.SUCCESS
    assert result.is_successful


@pytest.mark.asyncio
async def test_base_agent_contract() -> None:
    agent = ConcreteAgent()
    assert agent.identifier == "concrete_agent"
    assert agent.name == "Concrete Agent"
    assert agent.capabilities == {"inspection"}

    ctx = InvestigationContext(
        investigation_id=uuid.uuid4(),
        incident_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
    )
    result = await agent.execute(ctx)
    assert result.agent_id == "concrete_agent"
    assert result.status == ExecutionStatus.SUCCESS
    assert result.is_successful


@pytest.mark.asyncio
async def test_mock_investigation_agent_success() -> None:
    agent = MockInvestigationAgent(
        identifier="agent_x",
        name="Agent X",
        capabilities={"log_parsing"},
        output_metadata={"error_count": 5},
    )
    assert agent.identifier == "agent_x"
    assert agent.name == "Agent X"
    assert agent.capabilities == {"log_parsing"}
    assert agent.execution_count == 0

    ctx = InvestigationContext(
        investigation_id=uuid.uuid4(),
        incident_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
    )
    result = await agent.execute(ctx)
    assert result.status == ExecutionStatus.SUCCESS
    assert result.output_metadata == {"error_count": 5}
    assert agent.execution_count == 1
    assert agent.last_context is ctx
    assert ctx.agent_outputs["agent_x"] == {"error_count": 5}


@pytest.mark.asyncio
async def test_mock_investigation_agent_failure() -> None:
    agent = MockInvestigationAgent(
        identifier="agent_failing",
        should_fail=True,
        error_message="Simulated connection error",
    )
    ctx = InvestigationContext(
        investigation_id=uuid.uuid4(),
        incident_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
    )
    result = await agent.execute(ctx)
    assert result.status == ExecutionStatus.FAILED
    assert result.error_message == "Simulated connection error"
    assert not result.is_successful
    assert agent.execution_count == 1


@pytest.mark.asyncio
async def test_mock_investigation_agent_exception() -> None:
    agent = MockInvestigationAgent(
        raise_exception=RuntimeError("Fatal agent crash"),
    )
    ctx = InvestigationContext(
        investigation_id=uuid.uuid4(),
        incident_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
    )
    with pytest.raises(RuntimeError) as exc:
        await agent.execute(ctx)
    assert "Fatal agent crash" in str(exc.value)


@pytest.mark.asyncio
async def test_llm_provider_contract_costs_zero() -> None:
    # Verify that LLMProvider cannot be instantiated directly
    with pytest.raises(TypeError):
        LLMProvider()  # type: ignore[abstract]

    # Verify concrete mock provider contract
    provider = MockLLMProvider()
    assert provider.provider_name == "mock_nemotron_provider"
    completion = await provider.complete("Test prompt")
    assert completion == "Mock response to: Test prompt"


def test_workflow_definition_validation_success() -> None:
    wf = WorkflowDefinition(
        workflow_id="custom_wf",
        name="Custom Workflow",
        stage_ids=["stage_a", "stage_b"],
        failure_policy=FailurePolicy.FAIL_FAST,
    )
    assert wf.workflow_id == "custom_wf"
    assert wf.name == "Custom Workflow"
    assert wf.stage_ids == ["stage_a", "stage_b"]
    assert wf.failure_policy == FailurePolicy.FAIL_FAST


def test_workflow_definition_empty_id_rejected() -> None:
    with pytest.raises(WorkflowValidationError) as exc:
        WorkflowDefinition(
            workflow_id="",
            name="Workflow",
            stage_ids=["s1"],
        )
    assert "workflow_id must be a non-empty string" in str(exc.value)


def test_workflow_definition_empty_name_rejected() -> None:
    with pytest.raises(WorkflowValidationError) as exc:
        WorkflowDefinition(
            workflow_id="wf_1",
            name="",
            stage_ids=["s1"],
        )
    assert "workflow name must be a non-empty string" in str(exc.value)


def test_workflow_definition_empty_stages_rejected() -> None:
    with pytest.raises(WorkflowValidationError) as exc:
        WorkflowDefinition(
            workflow_id="wf_1",
            name="Workflow 1",
            stage_ids=[],
        )
    assert "must define at least one stage" in str(exc.value)


def test_workflow_definition_duplicate_stages_rejected() -> None:
    with pytest.raises(WorkflowValidationError) as exc:
        WorkflowDefinition(
            workflow_id="wf_1",
            name="Workflow 1",
            stage_ids=["stage_1", "stage_1"],
        )
    assert "duplicate stage 'stage_1'" in str(exc.value)


def test_workflow_definition_empty_stage_id_item_rejected() -> None:
    with pytest.raises(WorkflowValidationError) as exc:
        WorkflowDefinition(
            workflow_id="wf_1",
            name="Workflow 1",
            stage_ids=["stage_1", ""],
        )
    assert "contains an empty stage identifier" in str(exc.value)
