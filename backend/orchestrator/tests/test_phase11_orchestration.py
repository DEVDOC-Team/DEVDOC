"""Orchestration integration tests for Phase 11 operational agents."""

from __future__ import annotations

import logging
import socket
import uuid
from typing import Any

import pytest

from orchestrator.agents.docker_agent import DockerAgent
from orchestrator.agents.docker_inspector import FakeDockerInspector
from orchestrator.agents.github_agent import GitHubAgent
from orchestrator.agents.monitoring_agent import MonitoringAgent
from orchestrator.agents.monitoring_provider import FakeMonitoringProvider
from orchestrator.core.context import InvestigationContext
from orchestrator.core.orchestrator import DEVDOCOrchestrator
from orchestrator.core.result import ExecutionStatus
from orchestrator.stages.investigation import (
    CollectEvidenceStage,
    create_default_workflow,
    create_operational_stage_registry,
)
from orchestrator.tests.test_github_agent import FakeGitHubClient


@pytest.fixture
def operational_agents() -> tuple[GitHubAgent, DockerAgent, MonitoringAgent]:
    gh_client = FakeGitHubClient()
    doc_inspector = FakeDockerInspector(
        containers=[
            {
                "Id": "prod-api-001",
                "Names": ["/prod-api"],
                "Image": "devdoc/api:v1.0",
                "State": {"Status": "running", "Running": True, "ExitCode": 0},
            }
        ]
    )
    mon_provider = FakeMonitoringProvider(health_status="healthy")

    gh_agent = GitHubAgent(client=gh_client)
    doc_agent = DockerAgent(inspector=doc_inspector)
    mon_agent = MonitoringAgent(provider=mon_provider)
    return gh_agent, doc_agent, mon_agent


@pytest.fixture
def operational_context() -> InvestigationContext:
    return InvestigationContext(
        investigation_id=uuid.uuid4(),
        incident_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        execution_metadata={
            "github_repo": "DEVDOC-Team/devdoc",
            "service_name": "prod-api",
            "container_id": "prod-api-001",
        },
    )


@pytest.mark.asyncio
async def test_collect_evidence_stage_with_three_agents(
    operational_agents: tuple[GitHubAgent, DockerAgent, MonitoringAgent],
    operational_context: InvestigationContext,
) -> None:
    gh_agent, doc_agent, mon_agent = operational_agents
    stage = CollectEvidenceStage(agents=[gh_agent, doc_agent, mon_agent])

    result = await stage.execute(operational_context)

    assert result.status == ExecutionStatus.SUCCESS
    assert len(result.agent_results) == 3
    assert [a.agent_id for a in result.agent_results] == ["github_agent", "docker_agent", "monitoring_agent"]
    for agent_res in result.agent_results:
        assert agent_res.status == ExecutionStatus.SUCCESS
        assert agent_res.is_successful

    # Context should contain outputs for all three agents
    assert "github_agent" in operational_context.agent_outputs
    assert "docker_agent" in operational_context.agent_outputs
    assert "monitoring_agent" in operational_context.agent_outputs


@pytest.mark.asyncio
async def test_full_pipeline_with_operational_agents(
    operational_agents: tuple[GitHubAgent, DockerAgent, MonitoringAgent],
    operational_context: InvestigationContext,
) -> None:
    gh_agent, doc_agent, mon_agent = operational_agents
    registry = create_operational_stage_registry(
        github_agent=gh_agent,
        docker_agent=doc_agent,
        monitoring_agent=mon_agent,
    )
    workflow = create_default_workflow()
    orchestrator = DEVDOCOrchestrator(registry=registry, workflow=workflow)

    result = await orchestrator.execute(operational_context)

    assert result.status == ExecutionStatus.SUCCESS
    assert result.is_successful
    assert len(result.stage_results) == 8

    # Find the collect stage
    collect_stage = result.get_stage_result("collect")
    assert collect_stage is not None
    assert collect_stage.status == ExecutionStatus.SUCCESS
    assert len(collect_stage.agent_results) == 3


