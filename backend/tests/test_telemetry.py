"""Phase 21 tests for Prometheus metrics and OpenTelemetry tracing."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.metrics import metrics_registry
from app.core.telemetry import get_current_trace_id, trace_span
from app.main import app


def test_metrics_endpoint_scraping():
    client = TestClient(app)

    # Hit health endpoint to generate request traffic
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200

    # Scrape /metrics
    metrics_resp = client.get("/metrics")
    assert metrics_resp.status_code == 200
    assert "text/plain" in metrics_resp.headers["content-type"]

    text = metrics_resp.text
    assert "http_requests_total" in text
    assert 'method="GET"' in text
    assert 'status_class="2xx"' in text
    # Ensure /metrics itself is not recursively counted in http_requests_total
    assert 'path_template="/metrics"' not in text


def test_metrics_domain_recordings():
    # Record domain events
    metrics_registry.record_investigation(status="completed", duration_seconds=12.5)
    metrics_registry.record_sandbox_verification(provider="docker", status="passed")
    metrics_registry.record_llm_request(
        provider="nebius",
        input_tokens=1500,
        output_tokens=300,
        cost_usd=0.000162,
        success=True,
    )
    metrics_registry.record_llm_budget_rejection()
    metrics_registry.record_approval(status="approved")

    exported = metrics_registry.export_prometheus_text()

    assert 'devdoc_investigation_runs_total{status="completed"} 1' in exported
    assert 'devdoc_sandbox_verifications_total{provider="docker",status="passed"} 1' in exported
    assert 'devdoc_llm_tokens_total{provider="nebius",type="input"} 1500' in exported
    assert 'devdoc_llm_tokens_total{provider="nebius",type="output"} 300' in exported
    assert 'devdoc_llm_cost_usd_total{provider="nebius"} 0.000162' in exported
    assert "devdoc_llm_budget_rejections_total 1" in exported
    assert 'devdoc_approvals_total{status="approved"} 1' in exported


@pytest.mark.asyncio
async def test_tracing_span_lifecycle():
    trace_id = get_current_trace_id()
    assert len(trace_id) == 32

    attrs = {
        "user_id": "usr_123",
        "api_key": "sk-secret-token",
        "nested_token": "token123",
        "safe_int": 42,
    }

    async with trace_span("test_operation", attributes=attrs) as span:
        assert span["name"] == "test_operation"
        assert span["trace_id"] == trace_id
        assert len(span["span_id"]) == 16
        assert span["attributes"]["api_key"] == "[REDACTED]"
        assert span["attributes"]["nested_token"] == "[REDACTED]"
        assert span["attributes"]["user_id"] == "usr_123"
        assert span["attributes"]["safe_int"] == 42
        assert span["status"] == "unset"

    assert span["status"] == "ok"
    assert "duration_seconds" in span


@pytest.mark.asyncio
async def test_tracing_span_error_recording():
    with pytest.raises(ZeroDivisionError):
        async with trace_span("failing_span"):
            _ = 1 / 0
