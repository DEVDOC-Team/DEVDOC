"""Phase 19 security hardening tests covering secret redaction, SSRF, headers, and exception masking."""

from __future__ import annotations

import io
import logging
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient

from app.core.exceptions import generic_exception_handler, http_exception_handler
from app.core.logging import SecretRedactingFilter
from app.main import app
from orchestrator.agents.monitoring_provider import (
    MonitoringSecurityError,
    validate_monitoring_endpoint,
)


def test_log_secret_redaction():
    redacting_filter = SecretRedactingFilter()

    # Test Bearer token redaction
    record1 = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="User authenticated with Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.secretpayload",
        args=(),
        exc_info=None,
    )
    redacting_filter.filter(record1)
    assert "eyJhbGci" not in record1.msg
    assert "Bearer [REDACTED]" in record1.msg

    # Test database URL password redaction
    record2 = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="Connecting to postgresql+asyncpg://devdoc_user:super_secret_pw@db.supabase.co:5432/postgres",
        args=(),
        exc_info=None,
    )
    redacting_filter.filter(record2)
    assert "super_secret_pw" not in record2.msg
    assert "devdoc_user:[REDACTED]@" in record2.msg

    # Test API key redaction
    record3 = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="Initialized client with api_key='sk-nebius-1234567890abcdef'",
        args=(),
        exc_info=None,
    )
    redacting_filter.filter(record3)
    assert "sk-nebius-1234567890abcdef" not in record3.msg
    assert "[REDACTED]" in record3.msg


def test_ssrf_prevention():
    # Valid endpoints
    assert validate_monitoring_endpoint("https://prometheus.internal.company.com/api/v1")
    assert validate_monitoring_endpoint("http://monitoring-service:9090")

    # Cloud metadata endpoints must be blocked
    with pytest.raises(MonitoringSecurityError, match="blocked for security"):
        validate_monitoring_endpoint("http://169.254.169.254/latest/meta-data")

    with pytest.raises(MonitoringSecurityError, match="blocked for security"):
        validate_monitoring_endpoint("http://metadata.google.internal/computeMetadata/v1")

    # Non-HTTP schemes must be blocked
    with pytest.raises(MonitoringSecurityError, match="Only 'http' and 'https' allowed"):
        validate_monitoring_endpoint("file:///etc/passwd")

    with pytest.raises(MonitoringSecurityError, match="Only 'http' and 'https' allowed"):
        validate_monitoring_endpoint("gopher://127.0.0.1:70")


def test_security_headers_present():
    client = TestClient(app)
    response = client.get("/api/v1/health")
    assert response.status_code == 200

    headers = response.headers
    assert headers.get("X-Content-Type-Options") == "nosniff"
    assert headers.get("X-Frame-Options") == "DENY"
    assert headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert headers.get("Cache-Control") == "no-store"


@pytest.mark.asyncio
async def test_generic_exception_handler_masks_internal_details():
    mock_request = MagicMock(spec=Request)
    sensitive_exc = ValueError("Database connection failed: password=supersecret at host 10.0.0.5")

    response = await generic_exception_handler(mock_request, sensitive_exc)
    assert response.status_code == 500
    import json
    body = json.loads(response.body.decode("utf-8"))
    assert body["success"] is False
    assert body["error"]["code"] == 500
    assert body["error"]["message"] == "Internal server error"
    assert "supersecret" not in response.body.decode("utf-8")
    assert "10.0.0.5" not in response.body.decode("utf-8")
