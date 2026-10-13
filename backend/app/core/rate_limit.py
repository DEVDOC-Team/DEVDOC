"""Tenant quotas and burst protection using atomic token buckets."""

from __future__ import annotations

import asyncio
import math
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from starlette.responses import Response

from app.core.config import settings
from app.dependencies import get_token_payload

_REDIS_TOKEN_BUCKET_SCRIPT = """
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local cost = tonumber(ARGV[3])
local ttl_ms = tonumber(ARGV[4])
local time = redis.call('TIME')
local now = tonumber(time[1]) * 1000 + math.floor(tonumber(time[2]) / 1000)
local tokens = tonumber(redis.call('HGET', KEYS[1], 'tokens'))
local last = tonumber(redis.call('HGET', KEYS[1], 'last_ms'))
if tokens == nil then
    tokens = capacity
    last = now
end
tokens = math.min(capacity, tokens + math.max(0, now - last) / 1000 * refill_rate)
local allowed = 0
local retry_ms = 0
if tokens >= cost then
    tokens = tokens - cost
    allowed = 1
else
    retry_ms = math.ceil((cost - tokens) / refill_rate * 1000)
end
redis.call('HSET', KEYS[1], 'tokens', tokens, 'last_ms', now)
redis.call('PEXPIRE', KEYS[1], ttl_ms)
return {allowed, math.floor(tokens), retry_ms}
"""


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    remaining: int
    retry_after_seconds: int


@dataclass
class _MemoryBucket:
    tokens: float
    updated_at: float


class TenantRateLimiter:
    """Atomic Redis token buckets with a bounded local backend for development/tests."""

    def __init__(
        self,
        *,
        tenant_capacity: int,
        tenant_refill_per_second: float,
        ip_capacity: int,
        ip_refill_per_second: float,
        redis_url: str = "",
        memory_max_entries: int = 10_000,
    ) -> None:
        self._tenant_capacity = tenant_capacity
        self._tenant_refill = tenant_refill_per_second
        self._ip_capacity = ip_capacity
        self._ip_refill = ip_refill_per_second
        self._memory_max_entries = memory_max_entries
        self._redis_url = redis_url
        self._redis: Redis | None = None
        self._buckets: dict[str, _MemoryBucket] = {}
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        if not settings.rate_limit_enabled or not self._redis_url:
            return
        self._redis = Redis.from_url(
            self._redis_url,
            decode_responses=False,
            socket_connect_timeout=2,
            socket_timeout=2,
            health_check_interval=30,
        )
        try:
            await self._redis.ping()
        except Exception:
            await self.close()
            raise

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None

    async def check_tenant(self, tenant_id: str) -> RateLimitDecision:
        return await self._consume(
            f"tenant:{tenant_id}",
            self._tenant_capacity,
            self._tenant_refill,
        )

    async def check_ip(self, client_ip: str) -> RateLimitDecision:
        return await self._consume(
            f"ip:{client_ip}",
            self._ip_capacity,
            self._ip_refill,
        )

    @property
    def tenant_capacity(self) -> int:
        return self._tenant_capacity

    @property
    def ip_capacity(self) -> int:
        return self._ip_capacity

    async def _consume(
        self,
        bucket_key: str,
        capacity: int,
        refill_per_second: float,
    ) -> RateLimitDecision:
        if not settings.rate_limit_enabled:
            return RateLimitDecision(True, capacity, 0)

        if self._redis is not None:
            ttl_ms = max(1_000, math.ceil(capacity / refill_per_second * 2_000))
            result = await self._redis.eval(
                _REDIS_TOKEN_BUCKET_SCRIPT,
                1,
                f"devdoc:ratelimit:{bucket_key}",
                capacity,
                refill_per_second,
                1,
                ttl_ms,
            )
            allowed, remaining, retry_ms = (int(value) for value in result)
            return RateLimitDecision(
                allowed=bool(allowed),
                remaining=max(0, remaining),
                retry_after_seconds=max(1, math.ceil(retry_ms / 1000)) if retry_ms else 0,
            )

        now = time.monotonic()
        idle_ttl = max(1.0, capacity / refill_per_second * 2)
        async with self._lock:
            self._remove_expired(now, idle_ttl)
            bucket = self._buckets.get(bucket_key)
            if bucket is None:
                if len(self._buckets) >= self._memory_max_entries:
                    return RateLimitDecision(False, 0, 1)
                bucket = _MemoryBucket(float(capacity), now)
                self._buckets[bucket_key] = bucket

            bucket.tokens = min(
                float(capacity),
                bucket.tokens + max(0.0, now - bucket.updated_at) * refill_per_second,
            )
            bucket.updated_at = now
            if bucket.tokens < 1:
                retry_after = max(1, math.ceil((1 - bucket.tokens) / refill_per_second))
                return RateLimitDecision(False, 0, retry_after)

            bucket.tokens -= 1
            return RateLimitDecision(True, math.floor(bucket.tokens), 0)

    def _remove_expired(self, now: float, idle_ttl: float) -> None:
        expired = [
            key
            for key, bucket in self._buckets.items()
            if now - bucket.updated_at > idle_ttl
        ]
        for key in expired:
            del self._buckets[key]


