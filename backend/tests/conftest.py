from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest

from app.core.rate_limit import rate_limiter


@pytest.fixture(autouse=True)
def reset_rate_limiter_buckets():
    """Reset in-memory rate limiter buckets and isolate unit tests from external Redis."""
    orig_redis = rate_limiter._redis_url
    rate_limiter._redis_url = ""
    rate_limiter._buckets.clear()
    yield
    rate_limiter._buckets.clear()
    rate_limiter._redis_url = orig_redis

