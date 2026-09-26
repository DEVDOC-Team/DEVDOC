"""Async SQLAlchemy engine and session factory.

Usage in FastAPI route handlers
--------------------------------
    from app.db.session import get_db

    @router.get("/example")
    async def example(db: AsyncSession = Depends(get_db)):
        ...

Connection strategy
-------------------
* Runtime (FastAPI)  — asyncpg via create_async_engine + AsyncSession
* Migrations (Alembic) — synchronous psycopg2 via DIRECT_DATABASE_URL
* Unit tests — aiosqlite in-memory via TEST_DATABASE_URL override
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.core.logging import logger

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

_engine_kwargs: dict = {
    "echo": settings.db_echo,
    "future": True,
}

if settings.database_configured:
    _engine_kwargs.update(
        {
            "pool_size": settings.db_pool_size,
            "max_overflow": settings.db_max_overflow,
            "pool_timeout": settings.db_pool_timeout,
            "pool_recycle": settings.db_pool_recycle,
            "pool_pre_ping": True,
        }
    )
    engine = create_async_engine(settings.database_url, **_engine_kwargs)
    logger.info("Database engine created (pool_size=%d)", settings.db_pool_size)
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
# Session factory
# ---------------------------------------------------------------------------

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------


async def get_db() -> AsyncGenerator[AsyncSession]:
    """Yield an async database session; roll back on error and always close."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
