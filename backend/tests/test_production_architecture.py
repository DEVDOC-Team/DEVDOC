"""Phase 24 production architecture tests covering read-replica routing, Redis rate limiting, and resilience."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.core.config import settings
from app.core.rate_limit import TenantRateLimiter
from app.db.session import (
    AsyncReplicaSessionLocal,
    AsyncSessionLocal,
    engine,
    get_db,
    get_read_only_db,
    replica_engine,
)


def test_database_replica_routing_defaults_to_primary():
    """When no replica is configured, replica routing seamlessly uses the primary engine."""
    assert settings.database_replica_url is None or isinstance(settings.database_replica_url, str)
    if not settings.database_replica_url:
        assert replica_engine is engine
        assert AsyncReplicaSessionLocal is AsyncSessionLocal


@pytest.mark.asyncio
async def test_read_only_db_session_lifecycle():
    """Verify that read-only DB dependency yields an active session and cleans up safely."""
    from unittest.mock import patch

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    test_engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    test_sessionmaker = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    with patch("app.db.session.AsyncReplicaSessionLocal", test_sessionmaker):
        async for session in get_read_only_db():
            result = await session.execute(text("SELECT 1"))
            assert result.scalar() == 1
    await test_engine.dispose()


@pytest.mark.asyncio
async def test_rate_limiter_redis_unreachable_fallback_safety():
    """Verify that if an invalid Redis URL is provided, rate limiter falls back to in-memory."""
    bad_limiter = TenantRateLimiter(
        tenant_capacity=10,
        tenant_refill_per_second=1.0,
        ip_capacity=20,
        ip_refill_per_second=2.0,
        redis_url="redis://127.0.0.1:65534",  # Non-existent port
    )
    # Start should not raise; it falls back to in-memory
    await bad_limiter.start()
    assert bad_limiter._redis is None

    # Enforces limits in-memory
    decision = await bad_limiter.check_tenant("tenant-fallback-test")
    assert decision.allowed is True
    assert decision.remaining == 9
    await bad_limiter.close()
