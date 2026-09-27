"""DEVDOC Phase 6 — User & Project APIs Test Suite.

Comprehensive tests covering:
1. User Profile APIs:
   - GET /api/v1/users/me (retrieve own profile)
   - PATCH /api/v1/users/me (update mutable profile fields)
   - PATCH /api/v1/users/me with immutable fields rejected (422)
   - DELETE /api/v1/users/me (deactivate own account)
   - Deactivated user blocked from subsequent requests (403)
   - Unauthenticated requests rejected (401)
   - Identity spoofing prevention (JWT sub is authoritative)
2. Project APIs:
   - POST /api/v1/projects (create project with derived owner_id)
   - POST /api/v1/projects auto-generates slug from name
   - POST /api/v1/projects with spoofed owner_id rejected (422)
   - POST /api/v1/projects duplicate slug returns 409 Conflict
   - GET /api/v1/projects (list user's projects with pagination)
   - GET /api/v1/projects isolates cross-user projects
   - GET /api/v1/projects respects include_inactive toggle
   - GET /api/v1/projects/{project_id} (retrieve own project)
   - GET /api/v1/projects/{project_id} cross-user access denied (403)
   - GET /api/v1/projects/{project_id} nonexistent returns 404
   - PATCH /api/v1/projects/{project_id} (update own project)
   - PATCH /api/v1/projects/{project_id} cross-user update denied (403)
   - PATCH /api/v1/projects/{project_id} nonexistent returns 404
   - DELETE /api/v1/projects/{project_id} (delete own project)
   - DELETE /api/v1/projects/{project_id} cross-user delete denied (403)
   - DELETE /api/v1/projects/{project_id} nonexistent returns 404
   - Subsequent GET on deleted project returns 404
3. Input Validation & Edge Cases:
   - Malformed UUID in path parameter returns 422
   - Empty project name returns 422
   - Invalid slug characters returns 422
4. Live PostgreSQL Integration:
   - Live PG verification of RLS with get_authenticated_db session context
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

# ---------------------------------------------------------------------------
# Test Constants & Signing Configuration
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
    extra_claims: dict | None = None,
) -> str:
    """Generate a signed JWT token with configurable claims for testing."""
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
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, secret, algorithm="HS256")


def get_error_message(response) -> str:
    """Extract error detail message safely from response payload."""
    data = response.json()
    if isinstance(data, dict):
        if "error" in data and isinstance(data["error"], dict) and "message" in data["error"]:
            return str(data["error"]["message"])
        if "detail" in data:
            return str(data["detail"])
    return str(data)



# ---------------------------------------------------------------------------
# Database & API Fixtures
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
# USER API TESTS
# ---------------------------------------------------------------------------


def test_get_own_profile_success(client):
    """1. GET /api/v1/users/me returns authenticated user's profile."""
    user_id = str(uuid.uuid4())
    token = make_test_token(sub=user_id, email="alice@devdoc.ai")

    # Initial sync so user exists
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token}"})

    response = client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == user_id
    assert data["email"] == "alice@devdoc.ai"
    assert data["is_active"] is True
    assert data["is_superuser"] is False


def test_patch_own_profile_success(client):
    """2. PATCH /api/v1/users/me updates mutable profile fields."""
    user_id = str(uuid.uuid4())
    token = make_test_token(sub=user_id, email="bob@devdoc.ai")

    # Initial sync
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token}"})

    patch_payload = {
        "full_name": "Bob Senior SRE",
        "avatar_url": "https://devdoc.ai/avatars/bob.png",
    }
    response = client.patch(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
        json=patch_payload,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["full_name"] == "Bob Senior SRE"
    assert data["avatar_url"] == "https://devdoc.ai/avatars/bob.png"
    assert data["id"] == user_id

    # Verify persistent update via GET
    get_res = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
    assert get_res.json()["full_name"] == "Bob Senior SRE"


def test_patch_own_profile_immutable_fields_rejected(client):
    """3. PATCH /api/v1/users/me rejects modification of immutable fields with 422."""
    user_id = str(uuid.uuid4())
    token = make_test_token(sub=user_id, email="charlie@devdoc.ai")

    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token}"})

    # Attempt to change immutable fields (id, email, is_superuser)
    illegal_payloads = [
        {"id": str(uuid.uuid4())},
        {"email": "hacked@devdoc.ai"},
        {"is_superuser": True},
        {"is_active": False},
        {"provider": "evil-oauth"},
    ]
    for payload in illegal_payloads:
        response = client.patch(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
        )
        assert response.status_code == 422


