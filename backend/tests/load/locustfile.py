"""Locust load test suite for DEVDOC API.

Safe, conservative performance scenarios designed for local or staging benchmarking.
Guarantees zero live LLM charges by exercising lightweight endpoints, read paths,
authentication boundaries, and error handlers.
"""

from __future__ import annotations

import os
import uuid

from locust import HttpUser, between, task


class DevDocLoadUser(HttpUser):
    """Simulates realistic API client traffic across health, reads, and auth boundaries."""

    wait_time = between(0.05, 0.2)

    @task(5)
    def test_health_check(self) -> None:
        with self.client.get("/api/v1/health", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Unexpected health status: {response.status_code}")

    @task(3)
    def test_readiness_check(self) -> None:
        with self.client.get("/api/v1/ready", catch_response=True) as response:
            if response.status_code in (200, 503):
                # 200 when DB is live, 503 when local dev without DB — both valid responses
                response.success()
            else:
                response.failure(f"Unexpected ready status: {response.status_code}")

    @task(3)
    def test_api_root(self) -> None:
        with self.client.get("/", catch_response=True) as response:
            if response.status_code in (200, 429):
                response.success()
            else:
                response.failure(f"Unexpected root status: {response.status_code}")

    @task(3)
    def test_prometheus_metrics(self) -> None:
        with self.client.get("/metrics", catch_response=True) as response:
            if (response.status_code == 200 and "text/plain" in response.headers.get("content-type", "")) or response.status_code == 429:
                response.success()
            else:
                response.failure(f"Metrics failed: {response.status_code}")

    @task(2)
    def test_unauthorized_rejection(self) -> None:
        """Verify unauthenticated requests are safely rejected with 401 (or 429 when rate limited)."""
        with self.client.get("/api/v1/projects", catch_response=True) as response:
            if response.status_code in (401, 429):
                response.success()
            else:
                response.failure(f"Expected 401 Unauthorized or 429 Rate Limited, got {response.status_code}")

    @task(1)
    def test_nonexistent_project_rejection(self) -> None:
        """Verify random UUID lookups fail cleanly without server errors."""
        random_id = str(uuid.uuid4())
        with self.client.get(f"/api/v1/projects/{random_id}", name="/api/v1/projects/[id]", catch_response=True) as response:
            if response.status_code in (401, 403, 404, 429):
                response.success()
            else:
                response.failure(f"Unexpected status for nonexistent resource: {response.status_code}")

