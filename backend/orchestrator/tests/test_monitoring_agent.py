"""Tests for MonitoringAgent and MonitoringProvider."""

from __future__ import annotations

import uuid

import pytest

from orchestrator.agents.monitoring_agent import MonitoringAgent
from orchestrator.agents.monitoring_provider import (
    FakeMonitoringProvider,
    MonitoringSecurityError,
    validate_monitoring_endpoint,
)
from orchestrator.core.context import InvestigationContext
from orchestrator.core.result import ExecutionStatus


@pytest.fixture
def base_context() -> InvestigationContext:
    return InvestigationContext(
        investigation_id=uuid.uuid4(),
        incident_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        execution_metadata={"service_name": "payments-api"},
    )


@pytest.mark.asyncio
async def test_monitoring_agent_healthy_success(base_context: InvestigationContext) -> None:
    provider = FakeMonitoringProvider(health_status="healthy")
    agent = MonitoringAgent(provider=provider)

    result = await agent.execute(base_context)

    assert result.status == ExecutionStatus.SUCCESS
    assert result.is_successful
    assert result.source == "monitoring"
    assert result.data["health"]["status"] == "healthy"
    assert "metrics" in result.data
    assert "alerts" in result.data
    assert result.output_metadata["service"] == "payments-api"


@pytest.mark.asyncio
async def test_monitoring_agent_degraded_triggers_warning(base_context: InvestigationContext) -> None:
    provider = FakeMonitoringProvider(health_status="degraded")
    agent = MonitoringAgent(provider=provider)

    result = await agent.execute(base_context)

    assert result.status == ExecutionStatus.SUCCESS
    assert any("degraded" in w.lower() for w in result.warnings)


@pytest.mark.asyncio
async def test_monitoring_agent_metric_threshold_warnings(base_context: InvestigationContext) -> None:
    high_metrics = {
        "cpu_percent": 94.5,
        "memory_percent": 96.0,
        "error_rate_percent": 4.5,
        "latency_p99_ms": 350.0,
    }
    provider = FakeMonitoringProvider(metrics_data=high_metrics)
    agent = MonitoringAgent(provider=provider)

    result = await agent.execute(base_context)

    assert result.status == ExecutionStatus.SUCCESS
    warnings_text = " ".join(result.warnings)
    assert "High CPU utilization" in warnings_text
    assert "High memory utilization" in warnings_text
    assert "Elevated error rate" in warnings_text
    assert "High p99 latency" in warnings_text


@pytest.mark.asyncio
async def test_monitoring_agent_active_alerts_warning(base_context: InvestigationContext) -> None:
    alerts = [
        {"id": "a1", "name": "PodCrashLooping", "severity": "critical", "status": "firing"},
        {"id": "a2", "name": "DatabaseConnectionExhaustion", "severity": "critical", "status": "firing"},
    ]
    provider = FakeMonitoringProvider(alerts=alerts)
    agent = MonitoringAgent(provider=provider)

    result = await agent.execute(base_context)

    assert result.status == ExecutionStatus.SUCCESS
    assert result.output_metadata["active_alerts_count"] == 2
    assert any("2 active firing alerts" in w for w in result.warnings)


@pytest.mark.asyncio
async def test_monitoring_agent_connection_failure(base_context: InvestigationContext) -> None:
    provider = FakeMonitoringProvider(should_fail_connection=True)
    agent = MonitoringAgent(provider=provider)

    result = await agent.execute(base_context)

    assert result.status == ExecutionStatus.FAILED
    assert "connection failed" in (result.error_message or "").lower()
    assert result.output_metadata["error"] == "provider_unavailable"


@pytest.mark.asyncio
async def test_monitoring_agent_timeout(base_context: InvestigationContext) -> None:
    provider = FakeMonitoringProvider(should_timeout=True)
    agent = MonitoringAgent(provider=provider)

    result = await agent.execute(base_context)

    assert result.status == ExecutionStatus.FAILED
    assert "timed out" in (result.error_message or "").lower()
    assert result.output_metadata["error"] == "timeout"


def test_validate_monitoring_endpoint_ssrf_prevention() -> None:
    assert validate_monitoring_endpoint("http://prometheus.internal:9090") == "http://prometheus.internal:9090"
    assert validate_monitoring_endpoint("https://datadog.api.com") == "https://datadog.api.com"

    # Cloud metadata endpoints must be strictly blocked
    with pytest.raises(MonitoringSecurityError) as exc:
        validate_monitoring_endpoint("http://169.254.169.254/latest/meta-data")
    assert "metadata host" in str(exc.value)

    with pytest.raises(MonitoringSecurityError) as exc:
        validate_monitoring_endpoint("http://metadata.google.internal/computeMetadata/v1")
    assert "metadata host" in str(exc.value)

    # Disallowed protocols
    with pytest.raises(MonitoringSecurityError) as exc:
        validate_monitoring_endpoint("file:///etc/passwd")
    assert "URL scheme" in str(exc.value)


@pytest.mark.asyncio
async def test_monitoring_agent_redacts_credentials(base_context: InvestigationContext) -> None:
    provider = FakeMonitoringProvider(
        alerts=[
            {
                "id": "leak_alert",
                "name": "LeakedTokenAlert",
                "status": "firing",
                "description": "Found Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9 in query params",
            }
        ]
    )
    agent = MonitoringAgent(provider=provider)

    result = await agent.execute(base_context)

    assert result.status == ExecutionStatus.SUCCESS
    desc = result.data["alerts"][0]["description"]
    assert "Bearer" not in desc
    assert "[REDACTED]" in desc