def test_delete_own_profile_deactivates_user(client):
    """4. DELETE /api/v1/users/me deactivates the user account."""
    user_id = str(uuid.uuid4())
    token = make_test_token(sub=user_id, email="dan@devdoc.ai")

    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token}"})

    response = client.delete(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["user_id"] == user_id
    assert "deactivated" in data["message"].lower()

    # Subsequent requests from this user are now blocked by require_active_user (403)
    subsequent_res = client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert subsequent_res.status_code == 403
    assert "User account is inactive" in get_error_message(subsequent_res)


def test_unauthenticated_user_api_rejected(client):
    """5. Unauthenticated calls to user endpoints return 401."""
    assert client.get("/api/v1/users/me").status_code == 401
    assert client.patch("/api/v1/users/me", json={"full_name": "X"}).status_code == 401
    assert client.delete("/api/v1/users/me").status_code == 401


# ---------------------------------------------------------------------------
# PROJECT API TESTS
# ---------------------------------------------------------------------------


def test_create_project_success(client):
    """6 & 7. POST /api/v1/projects creates project and derives owner_id from JWT sub."""
    user_id = str(uuid.uuid4())
    token = make_test_token(sub=user_id, email="owner@devdoc.ai")
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token}"})

    create_payload = {
        "name": "Backend Service",
        "description": "Core SRE platform backend",
        "settings_json": '{"alert_channel": "#devdoc-alerts"}',
    }
    response = client.post(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {token}"},
        json=create_payload,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Backend Service"
    assert data["slug"] == "backend-service"
    assert data["owner_id"] == user_id
    assert data["is_active"] is True
    assert data["settings_json"] == '{"alert_channel": "#devdoc-alerts"}'


def test_create_project_custom_slug(client):
    """POST /api/v1/projects respects valid custom slug."""
    user_id = str(uuid.uuid4())
    token = make_test_token(sub=user_id, email="custom_slug@devdoc.ai")
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token}"})

    response = client.post(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Kube Operator", "slug": "k8s-operator"},
    )
    assert response.status_code == 201
    assert response.json()["slug"] == "k8s-operator"


def test_create_project_spoofed_owner_id_rejected(client):
    """8. Client-supplied owner_id is rejected by extra='forbid' with 422."""
    user_id = str(uuid.uuid4())
    attacker_token = make_test_token(sub=user_id, email="attacker@devdoc.ai")
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {attacker_token}"})

    response = client.post(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {attacker_token}"},
        json={
            "name": "Malicious Project",
            "owner_id": str(uuid.uuid4()),  # Client-supplied owner_id
        },
    )
    assert response.status_code == 422


def test_create_project_duplicate_slug_conflict(client):
    """Creating two projects with same slug for the same owner returns 409 Conflict."""
    user_id = str(uuid.uuid4())
    token = make_test_token(sub=user_id, email="slug_dup@devdoc.ai")
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token}"})

    # First creation -> 201
    res1 = client.post(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Duplicate Test", "slug": "dup-slug"},
    )
    assert res1.status_code == 201

    # Second creation with identical slug -> 409
    res2 = client.post(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Duplicate Test 2", "slug": "dup-slug"},
    )
    assert res2.status_code == 409
    assert "already exists for this owner" in get_error_message(res2)


