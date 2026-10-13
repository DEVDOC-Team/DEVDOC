from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.core import rate_limit
from app.core.config import Settings
from app.core.exceptions import http_exception_handler
from app.core.rate_limit import TenantRateLimiter, enforce_tenant_rate_limit
from app.dependencies import get_token_payload, require_active_user, require_project_access


@pytest.mark.asyncio
async def test_tenant_buckets_are_isolated_and_refill(monkeypatch: pytest.MonkeyPatch) -> None:
    now = [100.0]
    monkeypatch.setattr(rate_limit.time, "monotonic", lambda: now[0])
    limiter = TenantRateLimiter(
        tenant_capacity=2,
        tenant_refill_per_second=1,
        ip_capacity=2,
        ip_refill_per_second=1,
    )

    assert (await limiter.check_tenant("tenant-a")).remaining == 1
    assert (await limiter.check_tenant("tenant-a")).remaining == 0
    denied = await limiter.check_tenant("tenant-a")
    assert denied.allowed is False
    assert denied.retry_after_seconds == 1
    assert (await limiter.check_tenant("tenant-b")).allowed is True

    now[0] += 1.0
    refilled = await limiter.check_tenant("tenant-a")
    assert refilled.allowed is True
    assert refilled.remaining == 0


@pytest.mark.asyncio
async def test_memory_backend_bounds_bucket_cardinality() -> None:
    limiter = TenantRateLimiter(
        tenant_capacity=2,
        tenant_refill_per_second=1,
        ip_capacity=2,
        ip_refill_per_second=1,
        memory_max_entries=1,
    )

    assert (await limiter.check_tenant("tenant-a")).allowed is True
    overflow = await limiter.check_tenant("tenant-b")
    assert overflow.allowed is False
    assert overflow.retry_after_seconds == 1


def test_tenant_quota_returns_429_and_rate_limit_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limiter = TenantRateLimiter(
        tenant_capacity=1,
        tenant_refill_per_second=0.01,
        ip_capacity=10,
        ip_refill_per_second=1,
    )
    monkeypatch.setattr(rate_limit, "rate_limiter", limiter)
    tenant_id = str(uuid.uuid4())
    test_app = FastAPI()
    test_app.middleware("http")(rate_limit.rate_limit_middleware)
    test_app.dependency_overrides[get_token_payload] = lambda: {"sub": tenant_id}
    test_app.add_exception_handler(HTTPException, http_exception_handler)

    @test_app.get("/resource", dependencies=[Depends(enforce_tenant_rate_limit)])
    async def resource() -> dict[str, bool]:
        return {"ok": True}

    with TestClient(test_app) as client:
        first = client.get("/resource")
        second = client.get("/resource")

    assert first.status_code == 200
    assert first.headers["X-RateLimit-Limit"] == "1"
    assert first.headers["X-RateLimit-Remaining"] == "0"
    assert second.status_code == 429
    assert second.headers["Retry-After"] == "100"
    assert second.headers["X-RateLimit-Remaining"] == "0"


def test_ip_bucket_protects_unauthenticated_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limiter = TenantRateLimiter(
        tenant_capacity=10,
        tenant_refill_per_second=1,
        ip_capacity=1,
        ip_refill_per_second=0.01,
    )
    monkeypatch.setattr(rate_limit, "rate_limiter", limiter)
    test_app = FastAPI()
    test_app.middleware("http")(rate_limit.rate_limit_middleware)

    @test_app.get("/public")
    async def public() -> dict[str, bool]:
        return {"ok": True}

    with TestClient(test_app) as client:
        first = client.get("/public")
        second = client.get("/public")

    assert first.status_code == 200
    assert first.headers["X-RateLimit-Limit"] == "1"
    assert second.status_code == 429
    assert second.headers["Retry-After"] == "100"


def test_production_settings_require_shared_redis() -> None:
    with pytest.raises(ValueError, match="RATE_LIMIT_REDIS_URL"):
        Settings(environment="production", trusted_hosts=["api.example.com"])

    production_settings = Settings(
        environment="production",
        trusted_hosts=["api.example.com"],
        rate_limit_redis_url="redis://localhost:6379/0",
    )
    assert production_settings.rate_limit_enabled is True

    with pytest.raises(ValueError, match="cannot be disabled"):
        Settings(
            environment="production",
            trusted_hosts=["api.example.com"],
            rate_limit_enabled=False,
            rate_limit_redis_url="redis://localhost:6379/0",
        )


def test_protected_api_route_enforces_quota_through_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.main import app

    limiter = TenantRateLimiter(
        tenant_capacity=1,
        tenant_refill_per_second=0.01,
        ip_capacity=10,
        ip_refill_per_second=1,
    )
    monkeypatch.setattr(rate_limit, "rate_limiter", limiter)
    tenant_id = uuid.uuid4()
    project_id = uuid.uuid4()
    monkeypatch.setitem(
        app.dependency_overrides,
        get_token_payload,
        lambda: {"sub": str(tenant_id)},
    )
    monkeypatch.setitem(
        app.dependency_overrides,
        require_active_user,
        lambda: SimpleNamespace(id=tenant_id),
    )
    monkeypatch.setitem(
        app.dependency_overrides,
        require_project_access,
        lambda: SimpleNamespace(id=project_id, name="test", owner_id=tenant_id),
    )

    with TestClient(app) as client:
        path = f"/api/v1/auth/projects/{project_id}/verify-access"
        first = client.get(path)
        second = client.get(path)

    assert first.status_code == 200
    assert first.headers["X-RateLimit-Limit"] == "1"
    assert second.status_code == 429
    assert second.headers["Retry-After"] == "100"
