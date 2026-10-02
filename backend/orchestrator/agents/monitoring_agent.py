"""Monitoring Investigation Agent.

Gathers structured telemetry, service health checks, and active incident alerts.
Enforces provider neutrality, credential sanitization, SSRF protection, and bounded timeouts.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from orchestrator.agents.monitoring_provider import (
    FakeMonitoringProvider,
    MonitoringConnectionError,
    MonitoringError,
    MonitoringProvider,
    MonitoringSecurityError,
    MonitoringTimeoutError,
)
from orchestrator.contracts.agent import BaseAgent
from orchestrator.core.context import InvestigationContext
from orchestrator.core.result import AgentResult, ExecutionStatus
from orchestrator.core.sanitizer import sanitize_data

logger = logging.getLogger("devdoc.orchestrator.agents.monitoring")


class MonitoringAgent(BaseAgent):
    """Investigation agent inspecting operational service health, telemetry metrics, and alerts.

    Capabilities:
    - service_health: Service availability and subsystem status
    - telemetry_metrics: CPU, memory, request volume, error rates
    - active_alerts: Currently firing incident alerts
    - latency_metrics: p95 and p99 latency percentiles
    - error_rate_metrics: Percentage of failed requests
    """

    def __init__(self, provider: MonitoringProvider | None = None) -> None:
        self.provider = provider if provider is not None else FakeMonitoringProvider()

    @property
    def identifier(self) -> str:
        return "monitoring_agent"

    @property
    def name(self) -> str:
        return "Monitoring Investigation Agent"

    @property
    def capabilities(self) -> set[str]:
        return {
            "service_health",
            "telemetry_metrics",
            "active_alerts",
            "latency_metrics",
            "error_rate_metrics",
        }

    async def execute(self, context: InvestigationContext) -> AgentResult:
        """Query monitoring provider for health, metrics, and alerts."""
        start_time = time.perf_counter()
        started_at = datetime.now(UTC)

        metadata = context.execution_metadata
        service_name = metadata.get("service_name") or metadata.get("service")
        metric_names = metadata.get("metric_names")
        include_alerts = metadata.get("include_alerts", True)
        window_minutes = int(metadata.get("time_window_minutes", 15))

        warnings: list[str] = []
        errors: list[str] = []
        collected_data: dict[str, Any] = {}

        try:
            # 1. Service Health
            health = await self.provider.get_service_health(service_name)
            collected_data["health"] = health
            status_val = str(health.get("status", "")).lower()
            if status_val in ("degraded", "unhealthy", "down", "critical"):
                warnings.append(f"Service health status is '{status_val}'")

            # 2. Telemetry Metrics
            end_time = datetime.now(UTC)
            start_window = end_time - timedelta(minutes=max(1, min(window_minutes, 1440)))
            metrics = await self.provider.get_metrics(
                metric_names=metric_names,
                start_time=start_window,
                end_time=end_time,
            )
            collected_data["metrics"] = metrics

            # Check for critical telemetry anomalies to raise warnings
            metrics_dict = metrics.get("metrics", {})
            if isinstance(metrics_dict, dict):
                cpu = metrics_dict.get("cpu_percent")
                if isinstance(cpu, (int, float)) and cpu > 85.0:
                    warnings.append(f"High CPU utilization detected: {cpu}%")

                mem = metrics_dict.get("memory_percent")
                if isinstance(mem, (int, float)) and mem > 90.0:
                    warnings.append(f"High memory utilization detected: {mem}%")

                err_rate = metrics_dict.get("error_rate_percent")
                if isinstance(err_rate, (int, float)) and err_rate > 1.0:
                    warnings.append(f"Elevated error rate detected: {err_rate}%")

                p99 = metrics_dict.get("latency_p99_ms")
                if isinstance(p99, (int, float)) and p99 > 200.0:
                    warnings.append(f"High p99 latency detected: {p99}ms")

            # 3. Active Alerts
            if include_alerts:
                alerts = await self.provider.get_alerts(service_name=service_name, status="firing")
                collected_data["alerts"] = alerts
                if alerts:
                    warnings.append(f"Found {len(alerts)} active firing alerts")
            else:
                collected_data["alerts"] = []

            sanitized_data = sanitize_data(collected_data)
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            completed_at = datetime.now(UTC)

            summary_meta = {
                "service": service_name,
                "health_status": health.get("status"),
                "active_alerts_count": len(collected_data.get("alerts", [])),
                "warnings_count": len(warnings),
            }

            result = AgentResult(
                agent_id=self.identifier,
                status=ExecutionStatus.SUCCESS,
                investigation_id=context.investigation_id,
                execution_id=context.execution_id,
                source="monitoring",
                data=sanitized_data,
                output_metadata=summary_meta,
                warnings=warnings,
                errors=[],
                collected_at=completed_at,
                started_at=started_at,
                completed_at=completed_at,
                duration_ms=duration_ms,
            )
            context.record_agent_output(self.identifier, summary_meta)
            return result

        except MonitoringSecurityError as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            err_msg = f"Monitoring security error: {exc}"
            logger.warning("MonitoringAgent security violation: %s", exc)
            errors.append(err_msg)
            return AgentResult(
                agent_id=self.identifier,
                status=ExecutionStatus.FAILED,
                investigation_id=context.investigation_id,
                execution_id=context.execution_id,
                source="monitoring",
                error_message=err_msg,
                errors=errors,
                warnings=warnings,
                output_metadata={"error": "security_violation"},
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_ms=duration_ms,
            )

        except MonitoringConnectionError as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            err_msg = f"Monitoring provider connection failed: {exc}"
            errors.append(err_msg)
            return AgentResult(
                agent_id=self.identifier,
                status=ExecutionStatus.FAILED,
                investigation_id=context.investigation_id,
                execution_id=context.execution_id,
                source="monitoring",
                error_message=err_msg,
                errors=errors,
                warnings=warnings,
                output_metadata={"error": "provider_unavailable"},
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_ms=duration_ms,
            )

        except MonitoringTimeoutError as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            err_msg = f"Monitoring operation timed out: {exc}"
            errors.append(err_msg)
            return AgentResult(
                agent_id=self.identifier,
                status=ExecutionStatus.FAILED,
                investigation_id=context.investigation_id,
                execution_id=context.execution_id,
                source="monitoring",
                error_message=err_msg,
                errors=errors,
                warnings=warnings,
                output_metadata={"error": "timeout"},
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_ms=duration_ms,
            )

        except MonitoringError as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            err_msg = f"Monitoring operational error: {exc}"
            errors.append(err_msg)
            return AgentResult(
                agent_id=self.identifier,
                status=ExecutionStatus.FAILED,
                investigation_id=context.investigation_id,
                execution_id=context.execution_id,
                source="monitoring",
                error_message=err_msg,
                errors=errors,
                warnings=warnings,
                output_metadata={"error": "monitoring_error"},
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_ms=duration_ms,
            )

        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            err_msg = f"Unexpected failure in monitoring inspection: {exc}"
            logger.exception("Monitoring agent unexpected error")
            errors.append(err_msg)
            return AgentResult(
                agent_id=self.identifier,
                status=ExecutionStatus.FAILED,
                investigation_id=context.investigation_id,
                execution_id=context.execution_id,
                source="monitoring",
                error_message=err_msg,
                errors=errors,
                warnings=warnings,
                output_metadata={"error": "unexpected_error"},
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_ms=duration_ms,
            )