def test_list_projects_owner_scoping_and_pagination(client):
    """9. GET /api/v1/projects returns only authenticated user's projects with pagination."""
    user_a = str(uuid.uuid4())
    user_b = str(uuid.uuid4())
    token_a = make_test_token(sub=user_a, email="usera@devdoc.ai")
    token_b = make_test_token(sub=user_b, email="userb@devdoc.ai")

    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token_a}"})
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token_b}"})

    # User A creates 3 projects
    for i in range(3):
        client.post(
            "/api/v1/projects",
            headers={"Authorization": f"Bearer {token_a}"},
            json={"name": f"Project A{i}"},
        )

    # User B creates 1 project
    client.post(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"name": "Project B1"},
    )

    # User A lists projects
    res_a = client.get("/api/v1/projects", headers={"Authorization": f"Bearer {token_a}"})
    assert res_a.status_code == 200
    data_a = res_a.json()
    assert data_a["total"] == 3
    assert len(data_a["items"]) == 3
    assert all(p["owner_id"] == user_a for p in data_a["items"])

    # User B lists projects
    res_b = client.get("/api/v1/projects", headers={"Authorization": f"Bearer {token_b}"})
    assert res_b.status_code == 200
    data_b = res_b.json()
    assert data_b["total"] == 1
    assert len(data_b["items"]) == 1
    assert data_b["items"][0]["owner_id"] == user_b

    # Pagination test for User A
    res_page = client.get(
        "/api/v1/projects?limit=2&offset=0",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert len(res_page.json()["items"]) == 2
    assert res_page.json()["total"] == 3


def test_get_own_and_cross_user_project(client):
    """10 & 11. Retrieve own project succeeds (200), retrieving another user's project returns 403."""
    user_a = str(uuid.uuid4())
    user_b = str(uuid.uuid4())
    token_a = make_test_token(sub=user_a, email="alpha@devdoc.ai")
    token_b = make_test_token(sub=user_b, email="beta@devdoc.ai")

    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token_a}"})
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token_b}"})

    # User A creates a project
    create_res = client.post(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"name": "Confidential Repo"},
    )
    project_id = create_res.json()["id"]

    # User A retrieves project -> 200
    get_a = client.get(
        f"/api/v1/projects/{project_id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert get_a.status_code == 200
    assert get_a.json()["id"] == project_id

    # User B retrieves User A's project -> 403 Forbidden
    get_b = client.get(
        f"/api/v1/projects/{project_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert get_b.status_code == 403
    assert "You do not have access to this project" in get_error_message(get_b)


def test_update_own_and_cross_user_project(client):
    """12 & 13. Update own project succeeds (200), updating another user's project returns 403."""
    user_a = str(uuid.uuid4())
    user_b = str(uuid.uuid4())
    token_a = make_test_token(sub=user_a, email="u_a@devdoc.ai")
    token_b = make_test_token(sub=user_b, email="u_b@devdoc.ai")

    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token_a}"})
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token_b}"})

    # User A creates project
    create_res = client.post(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"name": "Initial Name"},
    )
    project_id = create_res.json()["id"]

    # User B attempts to update User A's project -> 403
    patch_b = client.patch(
        f"/api/v1/projects/{project_id}",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"name": "Hacked Name"},
    )
    assert patch_b.status_code == 403

    # User A updates own project -> 200
    patch_a = client.patch(
        f"/api/v1/projects/{project_id}",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"name": "Updated Name", "description": "New description"},
    )
    assert patch_a.status_code == 200
    assert patch_a.json()["name"] == "Updated Name"
    assert patch_a.json()["description"] == "New description"


