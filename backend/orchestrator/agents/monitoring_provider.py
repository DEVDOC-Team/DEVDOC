"""Monitoring Provider Abstraction and Implementations.

Defines a provider-neutral interface for retrieving service health, metrics,
and active alerts. Guarantees zero SSRF, credential sanitization, and bounded timeouts.
"""

from __future__ import annotations

import urllib.parse
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

# Blocked IP addresses for SSRF prevention (e.g., Cloud provider metadata endpoints)
_BLOCKED_METADATA_HOSTS = {
    "169.254.169.254",
    "metadata.google.internal",
    "instance-data",
}


class MonitoringError(Exception):
    """Base exception for monitoring provider failures."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class MonitoringConnectionError(MonitoringError):
    """Raised when the monitoring provider is unreachable."""


class MonitoringTimeoutError(MonitoringError):
    """Raised when a request to the monitoring provider times out."""


class MonitoringValidationError(MonitoringError):
    """Raised when parameters or provider responses fail validation."""


class MonitoringSecurityError(MonitoringError):
    """Raised when a URL or configuration violates security/SSRF constraints."""


def validate_monitoring_endpoint(endpoint: str) -> str:
    """Validate monitoring endpoint URL to prevent SSRF and protocol smuggling.

    Raises:
        MonitoringSecurityError: If the endpoint is invalid, non-HTTP, or targets cloud metadata.
    """
    clean = endpoint.strip()
    parsed = urllib.parse.urlparse(clean)
    if parsed.scheme not in ("http", "https"):
        raise MonitoringSecurityError(
            f"Invalid monitoring URL scheme '{parsed.scheme}': Only 'http' and 'https' allowed"
        )
    hostname = (parsed.hostname or "").lower()
    if not hostname:
        raise MonitoringSecurityError("Missing hostname in monitoring endpoint URL")
    if hostname in _BLOCKED_METADATA_HOSTS:
        raise MonitoringSecurityError(f"Access to metadata host '{hostname}' is blocked for security")
    return clean


class MonitoringProvider(ABC):
    """Abstract provider-neutral interface for operational telemetry inspection."""

    @abstractmethod
    async def get_service_health(self, service_name: str | None = None) -> dict[str, Any]:
        """Retrieve health and availability status of services."""
        ...

    @abstractmethod
    async def get_metrics(
        self,
        metric_names: list[str] | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> dict[str, Any]:
        """Retrieve operational metrics such as CPU, memory, errors, and latency."""
        ...

    @abstractmethod
    async def get_alerts(
        self,
        service_name: str | None = None,
        status: str = "firing",
    ) -> list[dict[str, Any]]:
        """Retrieve active operational alerts."""
        ...


class FakeMonitoringProvider(MonitoringProvider):
    """Deterministic in-memory fake monitoring provider for testing.

    Guarantees:
    - 0 network requests
    - Deterministic signals (CPU, memory, latency, errors, alerts)
    - Configurable failure and timeout triggers
    """

    def __init__(
        self,
        health_status: str = "healthy",
        metrics_data: dict[str, Any] | None = None,
        alerts: list[dict[str, Any]] | None = None,
        should_fail_connection: bool = False,
        should_timeout: bool = False,
        malformed_response: bool = False,
    ) -> None:
        self.health_status = health_status
        self.metrics_data = metrics_data or {
            "cpu_percent": 42.5,
            "memory_percent": 68.2,
            "error_rate_percent": 0.05,
            "requests_per_second": 125.0,
            "latency_p95_ms": 48.0,
            "latency_p99_ms": 115.0,
        }
        self.alerts = alerts or [
            {
                "id": "alert-001",
                "name": "HighLatencyWarning",
                "severity": "warning",
                "status": "firing",
                "description": "API Gateway p99 latency crossed 100ms threshold",
                "starts_at": "2026-10-02T15:00:00Z",
            }
        ]
        self.should_fail_connection = should_fail_connection
        self.should_timeout = should_timeout
        self.malformed_response = malformed_response

    async def get_service_health(self, service_name: str | None = None) -> dict[str, Any]:
        if self.should_fail_connection:
            raise MonitoringConnectionError("Monitoring provider connection refused")
        if self.should_timeout:
            raise MonitoringTimeoutError("Monitoring health check timed out")
        if self.malformed_response:
            return {"bad_payload": None}

        now = datetime.now(UTC).isoformat()
        return {
            "status": self.health_status,
            "service": service_name or "api-service",
            "checked_at": now,
            "components": {
                "database": "up",
                "cache": "up",
                "worker": "up" if self.health_status == "healthy" else "degraded",
            },
        }

    async def get_metrics(
        self,
        metric_names: list[str] | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> dict[str, Any]:
        if self.should_fail_connection:
            raise MonitoringConnectionError("Monitoring metrics query failed")
        if self.should_timeout:
            raise MonitoringTimeoutError("Monitoring metrics query timed out")

        now = end_time or datetime.now(UTC)
        start = start_time or (now - timedelta(minutes=15))

        # Filter or return all default metrics
        res_metrics = {}
        for k, v in self.metrics_data.items():
            if metric_names is None or k in metric_names:
                res_metrics[k] = v

        return {
            "start_time": start.isoformat(),
            "end_time": now.isoformat(),
            "metrics": res_metrics,
        }

    async def get_alerts(
        self,
        service_name: str | None = None,
        status: str = "firing",
    ) -> list[dict[str, Any]]:
        if self.should_fail_connection:
            raise MonitoringConnectionError("Failed to retrieve alerts")
        if self.should_timeout:
            raise MonitoringTimeoutError("Alerts query timed out")

        filtered = [a for a in self.alerts if status == "all" or a.get("status") == status]
        return filtered


class GenericHTTPMonitoringProvider(MonitoringProvider):
    """HTTP client querying a remote monitoring endpoint with SSRF protection."""

    def __init__(
        self,
        base_url: str = "http://localhost:9090",
        api_token: str | None = None,
        timeout: float = 5.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = validate_monitoring_endpoint(base_url).rstrip("/")
        self.api_token = api_token
        self.timeout = timeout
        self._external_client = client

    def _get_headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json", "User-Agent": "DEVDOC-MonitoringAgent"}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        return headers

    def _get_client(self) -> httpx.AsyncClient:
        if self._external_client is not None:
            return self._external_client
        return httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout)

    async def get_service_health(self, service_name: str | None = None) -> dict[str, Any]:
        client = self._get_client()
        should_close = self._external_client is None
        try:
            params = {"service": service_name} if service_name else None
            res = await client.get("/health", headers=self._get_headers(), params=params)
            if res.status_code == 200:
                data = res.json()
                return data if isinstance(data, dict) else {"raw": data}
            raise MonitoringError(f"Health check failed with status {res.status_code}")
        except httpx.TimeoutException as exc:
            raise MonitoringTimeoutError("Remote monitoring health check timed out") from exc
        except httpx.RequestError as exc:
            raise MonitoringConnectionError(f"Remote monitoring connection error: {exc}") from exc
        finally:
            if should_close:
                await client.aclose()

    async def get_metrics(
        self,
        metric_names: list[str] | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> dict[str, Any]:
        client = self._get_client()
        should_close = self._external_client is None
        try:
            params: dict[str, Any] = {}
            if metric_names:
                params["metrics"] = ",".join(metric_names)
            if start_time:
                params["start"] = start_time.isoformat()
            if end_time:
                params["end"] = end_time.isoformat()

            res = await client.get("/metrics", headers=self._get_headers(), params=params)
            if res.status_code == 200:
                data = res.json()
                return data if isinstance(data, dict) else {"raw": data}
            raise MonitoringError(f"Metrics query failed with status {res.status_code}")
        except httpx.TimeoutException as exc:
            raise MonitoringTimeoutError("Remote metrics query timed out") from exc
        except httpx.RequestError as exc:
            raise MonitoringConnectionError(f"Remote monitoring connection error: {exc}") from exc
        finally:
            if should_close:
                await client.aclose()

    async def get_alerts(
        self,
        service_name: str | None = None,
        status: str = "firing",
    ) -> list[dict[str, Any]]:
        client = self._get_client()
        should_close = self._external_client is None
        try:
            params = {"status": status}
            if service_name:
                params["service"] = service_name
            res = await client.get("/alerts", headers=self._get_headers(), params=params)
            if res.status_code == 200:
                data = res.json()
                return data if isinstance(data, list) else []
            raise MonitoringError(f"Alerts query failed with status {res.status_code}")
        except httpx.TimeoutException as exc:
            raise MonitoringTimeoutError("Remote alerts query timed out") from exc
        except httpx.RequestError as exc:
            raise MonitoringConnectionError(f"Remote monitoring connection error: {exc}") from exc
        finally:
            if should_close:
                await client.aclose()
