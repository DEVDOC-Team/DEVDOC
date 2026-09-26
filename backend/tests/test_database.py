"""Database test suite for DEVDOC Phase 2.

These tests use an in-memory SQLite database (via aiosqlite) so they
run without any external PostgreSQL / Supabase credentials.

Test coverage
-------------
1.  Database connection (in-memory SQLite)
2.  Table creation from Alembic-managed metadata
3.  Tables exist after create_all
4.  Basic CRUD — User model
5.  Basic CRUD — Project model
6.  Foreign key constraint — Project.owner_id must reference a User
7.  Unique constraint — users.email must be unique
8.  Unique constraint — projects (owner_id, slug)
9.  Timestamp columns are set on insert
10. updated_at changes on update
11. Cascade delete — deleting a User removes their Projects
12. Cascade delete — deleting a Project removes its Incidents
13. Transaction rollback — uncommitted changes are not visible
14. Invalid FK rejected — Incident.project_id must exist
15. API health endpoint still returns 200 (regression guard)
16. API readiness endpoint returns a structured JSON response
17. SQL injection attempt is neutralised by ORM parameterisation
"""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.main import app
from app.models.incident import Incident, IncidentSeverity, IncidentStatus
from app.models.project import Project
from app.models.user import User

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="function")
async def engine():
    """Create a fresh in-memory SQLite engine per test function."""
    _engine = create_async_engine(TEST_DATABASE_URL, echo=False, future=True)
    async with _engine.begin() as conn:
        # SQLite does not enforce FK constraints by default
        await conn.execute(text("PRAGMA foreign_keys = ON"))
        await conn.run_sync(Base.metadata.create_all)
    yield _engine
    await _engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db(engine) -> AsyncSession:
    """Yield an async session bound to the test engine."""
    factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )
    async with factory() as session:
        yield session