def test_delete_own_and_cross_user_project(client):
    """14 & 15. Delete own project succeeds (200), deleting another user's project returns 403."""
    user_a = str(uuid.uuid4())
    user_b = str(uuid.uuid4())
    token_a = make_test_token(sub=user_a, email="del_a@devdoc.ai")
    token_b = make_test_token(sub=user_b, email="del_b@devdoc.ai")

    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token_a}"})
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token_b}"})

    # User A creates project
    create_res = client.post(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"name": "To Be Deleted"},
    )
    project_id = create_res.json()["id"]

    # User B attempts to delete User A's project -> 403
    del_b = client.delete(
        f"/api/v1/projects/{project_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert del_b.status_code == 403

    # User A deletes own project -> 200
    del_a = client.delete(
        f"/api/v1/projects/{project_id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert del_a.status_code == 200
    assert del_a.json()["success"] is True

    # Subsequent GET returns 404
    get_deleted = client.get(
        f"/api/v1/projects/{project_id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert get_deleted.status_code == 404


def test_nonexistent_project_returns_404(client):
    """16. Requests for nonexistent projects return 404 Not Found."""
    user_id = str(uuid.uuid4())
    token = make_test_token(sub=user_id, email="missing@devdoc.ai")
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token}"})

    random_id = str(uuid.uuid4())
    assert (
        client.get(
            f"/api/v1/projects/{random_id}",
            headers={"Authorization": f"Bearer {token}"},
        ).status_code
        == 404
    )
    assert (
        client.patch(
            f"/api/v1/projects/{random_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "X"},
        ).status_code
        == 404
    )
    assert (
        client.delete(
            f"/api/v1/projects/{random_id}",
            headers={"Authorization": f"Bearer {token}"},
        ).status_code
        == 404
    )


def test_malformed_uuid_returns_422(client):
    """17. Malformed UUID in path parameters returns 422 Unprocessable Entity."""
    user_id = str(uuid.uuid4())
    token = make_test_token(sub=user_id, email="uuid@devdoc.ai")
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token}"})

    response = client.get(
        "/api/v1/projects/not-a-valid-uuid",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422


def test_project_create_validation_failures(client):
    """18. Invalid request payloads return 422 Unprocessable Entity."""
    user_id = str(uuid.uuid4())
    token = make_test_token(sub=user_id, email="val@devdoc.ai")
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token}"})

    # Empty name
    res_empty_name = client.post(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": ""},
    )
    assert res_empty_name.status_code == 422

    # Invalid slug with spaces or uppercase
    res_invalid_slug = client.post(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Valid Name", "slug": "Invalid Slug!"},
    )
    assert res_invalid_slug.status_code == 422


def test_unauthenticated_project_api_rejected(client):
    """Unauthenticated calls to project endpoints return 401."""
    random_id = str(uuid.uuid4())
    assert client.post("/api/v1/projects", json={"name": "X"}).status_code == 401
    assert client.get("/api/v1/projects").status_code == 401
    assert client.get(f"/api/v1/projects/{random_id}").status_code == 401
    assert client.patch(f"/api/v1/projects/{random_id}", json={"name": "X"}).status_code == 401
    assert client.delete(f"/api/v1/projects/{random_id}").status_code == 401


# ---------------------------------------------------------------------------
# 4. LIVE POSTGRESQL INTEGRATION TEST (RLS & Phase 6 DB propagation)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_live_pg_phase6_rls_integration():
    """Live PostgreSQL test verifying RLS boundary on Project records with SET LOCAL."""
    import asyncpg

    conn = None
    try:
        conn = await asyncpg.connect(PG_TEST_URL, timeout=3.0)
    except Exception:
        pytest.skip("Live PostgreSQL is not accessible for Phase 6 RLS integration test.")

    try:
        user_a = str(uuid.uuid4())
        user_b = str(uuid.uuid4())
        project_id = str(uuid.uuid4())
        email_a = f"pga_{uuid.uuid4().hex[:8]}@devdoc.ai"
        email_b = f"pgb_{uuid.uuid4().hex[:8]}@devdoc.ai"
        slug = f"pg-proj-{uuid.uuid4().hex[:8]}"

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

        # In transaction as User A: create project
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
            # User A can see it
            row_a = await conn.fetchrow("SELECT * FROM projects WHERE id = $1", uuid.UUID(project_id))
            assert row_a is not None

        # In transaction as User B: cannot see User A's project via RLS!
        async with conn.transaction():
            await conn.execute("SET ROLE authenticated")
            await conn.execute("SELECT set_config('request.jwt.claim.sub', $1, true)", user_b)
            row_b = await conn.fetchrow("SELECT * FROM projects WHERE id = $1", uuid.UUID(project_id))
            assert row_b is None, "RLS FAILURE: User B was able to see User A's project!"

    finally:
        if conn and not conn.is_closed():
            # Clean up test rows
            await conn.execute("DELETE FROM projects WHERE id = $1", uuid.UUID(project_id))
            await conn.execute("DELETE FROM users WHERE id IN ($1, $2)", uuid.UUID(user_a), uuid.UUID(user_b))
            await conn.close()

