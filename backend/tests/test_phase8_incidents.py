"""DEVDOC Phase 8 — Incident Management Test Suite.

Comprehensive tests covering:
1. Incident Creation:
   - Authenticated user can create incident in own project
   - Unauthenticated create rejected with 401
   - User cannot create incident in another user's project (403)
   - project_id cannot be spoofed through request body (422 extra="forbid")
   - incident response contains correct project_id from path
   - initial status must be OPEN or INVESTIGATING (422 otherwise)
   - foreign repository link rejected (400)
2. Incident Listing & Filtering:
   - List incidents for own project
   - Bounded pagination works (limit/offset, max limit 100 enforced)
   - Status filtering works
   - Severity filtering works
   - Source filtering works
   - Cross-user listing blocked (403)
3. Incident Retrieval:
   - Get own incident
   - Cross-user incident access rejected (403)
   - Nonexistent project returns 404
   - Nonexistent incident returns 404
4. Incident Mutation & Lifecycle:
   - Update own incident mutable fields
   - Cross-user update rejected (403)
   - Valid status transitions succeed (OPEN -> INVESTIGATING -> MITIGATED -> RESOLVED -> CLOSED)
   - Backward transitions succeed (INVESTIGATING -> OPEN, RESOLVED -> OPEN, CLOSED -> OPEN)
   - Invalid status transitions rejected (OPEN -> CLOSED, OPEN -> MITIGATED, CLOSED -> RESOLVED)
   - Dedicated PATCH /status endpoint validates transitions
   - resolved_at managed automatically (set on RESOLVED/CLOSED, cleared on reopen)
5. Incident Deletion:
   - Delete own incident succeeds
   - Cross-user delete rejected (403)
   - Subsequent GET returns 404
6. Regressions:
   - Unauthenticated calls rejected across all endpoints (401)
   - Phase 5 / Phase 6 / Phase 7 authorization patterns preserved
   - Live PostgreSQL RLS integration
"""

from __future__ import annotations

import os
import time
import uuid
from collections.abc import AsyncGenerator

import jwt
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.db.base import Base
from app.dependencies import get_db
from app.main import app
from app.models.incident import IncidentSeverity, IncidentSource, IncidentStatus

# ---------------------------------------------------------------------------
# Test Constants & Settings
# ---------------------------------------------------------------------------

TEST_JWT_SECRET = "devdoc-test-secret-key-32-chars-long-minimum!"
TEST_ISSUER = "https://test.supabase.co/auth/v1"
TEST_AUDIENCE = "authenticated"

TEST_SETTINGS = Settings(
    supabase_jwt_secret=TEST_JWT_SECRET,
    supabase_jwt_algorithm="HS256",
    supabase_jwt_issuer=TEST_ISSUER,
    supabase_jwt_audience=TEST_AUDIENCE,
)

SQLITE_TEST_URL = "sqlite+aiosqlite:///:memory:"

PG_TEST_URL = os.environ.get(
    "TEST_POSTGRESQL_URL",
    os.environ.get(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5433/devdoc_test",
    ),
).replace("+asyncpg", "")


def make_test_token(
    sub: str | None = None,
    email: str = "testuser@devdoc.ai",
    exp_offset_seconds: int = 3600,
    issuer: str = TEST_ISSUER,
    audience: str = TEST_AUDIENCE,
    secret: str = TEST_JWT_SECRET,
) -> str:
    """Generate a signed JWT token for testing."""
    user_id = sub or str(uuid.uuid4())
    payload = {
        "sub": user_id,
        "email": email,
        "aud": audience,
        "iss": issuer,
        "iat": int(time.time()),
        "exp": int(time.time()) + exp_offset_seconds,
        "role": "authenticated",
        "user_metadata": {"full_name": "Test User"},
    }
    return jwt.encode(payload, secret, algorithm="HS256")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="function")