@pytest.mark.asyncio
async def test_operational_pipeline_agent_failure_handling(
    operational_context: InvestigationContext,
) -> None:
    gh_client = FakeGitHubClient()
    failing_doc_inspector = FakeDockerInspector(should_fail_connection=True)
    mon_provider = FakeMonitoringProvider()

    gh_agent = GitHubAgent(client=gh_client)
    doc_agent = DockerAgent(inspector=failing_doc_inspector)
    mon_agent = MonitoringAgent(provider=mon_provider)

    registry = create_operational_stage_registry(
        github_agent=gh_agent,
        docker_agent=doc_agent,
        monitoring_agent=mon_agent,
    )
    workflow = create_default_workflow()
    orchestrator = DEVDOCOrchestrator(registry=registry, workflow=workflow)

    result = await orchestrator.execute(operational_context)

    # Fail fast stops pipeline because collect stage had a failure
    assert result.status == ExecutionStatus.FAILED
    collect_stage = result.get_stage_result("collect")
    assert collect_stage is not None
    assert collect_stage.status == ExecutionStatus.FAILED
    assert len(collect_stage.agent_results) == 3
    assert collect_stage.agent_results[1].status == ExecutionStatus.FAILED


@pytest.mark.asyncio
async def test_operational_pipeline_cancellation(
    operational_agents: tuple[GitHubAgent, DockerAgent, MonitoringAgent],
    operational_context: InvestigationContext,
) -> None:
    gh_agent, doc_agent, mon_agent = operational_agents
    registry = create_operational_stage_registry(
        github_agent=gh_agent,
        docker_agent=doc_agent,
        monitoring_agent=mon_agent,
    )
    workflow = create_default_workflow()
    orchestrator = DEVDOCOrchestrator(registry=registry, workflow=workflow)

    operational_context.cancel("Operator aborted before execution")
    result = await orchestrator.execute(operational_context)

    assert result.status == ExecutionStatus.CANCELLED
    assert len(result.stage_results) == 0


@pytest.mark.asyncio
async def test_no_external_network_calls_in_phase11_pipeline(
    operational_agents: tuple[GitHubAgent, DockerAgent, MonitoringAgent],
    operational_context: InvestigationContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Guarantee that zero external network connections occur during Phase 11 execution."""
    original_connect = socket.socket.connect

    def disallowed_connect(sock_self: Any, address: Any, *args: Any, **kwargs: Any) -> Any:
        if isinstance(address, tuple) and len(address) >= 1:
            host = address[0]
            if host in ("127.0.0.1", "::1", "localhost"):
                return original_connect(sock_self, address, *args, **kwargs)
        raise AssertionError(f"Unexpected outbound network call attempted to {address}!")

    monkeypatch.setattr(socket.socket, "connect", disallowed_connect)

    gh_agent, doc_agent, mon_agent = operational_agents
    registry = create_operational_stage_registry(
        github_agent=gh_agent,
        docker_agent=doc_agent,
        monitoring_agent=mon_agent,
    )
    workflow = create_default_workflow()
    orchestrator = DEVDOCOrchestrator(registry=registry, workflow=workflow)

    result = await orchestrator.execute(operational_context)
    assert result.status == ExecutionStatus.SUCCESS


@pytest.mark.asyncio
async def test_no_secrets_in_logs_during_phase11_execution(
    operational_agents: tuple[GitHubAgent, DockerAgent, MonitoringAgent],
    operational_context: InvestigationContext,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)

    gh_agent, doc_agent, mon_agent = operational_agents
    registry = create_operational_stage_registry(
        github_agent=gh_agent,
        docker_agent=doc_agent,
        monitoring_agent=mon_agent,
    )
    workflow = create_default_workflow()
    orchestrator = DEVDOCOrchestrator(registry=registry, workflow=workflow)

    await orchestrator.execute(operational_context)

    forbidden = ["token", "password", "secret", "bearer", "api_key"]
    for record in caplog.records:
        msg = record.getMessage().lower()
        for f in forbidden:
            assert f not in msg, f"Potential credential leak '{f}' found in log: {msg}"