rate_limiter = TenantRateLimiter(
    tenant_capacity=settings.rate_limit_tenant_capacity,
    tenant_refill_per_second=settings.rate_limit_tenant_refill_per_second,
    ip_capacity=settings.rate_limit_ip_capacity,
    ip_refill_per_second=settings.rate_limit_ip_refill_per_second,
    redis_url=settings.rate_limit_redis_url.get_secret_value(),
    memory_max_entries=settings.rate_limit_memory_max_entries,
)


def _rate_limit_headers(
    capacity: int,
    remaining: int,
    retry_after_seconds: int = 0,
) -> dict[str, str]:
    headers = {
        "X-RateLimit-Limit": str(capacity),
        "X-RateLimit-Remaining": str(max(0, remaining)),
    }
    if retry_after_seconds:
        headers["Retry-After"] = str(retry_after_seconds)
    return headers


def _rate_limit_exception(capacity: int, retry_after_seconds: int) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Rate limit exceeded. Please retry later.",
        headers=_rate_limit_headers(capacity, 0, retry_after_seconds),
    )


async def enforce_tenant_rate_limit(
    request: Request,
    token_payload: dict[str, Any] = Depends(get_token_payload),
) -> None:
    """Apply a shared account-level quota after cryptographic JWT verification."""
    if not settings.rate_limit_enabled:
        return
    tenant_id = str(token_payload["sub"])
    decision = await rate_limiter.check_tenant(tenant_id)
    request.state.tenant_rate_limit = (
        rate_limiter.tenant_capacity,
        decision.remaining,
    )
    if not decision.allowed:
        raise _rate_limit_exception(
            rate_limiter.tenant_capacity,
            decision.retry_after_seconds,
        )


async def rate_limit_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Protect every request by source IP and publish quota headers."""
    if not settings.rate_limit_enabled or request.url.path in {
        "/api/v1/health",
        "/api/v1/ready",
    }:
        return await call_next(request)

    client_ip = request.client.host if request.client is not None else "unknown"
    decision = await rate_limiter.check_ip(client_ip)
    request.state.ip_rate_limit = (rate_limiter.ip_capacity, decision.remaining)
    if not decision.allowed:
        response = JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={
                "success": False,
                "error": {
                    "code": status.HTTP_429_TOO_MANY_REQUESTS,
                    "message": "Rate limit exceeded. Please retry later.",
                },
            },
            headers=_rate_limit_headers(
                rate_limiter.ip_capacity,
                0,
                decision.retry_after_seconds,
            ),
        )
    else:
        response = await call_next(request)

    limit_state = getattr(request.state, "tenant_rate_limit", None)
    if limit_state is None:
        limit_state = getattr(request.state, "ip_rate_limit", None)
    if limit_state is not None:
        capacity, remaining = limit_state
        response.headers.update(_rate_limit_headers(capacity, remaining))
    return response