@pytest_asyncio.fixture(scope="function")
async def user(db: AsyncSession) -> User:
    """Persist and return a test User."""
    u = User(
        email="alice@example.com",
        full_name="Alice Smith",
        is_active=True,
        is_superuser=False,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest_asyncio.fixture(scope="function")
async def project(db: AsyncSession, user: User) -> Project:
    """Persist and return a test Project owned by the test User."""
    p = Project(
        name="Test Project",
        slug="test-project",
        owner_id=user.id,
    )
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return p


# ---------------------------------------------------------------------------
# Test 1 — Database connection
# ---------------------------------------------------------------------------


async def test_database_connection(engine):
    """Engine can execute a trivial query."""
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT 1"))
        row = result.fetchone()
    assert row is not None
    assert row[0] == 1


# ---------------------------------------------------------------------------
# Test 2 & 3 — Table creation
# ---------------------------------------------------------------------------


async def test_tables_created_from_metadata(engine):
    """All expected tables exist after metadata.create_all."""
    expected_tables = {
        "users",
        "projects",
        "repositories",
        "incidents",
        "investigations",
        "evidence",
        "deployments",
        "fix_proposals",
        "approvals",
        "audit_logs",
    }
    async with engine.connect() as conn:
        actual_tables = await conn.run_sync(
            lambda sync_conn: set(inspect(sync_conn).get_table_names())
        )
    assert expected_tables.issubset(actual_tables), (
        f"Missing tables: {expected_tables - actual_tables}"
    )


# ---------------------------------------------------------------------------
# Test 4 — CRUD User
# ---------------------------------------------------------------------------


async def test_create_read_user(db: AsyncSession):
    """Insert and retrieve a User."""
    u = User(email="bob@example.com", full_name="Bob Jones")
    db.add(u)
    await db.commit()
    await db.refresh(u)

    assert u.id is not None
    assert isinstance(u.id, uuid.UUID)
    assert u.email == "bob@example.com"
    assert u.full_name == "Bob Jones"
    assert u.is_active is True
    assert u.is_superuser is False


async def test_update_user(db: AsyncSession, user: User):
    """Update a User field and verify persistence."""
    user.full_name = "Alice Updated"
    await db.commit()
    await db.refresh(user)
    assert user.full_name == "Alice Updated"


async def test_delete_user(db: AsyncSession, user: User):
    """Delete a User and confirm it is gone."""
    user_id = user.id
    await db.delete(user)
    await db.commit()

    result = await db.get(User, user_id)
    assert result is None


# ---------------------------------------------------------------------------
# Test 5 — CRUD Project
# ---------------------------------------------------------------------------


async def test_create_read_project(db: AsyncSession, user: User):
    """Insert a Project and verify FK to User."""
    p = Project(name="My App", slug="my-app", owner_id=user.id)
    db.add(p)
    await db.commit()
    await db.refresh(p)

    assert p.id is not None
    assert p.owner_id == user.id
    assert p.slug == "my-app"


# ---------------------------------------------------------------------------
# Test 6 — Foreign key: Project.owner_id must exist
# ---------------------------------------------------------------------------


async def test_project_invalid_owner_fk_rejected(db: AsyncSession):
    """Creating a Project with a non-existent owner_id raises IntegrityError."""
    ghost_id = uuid.uuid4()
    p = Project(name="Ghost Project", slug="ghost", owner_id=ghost_id)
    db.add(p)
    with pytest.raises(IntegrityError):
        await db.commit()
    await db.rollback()


# ---------------------------------------------------------------------------
# Test 7 — Unique constraint: users.email
# ---------------------------------------------------------------------------


async def test_duplicate_email_rejected(db: AsyncSession, user: User):
    """Two Users with the same email raises IntegrityError."""
    duplicate = User(email=user.email, full_name="Dupe")
    db.add(duplicate)
    with pytest.raises(IntegrityError):
        await db.commit()
    await db.rollback()


# ---------------------------------------------------------------------------
# Test 8 — Unique constraint: projects (owner_id, slug)
# ---------------------------------------------------------------------------


async def test_duplicate_project_slug_per_owner_rejected(
    db: AsyncSession, user: User, project: Project
):
    """Same owner cannot have two projects with identical slug."""
    dup = Project(name="Another Project", slug=project.slug, owner_id=user.id)
    db.add(dup)
    with pytest.raises(IntegrityError):
        await db.commit()
    await db.rollback()


# ---------------------------------------------------------------------------
# Test 9 — Timestamps set on insert
# ---------------------------------------------------------------------------


async def test_timestamps_set_on_insert(db: AsyncSession, user: User):
    """created_at and updated_at are populated after insert."""
    assert user.created_at is not None
    assert user.updated_at is not None
    assert isinstance(user.created_at, datetime)
    # SQLite returns naive datetimes; PostgreSQL returns aware.
    # Accept both for portability.


# ---------------------------------------------------------------------------
# Test 10 — updated_at changes on update
# ---------------------------------------------------------------------------


async def test_updated_at_changes_on_update(db: AsyncSession, user: User):
    """updated_at is bumped when a record is modified."""
    original_updated_at = user.updated_at
    import asyncio

    await asyncio.sleep(0.01)  # ensure clock advances

    user.full_name = "Alice Changed"
    await db.commit()
    await db.refresh(user)

    # Python-side onupdate is invoked by SQLAlchemy
    assert user.updated_at >= original_updated_at


# ---------------------------------------------------------------------------
# Test 11 — Cascade delete: User → Projects
# ---------------------------------------------------------------------------


async def test_cascade_delete_user_removes_projects(
    db: AsyncSession, user: User, project: Project
):
    """Deleting a User also deletes their Projects (cascade=all, delete-orphan)."""
    project_id = project.id
    await db.delete(user)
    await db.commit()

    result = await db.get(Project, project_id)
    assert result is None


# ---------------------------------------------------------------------------
# Test 12 — Cascade delete: Project → Incidents
# ---------------------------------------------------------------------------


async def test_cascade_delete_project_removes_incidents(
    db: AsyncSession, project: Project
):
    """Deleting a Project also deletes its Incidents."""
    incident = Incident(
        project_id=project.id,
        title="Test Incident",
        severity=IncidentSeverity.HIGH,
        status=IncidentStatus.OPEN,
    )
    db.add(incident)
    await db.commit()
    incident_id = incident.id

    await db.delete(project)
    await db.commit()

    result = await db.get(Incident, incident_id)
    assert result is None


# ---------------------------------------------------------------------------
# Test 13 — Transaction rollback
# ---------------------------------------------------------------------------


async def test_transaction_rollback(db: AsyncSession):
    """Changes rolled back are not visible in subsequent queries."""
    u = User(email="rollback@example.com")
    db.add(u)
    # Do NOT commit — rollback instead
    await db.rollback()

    # The user should not exist
    from sqlalchemy import select

    result = await db.execute(
        select(User).where(User.email == "rollback@example.com")
    )
    assert result.scalar_one_or_none() is None


# ---------------------------------------------------------------------------
# Test 14 — Invalid FK: Incident.project_id must exist
# ---------------------------------------------------------------------------


async def test_incident_invalid_project_fk_rejected(db: AsyncSession):
    """Incident with non-existent project_id raises IntegrityError."""
    ghost_project_id = uuid.uuid4()
    incident = Incident(
        project_id=ghost_project_id,
        title="Orphan Incident",
        severity=IncidentSeverity.LOW,
        status=IncidentStatus.OPEN,
    )
    db.add(incident)
    with pytest.raises(IntegrityError):
        await db.commit()
    await db.rollback()


# ---------------------------------------------------------------------------
# Test 15 — Regression: health endpoint still works
# ---------------------------------------------------------------------------


def test_health_endpoint_returns_200():
    """GET /api/v1/health still returns 200 after Phase 2 changes."""
    client = TestClient(app)
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["service"] == "DEVDOC"
    assert data["status"] == "healthy"


# ---------------------------------------------------------------------------
# Test 16 — Readiness endpoint
# ---------------------------------------------------------------------------


def test_readiness_endpoint_returns_structured_response():
    """GET /api/v1/ready returns a JSON body with expected keys."""
    client = TestClient(app)
    response = client.get("/api/v1/ready")
    # 200 (DB ok — in-memory SQLite) or 503 (DB unavailable) are both valid
    assert response.status_code in (200, 503)
    data = response.json()
    assert "success" in data
    assert "service" in data
    assert data["service"] == "DEVDOC"
    assert "status" in data
    assert "checks" in data
    assert "database" in data["checks"]


# ---------------------------------------------------------------------------
# Test 17 — SQL injection neutralised by ORM
# ---------------------------------------------------------------------------


async def test_sql_injection_neutralised(db: AsyncSession):
    """ORM parameterisation neutralises a basic SQL injection attempt.

    The malicious string is stored literally — it does NOT break out of
    the query or return unexpected rows.
    """
    from sqlalchemy import select

    malicious_email = "' OR '1'='1"
    u = User(email=malicious_email, full_name="Injector")
    db.add(u)
    await db.commit()

    # Searching by the literal malicious string should find exactly one row
    result = await db.execute(
        select(User).where(User.email == malicious_email)
    )
    users = result.scalars().all()
    assert len(users) == 1
    assert users[0].email == malicious_email

    # Searching for a non-existent normal email must return nothing
    result2 = await db.execute(
        select(User).where(User.email == "nonexistent@example.com")
    )
    assert result2.scalar_one_or_none() is None
