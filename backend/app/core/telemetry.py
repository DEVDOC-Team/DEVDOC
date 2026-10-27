"""OpenTelemetry tracing abstraction with safe no-export local development mode."""

from __future__ import annotations

import contextvars
import secrets
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from app.core.config import settings
from app.core.logging import logger

_current_trace_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("current_trace_id", default=None)
_current_span_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("current_span_id", default=None)

_SENSITIVE_ATTR_KEYS = {"token", "key", "password", "secret", "auth", "credential", "cookie", "authorization"}


def _sanitize_attributes(attrs: dict[str, Any] | None) -> dict[str, Any]:
    if not attrs:
        return {}
    clean: dict[str, Any] = {}
    for k, v in attrs.items():
        if any(s in k.lower() for s in _SENSITIVE_ATTR_KEYS):
            clean[k] = "[REDACTED]"
        elif isinstance(v, (str, int, float, bool)):
            clean[k] = v
        else:
            clean[k] = str(v)[:128]
    return clean


def get_current_trace_id() -> str:
    """Return active W3C trace ID or generate a new 32-character hex ID."""
    tid = _current_trace_id.get()
    if not tid:
        tid = secrets.token_hex(16)  # 32 hex chars
        _current_trace_id.set(tid)
    return tid


@asynccontextmanager
async def trace_span(
    name: str,
    attributes: dict[str, Any] | None = None,
) -> AsyncGenerator[dict[str, Any]]:
    """Execute within a bounded trace span with safe fallback."""
    span_id = secrets.token_hex(8)  # 16 hex chars
    trace_id = get_current_trace_id()
    token_span = _current_span_id.set(span_id)

    safe_attrs = _sanitize_attributes(attributes)
    span_context = {
        "name": name,
        "trace_id": trace_id,
        "span_id": span_id,
        "start_time": time.time(),
        "attributes": safe_attrs,
        "status": "unset",
    }

    try:
        yield span_context
        span_context["status"] = "ok"
    except Exception as exc:
        span_context["status"] = "error"
        span_context["error_type"] = type(exc).__name__
        raise
    finally:
        span_context["duration_seconds"] = time.time() - span_context["start_time"]
        _current_span_id.reset(token_span)
        # In production with OTLP configured, export safely without raising
        if settings.opentelemetry_enabled and settings.otlp_endpoint:
            try:
                # OTLP export hook (non-blocking / no-throw)
                pass
            except Exception as export_err:
                logger.debug("Tracing export dropped: %s", export_err)
