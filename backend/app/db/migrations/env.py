"""Alembic migration environment for DEVDOC.

Supports both offline (SQL script generation) and online (live DB) modes.

Database URL strategy
---------------------
* Online migrations use ``DIRECT_DATABASE_URL`` from settings.
  This must be a synchronous driver URL (e.g. postgresql+psycopg2://…)
  because Alembic's built-in migration runner is synchronous.
* The async runtime URL (postgresql+asyncpg://…) used by FastAPI is
  kept separate to avoid driver conflicts.

Tables are NEVER created automatically on application startup.
Run ``alembic upgrade head`` explicitly in your deployment pipeline.
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# ---------------------------------------------------------------------------
# Ensure the backend root is on sys.path so app.* imports resolve correctly
# when Alembic is invoked from any working directory.
# ---------------------------------------------------------------------------
_backend_root = Path(__file__).resolve().parents[3]
if str(_backend_root) not in sys.path:
    sys.path.insert(0, str(_backend_root))

# ---------------------------------------------------------------------------
# Import settings and ALL models so Alembic can detect schema changes.
# app.models.__init__ re-exports every model class and Base.
# ---------------------------------------------------------------------------
from app.core.config import settings  # noqa: E402
from app.models import Base  # noqa: E402  # registers all table metadata

# ---------------------------------------------------------------------------
# Alembic config object
# ---------------------------------------------------------------------------
config = context.config

# Configure stdlib logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# The metadata Alembic uses to autogenerate migrations
target_metadata = Base.metadata


def _get_url(offline: bool = False) -> str:
    """Return the database URL for migrations.

    Precedence:
    1. DIRECT_DATABASE_URL from settings (psycopg2/psycopg driver)
    2. DATABASE_URL from settings (asyncpg or psycopg2)
    3. Offline fallback to postgresql:// for DDL SQL rendering without credentials.

    Never falls back to the placeholder in alembic.ini.
    """
    direct_url = settings.direct_database_url
    if direct_url:
        return direct_url

    url = settings.database_url
    if url:
        return url

    if offline:
        return "postgresql://postgres:postgres@localhost:5432/postgres"

    raise RuntimeError(
        "No database URL configured for migrations. "
        "Set DIRECT_DATABASE_URL or DATABASE_URL in your .env file."
    )


def run_migrations_offline() -> None:
    """Render migrations as SQL without connecting to the database.

    Useful for reviewing SQL before applying, or for environments where
    the migration is applied by a DBA rather than the application.
    """
    url = _get_url(offline=True)
    # Strip async prefix for offline dialect rendering if present
    if "+asyncpg" in url:
        url = url.replace("+asyncpg", "")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    """Run migrations within an established connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations(url: str) -> None:
    """Apply migrations asynchronously using asyncpg/create_async_engine."""
    from sqlalchemy.ext.asyncio import create_async_engine

    connectable = create_async_engine(
        url,
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Apply migrations against a live database connection."""
    url = _get_url(offline=False)

    if "+asyncpg" in url or "+aiosqlite" in url:
        import asyncio

        asyncio.run(run_async_migrations(url))
    else:
        configuration = config.get_section(config.config_ini_section, {})
        configuration["sqlalchemy.url"] = url

        connectable = engine_from_config(
            configuration,
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )

        with connectable.connect() as connection:
            do_run_migrations(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