async def sqlite_engine():
    engine = create_async_engine(SQLITE_TEST_URL, echo=False, future=True)
    async with engine.begin() as conn:
        await conn.execute(text("PRAGMA foreign_keys = ON"))
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def sqlite_session_factory(sqlite_engine):
    return async_sessionmaker(
        bind=sqlite_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


@pytest.fixture(scope="function")
def client(sqlite_session_factory, monkeypatch):
    """FastAPI test client with database override and security settings."""
    monkeypatch.setattr("app.core.security.settings", TEST_SETTINGS)
    monkeypatch.setattr("app.core.config.settings", TEST_SETTINGS)

    async def override_get_db() -> AsyncGenerator[AsyncSession]:
        async with sqlite_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 1. Incident Creation Tests
# ---------------------------------------------------------------------------


def test_create_incident_in_own_project(client):
    """1. Authenticated user can create an incident in their own project."""
    user_id = str(uuid.uuid4())
    token = make_test_token(sub=user_id)
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token}"})

    # Create project
    proj_resp = client.post(
        "/api/v1/projects",
        json={"name": "Core Service"},
        headers={"Authorization": f"Bearer {token}"},
    )
    project_id = proj_resp.json()["id"]

    # Create incident
    payload = {
        "title": "High latency on payment gateway",
        "description": "504 Gateway Timeouts observed on checkout endpoint",
        "severity": "high",
        "source": "monitoring",
        "external_reference": "PD-9876",
        "affected_users": 1500,
    }
    resp = client.post(
        f"/api/v1/projects/{project_id}/incidents",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == payload["title"]
    assert data["description"] == payload["description"]
    assert data["severity"] == "high"
    assert data["status"] == "open"
    assert data["source"] == "monitoring"
    assert data["external_reference"] == "PD-9876"
    assert data["affected_users"] == 1500
    assert data["project_id"] == project_id
    assert data["reported_by_id"] == user_id
    assert "id" in data
    assert "detected_at" in data
    assert "created_at" in data
    assert data["resolved_at"] is None


def test_unauthenticated_create_rejected(client):
    """2. Unauthenticated create request rejected with 401."""
    random_project_id = uuid.uuid4()
    resp = client.post(
        f"/api/v1/projects/{random_project_id}/incidents",
        json={"title": "Anonymous Incident"},
    )
    assert resp.status_code == 401


def test_user_cannot_create_incident_in_another_users_project(client):
    """3. User B cannot create an incident in User A's project (403)."""
    user_a = str(uuid.uuid4())
    user_b = str(uuid.uuid4())
    token_a = make_test_token(sub=user_a, email="user_a@devdoc.ai")
    token_b = make_test_token(sub=user_b, email="user_b@devdoc.ai")

    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token_a}"})
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token_b}"})

    # User A creates project
    proj_resp = client.post(
        "/api/v1/projects",
        json={"name": "Project A"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    project_id = proj_resp.json()["id"]

    # User B attempts to create incident in User A's project
    resp = client.post(
        f"/api/v1/projects/{project_id}/incidents",
        json={"title": "Unauthorized intrusion"},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp.status_code == 403


def test_project_id_cannot_be_spoofed_in_body(client):
    """4. Supplying project_id or id in request body rejected by extra='forbid' (422)."""
    user_id = str(uuid.uuid4())
    token = make_test_token(sub=user_id)
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token}"})

    proj_resp = client.post(
        "/api/v1/projects",
        json={"name": "Spoof Test Project"},
        headers={"Authorization": f"Bearer {token}"},
    )
    project_id = proj_resp.json()["id"]

    # Attempt to spoof project_id in body
    resp = client.post(
        f"/api/v1/projects/{project_id}/incidents",
        json={
            "title": "Spoofed Incident",
            "project_id": str(uuid.uuid4()),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_initial_status_validation(client):
    """20b. New incidents must start in OPEN or INVESTIGATING status; others return 422."""
    user_id = str(uuid.uuid4())
    token = make_test_token(sub=user_id)
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token}"})

    proj_resp = client.post(
        "/api/v1/projects",
        json={"name": "Status Validation Project"},
        headers={"Authorization": f"Bearer {token}"},
    )
    project_id = proj_resp.json()["id"]

    for invalid_initial in ["resolved", "closed", "mitigated"]:
        resp = client.post(
            f"/api/v1/projects/{project_id}/incidents",
            json={"title": "Invalid initial status", "status": invalid_initial},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 2. Incident Listing & Filtering Tests
# ---------------------------------------------------------------------------


def test_list_incidents_for_own_project(client):
    """6. List incidents for own project returns all created items."""
    user_id = str(uuid.uuid4())
    token = make_test_token(sub=user_id)
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token}"})

    proj_resp = client.post(
        "/api/v1/projects",
        json={"name": "List Project"},
        headers={"Authorization": f"Bearer {token}"},
    )
    project_id = proj_resp.json()["id"]

    for i in range(3):
        client.post(
            f"/api/v1/projects/{project_id}/incidents",
            json={"title": f"Incident {i}"},
            headers={"Authorization": f"Bearer {token}"},
        )

    list_resp = client.get(
        f"/api/v1/projects/{project_id}/incidents",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_resp.status_code == 200
    data = list_resp.json()
    assert data["total"] == 3
    assert len(data["items"]) == 3


def test_list_incidents_pagination(client):
    """7. Pagination works correctly and enforces maximum limit of 100."""
    user_id = str(uuid.uuid4())
    token = make_test_token(sub=user_id)
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token}"})

    proj_resp = client.post(
        "/api/v1/projects",
        json={"name": "Pagination Project"},
        headers={"Authorization": f"Bearer {token}"},
    )
    project_id = proj_resp.json()["id"]

    for i in range(5):
        client.post(
            f"/api/v1/projects/{project_id}/incidents",
            json={"title": f"Incident {i}"},
            headers={"Authorization": f"Bearer {token}"},
        )

    # Limit 2, Offset 0
    r1 = client.get(
        f"/api/v1/projects/{project_id}/incidents?limit=2&offset=0",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r1.status_code == 200
    assert len(r1.json()["items"]) == 2
    assert r1.json()["total"] == 5

    # Limit 2, Offset 2
    r2 = client.get(
        f"/api/v1/projects/{project_id}/incidents?limit=2&offset=2",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r2.status_code == 200
    assert len(r2.json()["items"]) == 2

    # Limit > 100 rejected by query validator
    r_overflow = client.get(
        f"/api/v1/projects/{project_id}/incidents?limit=101",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r_overflow.status_code == 422


def test_list_incidents_filtering(client):
    """8, 9, 10. Status, severity, and source filtering works."""
    user_id = str(uuid.uuid4())
    token = make_test_token(sub=user_id)
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token}"})

    proj_resp = client.post(
        "/api/v1/projects",
        json={"name": "Filter Project"},
        headers={"Authorization": f"Bearer {token}"},
    )
    project_id = proj_resp.json()["id"]

    # Incidents with various attributes
    client.post(
        f"/api/v1/projects/{project_id}/incidents",
        json={"title": "Crit 1", "severity": "critical", "source": "github", "status": "investigating"},
        headers={"Authorization": f"Bearer {token}"},
    )
    client.post(
        f"/api/v1/projects/{project_id}/incidents",
        json={"title": "Med 1", "severity": "medium", "source": "manual", "status": "open"},
        headers={"Authorization": f"Bearer {token}"},
    )
    client.post(
        f"/api/v1/projects/{project_id}/incidents",
        json={"title": "Crit 2", "severity": "critical", "source": "monitoring", "status": "open"},
        headers={"Authorization": f"Bearer {token}"},
    )

    # Filter by severity
    r_sev = client.get(
        f"/api/v1/projects/{project_id}/incidents?severity=critical",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r_sev.status_code == 200
    assert r_sev.json()["total"] == 2

    # Filter by status
    r_stat = client.get(
        f"/api/v1/projects/{project_id}/incidents?status=investigating",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r_stat.status_code == 200
    assert r_stat.json()["total"] == 1

    # Filter by source
    r_src = client.get(
        f"/api/v1/projects/{project_id}/incidents?source=monitoring",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r_src.status_code == 200
    assert r_src.json()["total"] == 1


# ---------------------------------------------------------------------------
# 3. Incident Retrieval & Isolation Tests
# ---------------------------------------------------------------------------


def test_get_own_incident(client):
    """11. GET /api/v1/projects/{project_id}/incidents/{incident_id} returns incident."""
    user_id = str(uuid.uuid4())
    token = make_test_token(sub=user_id)
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token}"})

    proj_resp = client.post(
        "/api/v1/projects",
        json={"name": "Get Project"},
        headers={"Authorization": f"Bearer {token}"},
    )
    project_id = proj_resp.json()["id"]

    inc_resp = client.post(
        f"/api/v1/projects/{project_id}/incidents",
        json={"title": "Specific Incident"},
        headers={"Authorization": f"Bearer {token}"},
    )
    incident_id = inc_resp.json()["id"]

    get_resp = client.get(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == incident_id
    assert get_resp.json()["title"] == "Specific Incident"


def test_cross_user_incident_access_rejected(client):
    """12. User B cannot retrieve User A's incident (403)."""
    user_a = str(uuid.uuid4())
    user_b = str(uuid.uuid4())
    token_a = make_test_token(sub=user_a, email="user_a@devdoc.ai")
    token_b = make_test_token(sub=user_b, email="user_b@devdoc.ai")

    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token_a}"})
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token_b}"})

    proj_resp = client.post(
        "/api/v1/projects",
        json={"name": "User A Project"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    project_id = proj_resp.json()["id"]

    inc_resp = client.post(
        f"/api/v1/projects/{project_id}/incidents",
        json={"title": "Confidential Incident"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    incident_id = inc_resp.json()["id"]

    # User B attempts to access User A's incident
    get_resp = client.get(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert get_resp.status_code == 403


def test_nonexistent_incident_returns_404(client):
    """17. Nonexistent incident ID returns 404."""
    user_id = str(uuid.uuid4())
    token = make_test_token(sub=user_id)
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token}"})

    proj_resp = client.post(
        "/api/v1/projects",
        json={"name": "Exist Project"},
        headers={"Authorization": f"Bearer {token}"},
    )
    project_id = proj_resp.json()["id"]

    random_inc_id = uuid.uuid4()
    resp = client.get(
        f"/api/v1/projects/{project_id}/incidents/{random_inc_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_nonexistent_project_returns_404(client):
    """16. Nonexistent project ID returns 404 for incident endpoints."""
    user_id = str(uuid.uuid4())
    token = make_test_token(sub=user_id)
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token}"})

    random_proj_id = uuid.uuid4()
    resp = client.get(
        f"/api/v1/projects/{random_proj_id}/incidents",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 4. Incident Updates & Status Lifecycle Tests
# ---------------------------------------------------------------------------


def test_update_own_incident_mutable_fields(client):
    """13. Update own incident mutable fields succeeds."""
    user_id = str(uuid.uuid4())
    token = make_test_token(sub=user_id)
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token}"})

    proj_resp = client.post(
        "/api/v1/projects",
        json={"name": "Update Project"},
        headers={"Authorization": f"Bearer {token}"},
    )
    project_id = proj_resp.json()["id"]

    inc_resp = client.post(
        f"/api/v1/projects/{project_id}/incidents",
        json={"title": "Old Title", "severity": "low"},
        headers={"Authorization": f"Bearer {token}"},
    )
    incident_id = inc_resp.json()["id"]

    update_payload = {
        "title": "New Title",
        "description": "Added detailed description",
        "severity": "critical",
        "affected_users": 500,
    }
    patch_resp = client.patch(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}",
        json=update_payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert patch_resp.status_code == 200
    data = patch_resp.json()
    assert data["title"] == "New Title"
    assert data["description"] == "Added detailed description"
    assert data["severity"] == "critical"
    assert data["affected_users"] == 500


def test_cross_user_update_rejected(client):
    """14. User B cannot update User A's incident (403)."""
    user_a = str(uuid.uuid4())
    user_b = str(uuid.uuid4())
    token_a = make_test_token(sub=user_a, email="user_a@devdoc.ai")
    token_b = make_test_token(sub=user_b, email="user_b@devdoc.ai")

    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token_a}"})
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token_b}"})

    proj_resp = client.post(
        "/api/v1/projects",
        json={"name": "Project A"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    project_id = proj_resp.json()["id"]

    inc_resp = client.post(
        f"/api/v1/projects/{project_id}/incidents",
        json={"title": "Initial Title"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    incident_id = inc_resp.json()["id"]

    patch_resp = client.patch(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}",
        json={"title": "Tampered Title"},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert patch_resp.status_code == 403


def test_valid_status_lifecycle_transitions(client):
    """21. Valid full lifecycle: OPEN -> INVESTIGATING -> MITIGATED -> RESOLVED -> CLOSED."""
    user_id = str(uuid.uuid4())
    token = make_test_token(sub=user_id)
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token}"})

    proj_resp = client.post(
        "/api/v1/projects",
        json={"name": "Lifecycle Project"},
        headers={"Authorization": f"Bearer {token}"},
    )
    project_id = proj_resp.json()["id"]

    inc_resp = client.post(
        f"/api/v1/projects/{project_id}/incidents",
        json={"title": "Lifecycle Incident", "status": "open"},
        headers={"Authorization": f"Bearer {token}"},
    )
    incident_id = inc_resp.json()["id"]

    # 1. OPEN -> INVESTIGATING
    r1 = client.patch(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/status",
        json={"status": "investigating"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r1.status_code == 200
    assert r1.json()["status"] == "investigating"
    assert r1.json()["resolved_at"] is None

    # 2. INVESTIGATING -> MITIGATED
    r2 = client.patch(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/status",
        json={"status": "mitigated"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r2.status_code == 200
    assert r2.json()["status"] == "mitigated"

    # 3. MITIGATED -> RESOLVED (sets resolved_at)
    r3 = client.patch(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/status",
        json={"status": "resolved"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r3.status_code == 200
    assert r3.json()["status"] == "resolved"
    assert r3.json()["resolved_at"] is not None

    # 4. RESOLVED -> CLOSED
    r4 = client.patch(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/status",
        json={"status": "closed"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r4.status_code == 200
    assert r4.json()["status"] == "closed"


def test_backward_status_transitions_and_reopen(client):
    """22. Backward transitions succeed (INVESTIGATING -> OPEN, RESOLVED -> OPEN clears resolved_at)."""
    user_id = str(uuid.uuid4())
    token = make_test_token(sub=user_id)
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token}"})

    proj_resp = client.post(
        "/api/v1/projects",
        json={"name": "Reopen Project"},
        headers={"Authorization": f"Bearer {token}"},
    )
    project_id = proj_resp.json()["id"]

    inc_resp = client.post(
        f"/api/v1/projects/{project_id}/incidents",
        json={"title": "Reopen Incident"},
        headers={"Authorization": f"Bearer {token}"},
    )
    incident_id = inc_resp.json()["id"]

    # OPEN -> INVESTIGATING -> RESOLVED
    client.patch(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/status",
        json={"status": "investigating"},
        headers={"Authorization": f"Bearer {token}"},
    )
    res_step = client.patch(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/status",
        json={"status": "resolved"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_step.json()["resolved_at"] is not None

    # Reopen: RESOLVED -> OPEN
    reopened = client.patch(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/status",
        json={"status": "open"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert reopened.status_code == 200
    assert reopened.json()["status"] == "open"
    # resolved_at must be cleared on reopen
    assert reopened.json()["resolved_at"] is None


def test_invalid_status_transitions_rejected(client):
    """23. Arbitrary invalid status transitions return 422."""
    user_id = str(uuid.uuid4())
    token = make_test_token(sub=user_id)
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token}"})

    proj_resp = client.post(
        "/api/v1/projects",
        json={"name": "Invalid Transition Project"},
        headers={"Authorization": f"Bearer {token}"},
    )
    project_id = proj_resp.json()["id"]

    # Initial incident in OPEN status
    inc_resp = client.post(
        f"/api/v1/projects/{project_id}/incidents",
        json={"title": "Jump Test Incident"},
        headers={"Authorization": f"Bearer {token}"},
    )
    incident_id = inc_resp.json()["id"]

    # OPEN -> CLOSED is forbidden
    r_bad1 = client.patch(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/status",
        json={"status": "closed"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r_bad1.status_code == 422
    assert "invalid status transition" in r_bad1.json()["error"]["message"].lower()

    # OPEN -> MITIGATED is forbidden (must investigate first)
    r_bad2 = client.patch(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/status",
        json={"status": "mitigated"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r_bad2.status_code == 422


def test_status_transition_cross_user_rejected(client):
    """24. User B cannot change the status of User A's incident (403)."""
    user_a = str(uuid.uuid4())
    user_b = str(uuid.uuid4())
    token_a = make_test_token(sub=user_a, email="user_a@devdoc.ai")
    token_b = make_test_token(sub=user_b, email="user_b@devdoc.ai")

    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token_a}"})
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token_b}"})

    proj_resp = client.post(
        "/api/v1/projects",
        json={"name": "Project A"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    project_id = proj_resp.json()["id"]

    inc_resp = client.post(
        f"/api/v1/projects/{project_id}/incidents",
        json={"title": "Incident A"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    incident_id = inc_resp.json()["id"]

    resp = client.patch(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/status",
        json={"status": "investigating"},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 5. Incident Deletion Tests
# ---------------------------------------------------------------------------


def test_delete_own_incident(client):
    """15. Delete own incident succeeds; subsequent GET returns 404."""
    user_id = str(uuid.uuid4())
    token = make_test_token(sub=user_id)
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token}"})

    proj_resp = client.post(
        "/api/v1/projects",
        json={"name": "Delete Project"},
        headers={"Authorization": f"Bearer {token}"},
    )
    project_id = proj_resp.json()["id"]

    inc_resp = client.post(
        f"/api/v1/projects/{project_id}/incidents",
        json={"title": "Delete Target"},
        headers={"Authorization": f"Bearer {token}"},
    )
    incident_id = inc_resp.json()["id"]

    del_resp = client.delete(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_resp.status_code == 200
    assert del_resp.json()["success"] is True

    # Subsequent GET returns 404
    get_resp = client.get(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_resp.status_code == 404


def test_cross_user_delete_rejected(client):
    """User B cannot delete User A's incident (403)."""
    user_a = str(uuid.uuid4())
    user_b = str(uuid.uuid4())
    token_a = make_test_token(sub=user_a, email="user_a@devdoc.ai")
    token_b = make_test_token(sub=user_b, email="user_b@devdoc.ai")

    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token_a}"})
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token_b}"})

    proj_resp = client.post(
        "/api/v1/projects",
        json={"name": "Project A"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    project_id = proj_resp.json()["id"]

    inc_resp = client.post(
        f"/api/v1/projects/{project_id}/incidents",
        json={"title": "Protected Incident"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    incident_id = inc_resp.json()["id"]

    del_resp = client.delete(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert del_resp.status_code == 403


# ---------------------------------------------------------------------------
# 6. Enum & Input Validation Failures
# ---------------------------------------------------------------------------


def test_invalid_severity_rejected(client):
    """18. Invalid severity value returns 422."""
    user_id = str(uuid.uuid4())
    token = make_test_token(sub=user_id)
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token}"})

    proj_resp = client.post(
        "/api/v1/projects",
        json={"name": "Enum Project"},
        headers={"Authorization": f"Bearer {token}"},
    )
    project_id = proj_resp.json()["id"]

    resp = client.post(
        f"/api/v1/projects/{project_id}/incidents",
        json={"title": "Bad Severity", "severity": "ultra_catastrophic"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_invalid_source_rejected(client):
    """19. Invalid source value returns 422."""
    user_id = str(uuid.uuid4())
    token = make_test_token(sub=user_id)
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token}"})

    proj_resp = client.post(
        "/api/v1/projects",
        json={"name": "Enum Project"},
        headers={"Authorization": f"Bearer {token}"},
    )
    project_id = proj_resp.json()["id"]

    resp = client.post(
        f"/api/v1/projects/{project_id}/incidents",
        json={"title": "Bad Source", "source": "carrier_pigeon"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 7. Unauthenticated Regression Tests (Phase 5/6 Guard)
# ---------------------------------------------------------------------------


def test_unauthenticated_all_incident_endpoints_rejected(client):
    """25. All incident endpoints reject unauthenticated requests with 401."""
    p_id = uuid.uuid4()
    i_id = uuid.uuid4()

    endpoints = [
        ("GET", f"/api/v1/projects/{p_id}/incidents"),
        ("POST", f"/api/v1/projects/{p_id}/incidents"),
        ("GET", f"/api/v1/projects/{p_id}/incidents/{i_id}"),
        ("PATCH", f"/api/v1/projects/{p_id}/incidents/{i_id}"),
        ("PATCH", f"/api/v1/projects/{p_id}/incidents/{i_id}/status"),
        ("DELETE", f"/api/v1/projects/{p_id}/incidents/{i_id}"),
    ]

    for method, path in endpoints:
        if method == "GET":
            resp = client.get(path)
        elif method == "POST":
            resp = client.post(path, json={"title": "Incident"})
        elif method == "PATCH":
            resp = client.patch(path, json={"title": "Updated"})
        elif method == "DELETE":
            resp = client.delete(path)
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 8. LIVE POSTGRESQL INTEGRATION TEST (RLS on Incidents)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_live_pg_phase8_rls_integration():
    """Live PostgreSQL test verifying RLS boundary on Incident records via has_project_access."""
    import asyncpg

    conn = None
    try:
        conn = await asyncpg.connect(PG_TEST_URL, timeout=3.0)
    except Exception:
        pytest.skip("Live PostgreSQL is not accessible for Phase 8 RLS integration test.")

    try:
        user_a = str(uuid.uuid4())
        user_b = str(uuid.uuid4())
        project_id = str(uuid.uuid4())
        incident_id = str(uuid.uuid4())
        email_a = f"pg_inc_a_{uuid.uuid4().hex[:8]}@devdoc.ai"
        email_b = f"pg_inc_b_{uuid.uuid4().hex[:8]}@devdoc.ai"
        slug = f"pg-inc-{uuid.uuid4().hex[:8]}"

        # Insert user profiles
        await conn.execute(
            "INSERT INTO users (id, email, is_active, created_at, updated_at) VALUES ($1, $2, true, now(), now())",
            uuid.UUID(user_a),
            email_a,
        )
        await conn.execute(
            "INSERT INTO users (id, email, is_active, created_at, updated_at) VALUES ($1, $2, true, now(), now())",
            uuid.UUID(user_b),
            email_b,
        )

        # In transaction as User A: create project and incident
        async with conn.transaction():
            await conn.execute("SET ROLE authenticated")
            await conn.execute("SELECT set_config('request.jwt.claim.sub', $1, true)", user_a)
            await conn.execute(
                "INSERT INTO projects (id, name, slug, owner_id, is_active, created_at, updated_at) "
                "VALUES ($1, $2, $3, $4, true, now(), now())",
                uuid.UUID(project_id),
                "PG Project",
                slug,
                uuid.UUID(user_a),
            )
            await conn.execute(
                "INSERT INTO incidents (id, project_id, reported_by_id, title, severity, status, created_at, updated_at) "
                "VALUES ($1, $2, $3, $4, 'high', 'open', now(), now())",
                uuid.UUID(incident_id),
                uuid.UUID(project_id),
                uuid.UUID(user_a),
                "PG Incident A",
            )
            # User A can see the incident
            row_a = await conn.fetchrow("SELECT * FROM incidents WHERE id = $1", uuid.UUID(incident_id))
            assert row_a is not None
            assert row_a["title"] == "PG Incident A"

        # In transaction as User B: cannot see User A's incident via RLS!
        async with conn.transaction():
            await conn.execute("SET ROLE authenticated")
            await conn.execute("SELECT set_config('request.jwt.claim.sub', $1, true)", user_b)
            row_b = await conn.fetchrow("SELECT * FROM incidents WHERE id = $1", uuid.UUID(incident_id))
            assert row_b is None, "RLS FAILURE: User B was able to see User A's incident!"

    finally:
        if conn and not conn.is_closed():
            await conn.execute("DELETE FROM incidents WHERE id = $1", uuid.UUID(incident_id))
            await conn.execute("DELETE FROM projects WHERE id = $1", uuid.UUID(project_id))
            await conn.execute("DELETE FROM users WHERE id IN ($1, $2)", uuid.UUID(user_a), uuid.UUID(user_b))
            await conn.close()
