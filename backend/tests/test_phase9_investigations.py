"""DEVDOC Phase 9 — Investigation API Test Suite.

Comprehensive tests covering:
1. Investigation Creation:
   - Authenticated user can create investigation in own project/incident
   - Creation with status=running sets started_at
   - Unauthenticated create rejected with 401
   - User cannot create investigation in another user's project (403)
   - project_id and incident_id cannot be spoofed in request body (422)
   - id and timestamps cannot be spoofed in body (422)
   - Initial status validation (PENDING or RUNNING allowed; COMPLETED/FAILED rejected)
   - Incident not belonging to project rejected (404)
   - Active investigation conflict (409) when PENDING/RUNNING already exists
   - Creation succeeds after previous investigation is COMPLETED
2. Investigation Listing & Pagination:
   - List investigations for own incident
   - Bounded pagination (limit/offset, max limit 100)
   - Status filtering
   - Cross-user listing blocked (403)
3. Investigation Retrieval:
   - Get own investigation returns full normalized representation
   - Cross-user investigation access rejected (403)
   - Investigation queried under wrong incident returns 404
   - Nonexistent investigation/incident/project returns 404
4. Investigation Mutation:
   - Update mutable fields (summary, root_cause_summary, confidence_score)
   - Cross-user update rejected (403)
   - Immutable fields rejected (422)
5. Status Lifecycle & Finite State Machine:
   - PENDING -> RUNNING -> COMPLETED
   - PENDING -> CANCELLED
   - RUNNING -> FAILED
   - RUNNING -> CANCELLED
   - Invalid transitions rejected (PENDING -> COMPLETED, COMPLETED -> RUNNING, etc. 422)
   - Idempotent same-state transition succeeds (200)
   - Cross-user status transition rejected (403)
6. Investigation Deletion:
   - Delete own investigation succeeds
   - Subsequent GET returns 404
   - Cross-user delete rejected (403)
7. Regressions & Security:
   - All endpoints reject unauthenticated calls with 401
   - Invalid enums and malformed UUIDs rejected with 422
   - Live PostgreSQL 16 Row Level Security (RLS) integration
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
from app.models.investigation import InvestigationStatus

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
    email: str | None = None,
    exp_offset_seconds: int = 3600,
    issuer: str = TEST_ISSUER,
    audience: str = TEST_AUDIENCE,
    secret: str = TEST_JWT_SECRET,
) -> str:
    """Generate a signed JWT token for testing."""
    user_id = sub or str(uuid.uuid4())
    user_email = email or f"user_{uuid.uuid4().hex[:8]}@devdoc.ai"
    payload = {
        "sub": user_id,
        "email": user_email,
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


def create_user_project_and_incident(
    client: TestClient,
    user_id: str | None = None,
    proj_name: str = "Production Platform",
    incident_title: str = "Database Connection Timeout",
) -> tuple[str, str, str, str]:
    """Helper to provision a user, project, and incident for tests."""
    uid = user_id or str(uuid.uuid4())
    token = make_test_token(sub=uid)
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token}"})

    proj_resp = client.post(
        "/api/v1/projects",
        json={"name": proj_name},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert proj_resp.status_code == 201
    project_id = proj_resp.json()["id"]

    inc_resp = client.post(
        f"/api/v1/projects/{project_id}/incidents",
        json={"title": incident_title, "severity": "high", "source": "monitoring"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert inc_resp.status_code == 201
    incident_id = inc_resp.json()["id"]

    return uid, token, project_id, incident_id


# ---------------------------------------------------------------------------
# 1. Investigation Creation Tests
# ---------------------------------------------------------------------------


def test_create_investigation_in_own_incident(client):
    """1. Authenticated user can create an investigation in their own incident."""
    uid, token, project_id, incident_id = create_user_project_and_incident(client)

    payload = {
        "summary": "Investigating high error rates on payment checkout",
        "status": "pending",
    }
    resp = client.post(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/investigations",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["summary"] == payload["summary"]
    assert data["status"] == "pending"
    assert data["project_id"] == project_id
    assert data["incident_id"] == incident_id
    assert data["initiated_by_id"] == uid
    assert data["started_at"] is None
    assert data["completed_at"] is None
    assert data["tokens_used"] == 0
    assert data["estimated_cost_usd"] == 0
    assert "root_cause_summary" not in data
    assert "confidence_score" not in data


def test_create_investigation_running_status_sets_started_at(client):
    """2. Creating an investigation directly with status=running sets started_at."""
    _, token, project_id, incident_id = create_user_project_and_incident(client)

    payload = {
        "summary": "Urgent immediate analysis of gateway failure",
        "status": "running",
    }
    resp = client.post(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/investigations",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "running"
    assert data["started_at"] is not None
    assert data["completed_at"] is None


def test_unauthenticated_create_rejected(client):
    """3. Unauthenticated create request is rejected with 401."""
    _, _, project_id, incident_id = create_user_project_and_incident(client)

    resp = client.post(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/investigations",
        json={"summary": "Unauthorized attempt"},
    )
    assert resp.status_code == 401


def test_user_cannot_create_investigation_in_another_users_project(client):
    """4. User B cannot create an investigation in User A's project (403)."""
    _, _, proj_a_id, inc_a_id = create_user_project_and_incident(client, proj_name="User A App")

    # User B
    user_b_id = str(uuid.uuid4())
    token_b = make_test_token(sub=user_b_id, email="user_b@devdoc.ai")
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token_b}"})

    resp = client.post(
        f"/api/v1/projects/{proj_a_id}/incidents/{inc_a_id}/investigations",
        json={"summary": "Malicious probe"},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp.status_code == 403


def test_project_id_cannot_be_spoofed_in_body(client):
    """5. Supplying project_id in request body is rejected with 422 (extra="forbid")."""
    _, token, project_id, incident_id = create_user_project_and_incident(client)

    resp = client.post(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/investigations",
        json={"summary": "Spoof test", "project_id": str(uuid.uuid4())},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_incident_id_cannot_be_spoofed_in_body(client):
    """6. Supplying incident_id in request body is rejected with 422 (extra="forbid")."""
    _, token, project_id, incident_id = create_user_project_and_incident(client)

    resp = client.post(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/investigations",
        json={"summary": "Spoof test", "incident_id": str(uuid.uuid4())},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_id_and_timestamps_cannot_be_spoofed_in_body(client):
    """7. Supplying id, created_at, or updated_at in request body is rejected with 422."""
    _, token, project_id, incident_id = create_user_project_and_incident(client)

    for field in ["id", "created_at", "updated_at", "started_at", "completed_at", "root_cause_summary", "confidence_score"]:
        resp = client.post(
            f"/api/v1/projects/{project_id}/incidents/{incident_id}/investigations",
            json={"summary": "Spoof test", field: "2026-01-01T00:00:00Z"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422, f"Expected 422 for forbidden field '{field}'"


def test_initial_status_validation(client):
    """8. New investigations must start in PENDING or RUNNING status; others rejected with 422."""
    _, token, project_id, incident_id = create_user_project_and_incident(client)

    for invalid_status in ["completed", "failed", "cancelled"]:
        resp = client.post(
            f"/api/v1/projects/{project_id}/incidents/{incident_id}/investigations",
            json={"summary": "Invalid initial status", "status": invalid_status},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422


def test_incident_not_belonging_to_project_rejected(client):
    """9. Attempting to create investigation with an incident belonging to another project returns 404."""
    uid, token, proj_a_id, inc_a_id = create_user_project_and_incident(client, proj_name="Project A")

    # Create Project B for same user
    proj_b_resp = client.post(
        "/api/v1/projects",
        json={"name": "Project B"},
        headers={"Authorization": f"Bearer {token}"},
    )
    proj_b_id = proj_b_resp.json()["id"]

    # Request to Project B using inc_a_id (which belongs to Project A)
    resp = client.post(
        f"/api/v1/projects/{proj_b_id}/incidents/{inc_a_id}/investigations",
        json={"summary": "Cross-project mismatch test"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
    error_msg = resp.json().get("detail") or resp.json().get("error", {}).get("message", "")
    assert f"Incident '{inc_a_id}' not found in project '{proj_b_id}'" in error_msg


def test_active_investigation_conflict_409(client):
    """10. Creating a second investigation when one is already PENDING or RUNNING returns 409 Conflict."""
    _, token, project_id, incident_id = create_user_project_and_incident(client)

    # First investigation: PENDING
    first_resp = client.post(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/investigations",
        json={"summary": "First active investigation", "status": "pending"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert first_resp.status_code == 201

    # Second investigation attempt on same incident
    second_resp = client.post(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/investigations",
        json={"summary": "Second concurrent attempt", "status": "pending"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert second_resp.status_code == 409
    conflict_msg = second_resp.json().get("detail") or second_resp.json().get("error", {}).get("message", "")
    assert "already in progress" in conflict_msg


def test_create_second_investigation_after_first_completed(client):
    """11. After the active investigation transitions to COMPLETED, creating a new investigation succeeds."""
    _, token, project_id, incident_id = create_user_project_and_incident(client)

    # First investigation
    first_resp = client.post(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/investigations",
        json={"summary": "Initial investigation", "status": "running"},
        headers={"Authorization": f"Bearer {token}"},
    )
    inv1_id = first_resp.json()["id"]

    # Complete it
    comp_resp = client.patch(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/investigations/{inv1_id}/status",
        json={"status": "completed"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert comp_resp.status_code == 200

    # Second investigation now succeeds
    second_resp = client.post(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/investigations",
        json={"summary": "Follow-up investigation", "status": "pending"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert second_resp.status_code == 201
    assert second_resp.json()["id"] != inv1_id


# ---------------------------------------------------------------------------
# 2. Investigation Listing & Pagination Tests
# ---------------------------------------------------------------------------


def test_list_investigations_for_own_incident(client):
    """12. List investigations for own incident returns paginated list."""
    _, token, project_id, incident_id = create_user_project_and_incident(client)

    # Create an investigation
    client.post(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/investigations",
        json={"summary": "Inv 1"},
        headers={"Authorization": f"Bearer {token}"},
    )

    resp = client.get(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/investigations",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["summary"] == "Inv 1"


def test_list_investigations_pagination_bounds(client):
    """13. Pagination limits (default 20, max 100) are enforced."""
    _, token, project_id, incident_id = create_user_project_and_incident(client)

    # Query with limit > 100 is capped to 100
    resp = client.get(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/investigations?limit=100&offset=0",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["limit"] == 100

    # Limit > 100 rejected by FastAPI Query(le=100) validation
    resp_over = client.get(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/investigations?limit=150",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_over.status_code == 422


def test_list_investigations_status_filtering(client):
    """14. Status filtering on investigation list works properly."""
    _, token, project_id, incident_id = create_user_project_and_incident(client)

    # Create investigation in pending
    resp_create = client.post(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/investigations",
        json={"summary": "Pending investigation", "status": "pending"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_create.status_code == 201

    # Filter for pending -> returns 1
    resp_p = client.get(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/investigations?status=pending",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_p.status_code == 200
    assert resp_p.json()["total"] == 1

    # Filter for running -> returns 0
    resp_r = client.get(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/investigations?status=running",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_r.status_code == 200
    assert resp_r.json()["total"] == 0


def test_list_investigations_cross_user_rejected(client):
    """15. User B cannot list investigations in User A's incident (403)."""
    _, _, proj_a_id, inc_a_id = create_user_project_and_incident(client)

    token_b = make_test_token(sub=str(uuid.uuid4()))
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token_b}"})

    resp = client.get(
        f"/api/v1/projects/{proj_a_id}/incidents/{inc_a_id}/investigations",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 3. Investigation Retrieval Tests
# ---------------------------------------------------------------------------


def test_get_own_investigation(client):
    """16. Get own investigation returns full normalized data."""
    _, token, project_id, incident_id = create_user_project_and_incident(client)

    create_resp = client.post(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/investigations",
        json={"summary": "Root cause drilldown", "status": "pending"},
        headers={"Authorization": f"Bearer {token}"},
    )
    inv_id = create_resp.json()["id"]

    resp = client.get(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/investigations/{inv_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == inv_id
    assert data["summary"] == "Root cause drilldown"
    assert data["status"] == "pending"


def test_get_investigation_cross_user_rejected(client):
    """17. User B cannot retrieve User A's investigation (403)."""
    _, token_a, proj_a_id, inc_a_id = create_user_project_and_incident(client)

    create_resp = client.post(
        f"/api/v1/projects/{proj_a_id}/incidents/{inc_a_id}/investigations",
        json={"summary": "Private A investigation"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    inv_id = create_resp.json()["id"]

    token_b = make_test_token(sub=str(uuid.uuid4()))
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token_b}"})

    resp = client.get(
        f"/api/v1/projects/{proj_a_id}/incidents/{inc_a_id}/investigations/{inv_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp.status_code == 403


def test_get_investigation_wrong_incident_returns_404(client):
    """18. Querying investigation with an incident it does not belong to returns 404."""
    _, token, project_id, inc_a_id = create_user_project_and_incident(client)

    # Create second incident in same project
    inc_b_resp = client.post(
        f"/api/v1/projects/{project_id}/incidents",
        json={"title": "Second Incident"},
        headers={"Authorization": f"Bearer {token}"},
    )
    inc_b_id = inc_b_resp.json()["id"]

    # Create investigation for Incident A
    inv_resp = client.post(
        f"/api/v1/projects/{project_id}/incidents/{inc_a_id}/investigations",
        json={"summary": "Belongs to A"},
        headers={"Authorization": f"Bearer {token}"},
    )
    inv_id = inv_resp.json()["id"]

    # Query inv_id under Incident B
    resp = client.get(
        f"/api/v1/projects/{project_id}/incidents/{inc_b_id}/investigations/{inv_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_nonexistent_investigation_returns_404(client):
    """19. Nonexistent investigation ID returns 404."""
    _, token, project_id, incident_id = create_user_project_and_incident(client)

    fake_id = str(uuid.uuid4())
    resp = client.get(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/investigations/{fake_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_nonexistent_incident_returns_404(client):
    """20. Nonexistent incident ID returns 404."""
    _, token, project_id, _ = create_user_project_and_incident(client)

    fake_inc_id = str(uuid.uuid4())
    resp = client.get(
        f"/api/v1/projects/{project_id}/incidents/{fake_inc_id}/investigations",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_nonexistent_project_returns_404(client):
    """21. Nonexistent project ID returns 404."""
    token = make_test_token()
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token}"})

    fake_proj = str(uuid.uuid4())
    fake_inc = str(uuid.uuid4())
    resp = client.get(
        f"/api/v1/projects/{fake_proj}/incidents/{fake_inc}/investigations",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 4. Investigation Mutation Tests
# ---------------------------------------------------------------------------


def test_update_own_investigation_mutable_fields(client):
    """22. Updating mutable fields on own investigation succeeds."""
    _, token, project_id, incident_id = create_user_project_and_incident(client)

    inv_resp = client.post(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/investigations",
        json={"summary": "Initial summary"},
        headers={"Authorization": f"Bearer {token}"},
    )
    inv_id = inv_resp.json()["id"]

    patch_payload = {
        "summary": "Updated summary with deeper findings",
        "error_message": "Warning: transient latency observed",
    }
    resp = client.patch(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/investigations/{inv_id}",
        json=patch_payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["summary"] == patch_payload["summary"]
    assert data["error_message"] == patch_payload["error_message"]
    assert "root_cause_summary" not in data
    assert "confidence_score" not in data


def test_update_investigation_cross_user_rejected(client):
    """23. User B cannot update User A's investigation (403)."""
    _, token_a, proj_a_id, inc_a_id = create_user_project_and_incident(client)

    inv_resp = client.post(
        f"/api/v1/projects/{proj_a_id}/incidents/{inc_a_id}/investigations",
        json={"summary": "A's investigation"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    inv_id = inv_resp.json()["id"]

    token_b = make_test_token(sub=str(uuid.uuid4()))
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token_b}"})

    resp = client.patch(
        f"/api/v1/projects/{proj_a_id}/incidents/{inc_a_id}/investigations/{inv_id}",
        json={"summary": "Malicious edit"},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp.status_code == 403


def test_update_investigation_immutable_fields_rejected(client):
    """24. Attempting to update immutable fields (project_id, incident_id, id) returns 422."""
    _, token, project_id, incident_id = create_user_project_and_incident(client)

    inv_resp = client.post(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/investigations",
        json={"summary": "A investigation"},
        headers={"Authorization": f"Bearer {token}"},
    )
    inv_id = inv_resp.json()["id"]

    for forbidden_field in [
        "id", "project_id", "incident_id", "created_at", "updated_at",
        "root_cause_summary", "confidence_score"
    ]:
        val = str(uuid.uuid4()) if "id" in forbidden_field else "test_forbidden"
        resp = client.patch(
            f"/api/v1/projects/{project_id}/incidents/{incident_id}/investigations/{inv_id}",
            json={forbidden_field: val},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 5. Status Lifecycle & Finite State Machine Tests
# ---------------------------------------------------------------------------


def test_valid_status_lifecycle_pending_to_running_to_completed(client):
    """25. Lifecycle: PENDING -> RUNNING (sets started_at) -> COMPLETED (sets completed_at)."""
    _, token, project_id, incident_id = create_user_project_and_incident(client)

    create_resp = client.post(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/investigations",
        json={"summary": "Lifecycle test", "status": "pending"},
        headers={"Authorization": f"Bearer {token}"},
    )
    inv_id = create_resp.json()["id"]
    assert create_resp.json()["status"] == "pending"
    assert create_resp.json()["started_at"] is None

    # Step 1: PENDING -> RUNNING
    run_resp = client.patch(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/investigations/{inv_id}/status",
        json={"status": "running"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert run_resp.status_code == 200
    assert run_resp.json()["status"] == "running"
    assert run_resp.json()["started_at"] is not None
    assert run_resp.json()["completed_at"] is None

    # Step 2: RUNNING -> COMPLETED
    comp_resp = client.patch(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/investigations/{inv_id}/status",
        json={"status": "completed"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert comp_resp.status_code == 200
    comp_data = comp_resp.json()
    assert comp_data["status"] == "completed"
    assert comp_data["completed_at"] is not None
    assert "root_cause_summary" not in comp_data
    assert "confidence_score" not in comp_data


def test_valid_status_lifecycle_pending_to_cancelled(client):
    """26. Lifecycle: PENDING -> CANCELLED sets completed_at."""
    _, token, project_id, incident_id = create_user_project_and_incident(client)

    create_resp = client.post(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/investigations",
        json={"summary": "Cancel test", "status": "pending"},
        headers={"Authorization": f"Bearer {token}"},
    )
    inv_id = create_resp.json()["id"]

    resp = client.patch(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/investigations/{inv_id}/status",
        json={"status": "cancelled"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"
    assert resp.json()["completed_at"] is not None


def test_valid_status_lifecycle_running_to_failed(client):
    """27. Lifecycle: RUNNING -> FAILED sets completed_at and error_message."""
    _, token, project_id, incident_id = create_user_project_and_incident(client)

    create_resp = client.post(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/investigations",
        json={"summary": "Failure test", "status": "running"},
        headers={"Authorization": f"Bearer {token}"},
    )
    inv_id = create_resp.json()["id"]

    resp = client.patch(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/investigations/{inv_id}/status",
        json={"status": "failed", "error_message": "GitHub API rate limit exhausted"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "failed"
    assert resp.json()["completed_at"] is not None
    assert resp.json()["error_message"] == "GitHub API rate limit exhausted"


def test_valid_status_lifecycle_running_to_cancelled(client):
    """28. Lifecycle: RUNNING -> CANCELLED succeeds."""
    _, token, project_id, incident_id = create_user_project_and_incident(client)

    create_resp = client.post(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/investigations",
        json={"summary": "Cancel running test", "status": "running"},
        headers={"Authorization": f"Bearer {token}"},
    )
    inv_id = create_resp.json()["id"]

    resp = client.patch(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/investigations/{inv_id}/status",
        json={"status": "cancelled"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"
    assert resp.json()["completed_at"] is not None


def test_invalid_status_transitions_rejected(client):
    """29. Invalid transitions (e.g. PENDING -> COMPLETED, terminal states) are rejected with 422."""
    _, token, project_id, incident_id = create_user_project_and_incident(client)

    # 1. PENDING -> COMPLETED is forbidden (must go through RUNNING)
    inv_resp = client.post(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/investigations",
        json={"summary": "Skip test", "status": "pending"},
        headers={"Authorization": f"Bearer {token}"},
    )
    inv_id = inv_resp.json()["id"]

    skip_resp = client.patch(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/investigations/{inv_id}/status",
        json={"status": "completed"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert skip_resp.status_code == 422

    # 2. RUNNING -> COMPLETED
    client.patch(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/investigations/{inv_id}/status",
        json={"status": "running"},
        headers={"Authorization": f"Bearer {token}"},
    )
    client.patch(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/investigations/{inv_id}/status",
        json={"status": "completed"},
        headers={"Authorization": f"Bearer {token}"},
    )

    # 3. COMPLETED is terminal -> cannot transition to RUNNING or PENDING
    term_resp = client.patch(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/investigations/{inv_id}/status",
        json={"status": "running"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert term_resp.status_code == 422


def test_idempotent_status_transition_succeeds(client):
    """30. Transitioning to the current status is an idempotent no-op returning 200."""
    _, token, project_id, incident_id = create_user_project_and_incident(client)

    inv_resp = client.post(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/investigations",
        json={"summary": "Idempotent test", "status": "pending"},
        headers={"Authorization": f"Bearer {token}"},
    )
    inv_id = inv_resp.json()["id"]

    resp = client.patch(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/investigations/{inv_id}/status",
        json={"status": "pending"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "pending"


def test_status_transition_cross_user_rejected(client):
    """31. User B cannot transition status on User A's investigation (403)."""
    _, token_a, proj_a_id, inc_a_id = create_user_project_and_incident(client)

    inv_resp = client.post(
        f"/api/v1/projects/{proj_a_id}/incidents/{inc_a_id}/investigations",
        json={"summary": "A's investigation", "status": "pending"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    inv_id = inv_resp.json()["id"]

    token_b = make_test_token(sub=str(uuid.uuid4()))
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token_b}"})

    resp = client.patch(
        f"/api/v1/projects/{proj_a_id}/incidents/{inc_a_id}/investigations/{inv_id}/status",
        json={"status": "running"},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 6. Investigation Deletion Tests
# ---------------------------------------------------------------------------


def test_delete_own_investigation(client):
    """32. Delete own investigation succeeds and subsequent GET returns 404."""
    _, token, project_id, incident_id = create_user_project_and_incident(client)

    inv_resp = client.post(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/investigations",
        json={"summary": "Delete test"},
        headers={"Authorization": f"Bearer {token}"},
    )
    inv_id = inv_resp.json()["id"]

    del_resp = client.delete(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/investigations/{inv_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_resp.status_code == 200
    assert del_resp.json()["success"] is True
    assert del_resp.json()["investigation_id"] == inv_id

    # Subsequent GET returns 404
    get_resp = client.get(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/investigations/{inv_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_resp.status_code == 404


def test_cross_user_delete_rejected(client):
    """33. User B cannot delete User A's investigation (403)."""
    _, token_a, proj_a_id, inc_a_id = create_user_project_and_incident(client)

    inv_resp = client.post(
        f"/api/v1/projects/{proj_a_id}/incidents/{inc_a_id}/investigations",
        json={"summary": "A's investigation"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    inv_id = inv_resp.json()["id"]

    token_b = make_test_token(sub=str(uuid.uuid4()))
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token_b}"})

    del_resp = client.delete(
        f"/api/v1/projects/{proj_a_id}/incidents/{inc_a_id}/investigations/{inv_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert del_resp.status_code == 403


# ---------------------------------------------------------------------------
# 7. Regressions & Validation Tests
# ---------------------------------------------------------------------------


def test_invalid_enum_and_uuid_rejected(client):
    """34. Invalid status string returns 422; malformed UUID returns 422."""
    _, token, project_id, incident_id = create_user_project_and_incident(client)

    # Invalid status enum
    resp = client.post(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/investigations",
        json={"summary": "Bad enum", "status": "nonexistent_status"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422

    # Malformed investigation UUID
    resp_uuid = client.get(
        f"/api/v1/projects/{project_id}/incidents/{incident_id}/investigations/not-a-uuid",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_uuid.status_code == 422


def test_unauthenticated_all_investigation_endpoints_rejected(client):
    """35. All investigation endpoints return 401 when called unauthenticated."""
    fake_proj = str(uuid.uuid4())
    fake_inc = str(uuid.uuid4())
    fake_inv = str(uuid.uuid4())

    base = f"/api/v1/projects/{fake_proj}/incidents/{fake_inc}/investigations"

    assert client.post(base, json={"summary": "test"}).status_code == 401
    assert client.get(base).status_code == 401
    assert client.get(f"{base}/{fake_inv}").status_code == 401
    assert client.patch(f"{base}/{fake_inv}", json={"summary": "test"}).status_code == 401
    assert client.patch(f"{base}/{fake_inv}/status", json={"status": "running"}).status_code == 401
    assert client.delete(f"{base}/{fake_inv}").status_code == 401


# ---------------------------------------------------------------------------
# 8. Live PostgreSQL & Row Level Security (RLS) Integration Test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_live_pg_phase9_rls_integration():
    """36. Live PostgreSQL 16 test verifying RLS boundary on Investigation records via has_project_access."""
    import asyncpg

    conn = None
    try:
        conn = await asyncpg.connect(PG_TEST_URL, timeout=3.0)
    except Exception:
        pytest.skip("Live PostgreSQL is not accessible for Phase 9 RLS integration test.")

    user_a = str(uuid.uuid4())
    user_b = str(uuid.uuid4())
    project_id = str(uuid.uuid4())
    incident_id = str(uuid.uuid4())
    investigation_id = str(uuid.uuid4())
    email_a = f"pg_inv_a_{uuid.uuid4().hex[:8]}@devdoc.ai"
    email_b = f"pg_inv_b_{uuid.uuid4().hex[:8]}@devdoc.ai"
    slug = f"pg-inv-{uuid.uuid4().hex[:8]}"

    try:
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

        # In transaction as User A: create project, incident, and investigation
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
            await conn.execute(
                "INSERT INTO investigations (id, project_id, incident_id, initiated_by_id, status, summary, tokens_used, estimated_cost_usd, created_at, updated_at) "
                "VALUES ($1, $2, $3, $4, 'pending', 'PG Investigation A', 0, 0, now(), now())",
                uuid.UUID(investigation_id),
                uuid.UUID(project_id),
                uuid.UUID(incident_id),
                uuid.UUID(user_a),
            )
            # User A can see the investigation
            row_a = await conn.fetchrow("SELECT * FROM investigations WHERE id = $1", uuid.UUID(investigation_id))
            assert row_a is not None
            assert row_a["summary"] == "PG Investigation A"

        # In transaction as User B: cannot see User A's investigation via RLS!
        async with conn.transaction():
            await conn.execute("SET ROLE authenticated")
            await conn.execute("SELECT set_config('request.jwt.claim.sub', $1, true)", user_b)
            row_b = await conn.fetchrow("SELECT * FROM investigations WHERE id = $1", uuid.UUID(investigation_id))
            assert row_b is None, "RLS FAILURE: User B was able to see User A's investigation!"

    finally:
        if conn and not conn.is_closed():
            await conn.execute("DELETE FROM investigations WHERE id = $1", uuid.UUID(investigation_id))
            await conn.execute("DELETE FROM incidents WHERE id = $1", uuid.UUID(incident_id))
            await conn.execute("DELETE FROM projects WHERE id = $1", uuid.UUID(project_id))
            await conn.execute("DELETE FROM users WHERE id IN ($1, $2)", uuid.UUID(user_a), uuid.UUID(user_b))
            await conn.close()
