"""Alembic migration environment for DEVDOC.

Supports both offline (SQL script generation) and online (live DB) modes.

Database URL strategy
---------------------
* Online migrations prefer ``DATABASE_URL`` so they use the same reachable
  endpoint as the application. This matters on IPv4-only hosts such as Render:
  Supabase's direct ``db.<project>.supabase.co`` endpoint is IPv6-only unless
  the project has IPv4 enabled. Use the Supabase Session Pooler URL there.
* ``DIRECT_DATABASE_URL`` is only a fallback for environments that can reach
  the direct endpoint. Standard Supabase ``postgresql://`` URLs are normalized
  to the async driver scheme before connecting.
* Alembic's synchronous migration operations run through SQLAlchemy's async
  connection bridge, using the same asyncpg driver as the FastAPI runtime.

Migrations must be applied with ``alembic upgrade head`` before serving traffic.
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
from app.core.config import normalize_async_database_url, settings  # noqa: E402
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
    1. DATABASE_URL from settings (normalized to asyncpg for PostgreSQL)
    2. DIRECT_DATABASE_URL from settings (normalized to asyncpg for PostgreSQL)
    3. Offline fallback to postgresql:// for DDL SQL rendering without credentials.

    Never falls back to the placeholder in alembic.ini.
    """
    url = settings.database_url
    if url:
        return normalize_async_database_url(url)

    direct_url = settings.direct_database_url
    if direct_url:
        return normalize_async_database_url(direct_url)

    if offline:
        return "postgresql://postgres:postgres@localhost:5432/postgres"

    raise RuntimeError(
        "No database URL configured for migrations. "
        "Set DATABASE_URL (recommended) or DIRECT_DATABASE_URL in your .env file."
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

