"""Bounded-cardinality Prometheus metrics registry and exporter for DEVDOC."""

from __future__ import annotations

import threading
from collections import defaultdict


class MetricsRegistry:
    """Thread-safe Prometheus metrics registry with strict bounded cardinality."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # Counters: key -> float
        self._http_requests: dict[tuple[str, str, str], int] = defaultdict(int)
        self._http_duration_sum: dict[tuple[str, str], float] = defaultdict(float)
        self._http_duration_count: dict[tuple[str, str], int] = defaultdict(int)

        self._investigations: dict[tuple[str], int] = defaultdict(int)
        self._investigation_duration_sum: float = 0.0
        self._investigation_duration_count: int = 0

        self._sandbox_verifications: dict[tuple[str, str], int] = defaultdict(int)

        self._llm_requests: dict[tuple[str, str], int] = defaultdict(int)
        self._llm_tokens: dict[tuple[str, str], int] = defaultdict(int)
        self._llm_cost_usd: dict[tuple[str], float] = defaultdict(float)
        self._llm_budget_rejections: int = 0

        self._approvals: dict[tuple[str], int] = defaultdict(int)

    def record_http_request(
        self,
        method: str,
        path_template: str,
        status_code: int,
        duration_seconds: float,
    ) -> None:
        # Bounded normalization: never allow raw IDs or unbounded paths
        clean_method = method.upper() if method in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"} else "OTHER"
        clean_template = path_template if path_template.startswith("/") else "/"
        status_class = f"{status_code // 100}xx" if 100 <= status_code < 600 else "unknown"

        with self._lock:
            self._http_requests[(clean_method, clean_template, status_class)] += 1
            self._http_duration_sum[(clean_method, clean_template)] += duration_seconds
            self._http_duration_count[(clean_method, clean_template)] += 1

    def record_investigation(self, status: str, duration_seconds: float = 0.0) -> None:
        clean_status = status.lower()[:32]
        with self._lock:
            self._investigations[(clean_status,)] += 1
            if duration_seconds > 0:
                self._investigation_duration_sum += duration_seconds
                self._investigation_duration_count += 1

    def record_sandbox_verification(self, provider: str, status: str) -> None:
        clean_provider = provider.lower()[:32]
        clean_status = status.lower()[:32]
        with self._lock:
            self._sandbox_verifications[(clean_provider, clean_status)] += 1

    def record_llm_request(
        self,
        provider: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        success: bool = True,
    ) -> None:
        clean_provider = provider.lower()[:32]
        outcome = "success" if success else "error"
        with self._lock:
            self._llm_requests[(clean_provider, outcome)] += 1
            self._llm_tokens[(clean_provider, "input")] += max(0, input_tokens)
            self._llm_tokens[(clean_provider, "output")] += max(0, output_tokens)
            self._llm_cost_usd[(clean_provider,)] += max(0.0, cost_usd)

    def record_llm_budget_rejection(self) -> None:
        with self._lock:
            self._llm_budget_rejections += 1

    def record_approval(self, status: str) -> None:
        clean_status = status.lower()[:32]
        with self._lock:
            self._approvals[(clean_status,)] += 1

    def export_prometheus_text(self) -> str:
        lines: list[str] = []
        with self._lock:
            # HTTP requests total
            lines.append("# HELP http_requests_total Total HTTP requests by method, route, and status class.")
            lines.append("# TYPE http_requests_total counter")
            for (method, path, status_class), count in sorted(self._http_requests.items()):
                lines.append(f'http_requests_total{{method="{method}",path_template="{path}",status_class="{status_class}"}} {count}')

            # HTTP duration
            lines.append("# HELP http_request_duration_seconds Total time spent in HTTP requests by method and route.")
            lines.append("# TYPE http_request_duration_seconds summary")
            for (method, path), total_sec in sorted(self._http_duration_sum.items()):
                count = self._http_duration_count[(method, path)]
                lines.append(f'http_request_duration_seconds_sum{{method="{method}",path_template="{path}"}} {total_sec:.6f}')
                lines.append(f'http_request_duration_seconds_count{{method="{method}",path_template="{path}"}} {count}')

            # Investigations
            lines.append("# HELP devdoc_investigation_runs_total Total investigation executions by final status.")
            lines.append("# TYPE devdoc_investigation_runs_total counter")
            for (status,), count in sorted(self._investigations.items()):
                lines.append(f'devdoc_investigation_runs_total{{status="{status}"}} {count}')

            if self._investigation_duration_count > 0:
                lines.append("# HELP devdoc_investigation_duration_seconds Cumulative seconds spent in investigations.")
                lines.append("# TYPE devdoc_investigation_duration_seconds summary")
                lines.append(f"devdoc_investigation_duration_seconds_sum {self._investigation_duration_sum:.4f}")
                lines.append(f"devdoc_investigation_duration_seconds_count {self._investigation_duration_count}")

            # Sandbox
            lines.append("# HELP devdoc_sandbox_verifications_total Total sandbox verification attempts by provider and outcome.")
            lines.append("# TYPE devdoc_sandbox_verifications_total counter")
            for (provider, status), count in sorted(self._sandbox_verifications.items()):
                lines.append(f'devdoc_sandbox_verifications_total{{provider="{provider}",status="{status}"}} {count}')

            # LLM metrics
            lines.append("# HELP devdoc_llm_requests_total Total LLM calls by provider and outcome.")
            lines.append("# TYPE devdoc_llm_requests_total counter")
            for (provider, outcome), count in sorted(self._llm_requests.items()):
                lines.append(f'devdoc_llm_requests_total{{provider="{provider}",outcome="{outcome}"}} {count}')

            lines.append("# HELP devdoc_llm_tokens_total Total LLM tokens consumed by provider and token type.")
            lines.append("# TYPE devdoc_llm_tokens_total counter")
            for (provider, token_type), tokens in sorted(self._llm_tokens.items()):
                lines.append(f'devdoc_llm_tokens_total{{provider="{provider}",type="{token_type}"}} {tokens}')

            lines.append("# HELP devdoc_llm_cost_usd_total Estimated cumulative LLM spend in USD.")
            lines.append("# TYPE devdoc_llm_cost_usd_total counter")
            for (provider,), cost in sorted(self._llm_cost_usd.items()):
                lines.append(f'devdoc_llm_cost_usd_total{{provider="{provider}"}} {cost:.6f}')

            lines.append("# HELP devdoc_llm_budget_rejections_total Total requests rejected due to exhausted LLM budget.")
            lines.append("# TYPE devdoc_llm_budget_rejections_total counter")
            lines.append(f"devdoc_llm_budget_rejections_total {self._llm_budget_rejections}")

            # Approvals
            lines.append("# HELP devdoc_approvals_total Human approval decisions recorded by outcome.")
            lines.append("# TYPE devdoc_approvals_total counter")
            for (status,), count in sorted(self._approvals.items()):
                lines.append(f'devdoc_approvals_total{{status="{status}"}} {count}')

        return "\n".join(lines) + "\n"


metrics_registry = MetricsRegistry()
