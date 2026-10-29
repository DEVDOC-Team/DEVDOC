"""Async SQLAlchemy engine and session factory.

Usage in FastAPI route handlers
--------------------------------
    from app.db.session import get_db

    @router.get("/example")
    async def example(db: AsyncSession = Depends(get_db)):
        ...

Connection strategy
-------------------
* Runtime (FastAPI) -- asyncpg via create_async_engine and AsyncSession
* Migrations (Alembic) -- asyncpg via DIRECT_DATABASE_URL
* Unit tests -- aiosqlite in-memory via TEST_DATABASE_URL override
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import normalize_async_database_url, settings
from app.core.logging import logger

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

_engine_kwargs: dict = {
    "echo": settings.db_echo,
    "future": True,
}

if settings.database_configured:
    database_url = normalize_async_database_url(settings.database_url)
    if "sqlite" not in database_url:
        _engine_kwargs.update(
            {
                "pool_size": settings.db_pool_size,
                "max_overflow": settings.db_max_overflow,
                "pool_timeout": settings.db_pool_timeout,
                "pool_recycle": settings.db_pool_recycle,
                "pool_pre_ping": True,
            }
        )
    engine = create_async_engine(database_url, **_engine_kwargs)
    logger.info("Database engine created")
else:
    # Fallback to in-memory SQLite so FastAPI starts without a real DB URL.
    # Tests and development without Supabase can still import models.
    _sqlite_url = "sqlite+aiosqlite:///:memory:"
    engine = create_async_engine(_sqlite_url, **_engine_kwargs)
    logger.warning(
        "DATABASE_URL not configured — using in-memory SQLite. "
        "Set DATABASE_URL in .env for Supabase/PostgreSQL."
    )

# ---------------------------------------------------------------------------
# Session factory & Optional Read Replica (Phase 24)
# ---------------------------------------------------------------------------

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

if settings.database_replica_url:
    replica_url = normalize_async_database_url(settings.database_replica_url)
    _replica_kwargs = dict(_engine_kwargs)
    if "sqlite" in replica_url:
        for k in ("pool_size", "max_overflow", "pool_timeout", "pool_recycle", "pool_pre_ping"):
            _replica_kwargs.pop(k, None)
    replica_engine = create_async_engine(replica_url, **_replica_kwargs)
    AsyncReplicaSessionLocal = async_sessionmaker(
        bind=replica_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    logger.info("Database read-replica engine configured")
else:
    replica_engine = engine
    AsyncReplicaSessionLocal = AsyncSessionLocal


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------


async def get_db() -> AsyncGenerator[AsyncSession]:
    """Yield an async primary database session; roll back on error and always close."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_read_only_db() -> AsyncGenerator[AsyncSession]:
    """Yield a read-only async session from the replica engine (or primary if unconfigured)."""
    async with AsyncReplicaSessionLocal() as session:
        try:
            yield session
            # Never commit writes on read-only session
            await session.rollback()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
