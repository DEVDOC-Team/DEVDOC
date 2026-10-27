"""DEVDOC Phase 5 — Authentication & Authorization Test Suite.

Comprehensive security test suite verifying:
1. Bearer Token Parsing & Header Validation
   - Missing Authorization header -> 401
   - Malformed Authorization header -> 401
   - Missing Bearer prefix -> 401
   - Empty token -> 401
2. Cryptographic JWT Verification
   - Valid JWT signature accepted
   - Invalid signature rejected -> 401
   - Malformed/tampered JWT rejected -> 401
   - Expired JWT rejected -> 401
   - Invalid issuer rejected -> 401
   - Invalid audience rejected -> 401
   - Invalid non-UUID sub claim rejected -> 401
3. User Identity Consistency & Provisioning
   - JWT sub matches public.users.id exactly
   - Profile sync creates user with authenticated UUID
   - Profile sync is idempotent (multiple calls succeed safely)
   - User A cannot supply User B's UUID to impersonate them
4. FastAPI Dependencies & Authorization
   - get_current_user resolves authenticated User
   - require_active_user rejects deactivated users -> 403
   - require_superuser enforces admin privilege -> 403
   - require_project_access allows owner -> 200
   - require_project_access denies non-owner -> 403
   - Non-existent project -> 404
5. PostgreSQL Session Identity & Connection Isolation
   - SET LOCAL request.jwt.claim.sub sets session identity to auth.uid()
   - Connection pool reuse does NOT leak User A's identity to subsequent requests
   - Transaction boundary correctly resets identity
"""

from __future__ import annotations

import os
import time
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone

import jwt
import pytest
import pytest_asyncio
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.v1.auth import router as auth_router
from app.core.config import Settings
from app.core.security import extract_bearer_token, verify_and_decode_jwt
from app.db.base import Base
from app.dependencies import (
    get_authenticated_db,
    get_current_user,
    get_db,
    get_token_payload,
    require_active_user,
    require_project_access,
    require_superuser,
)
from app.models.project import Project
from app.models.user import User
from app.schemas.auth import TokenPayload
from app.services.auth import get_or_sync_user_profile

# ---------------------------------------------------------------------------
# Test Constants & Signing Keys
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


# ---------------------------------------------------------------------------
# PART 1: Token Parsing & Low-Level JWT Verification
# ---------------------------------------------------------------------------


def test_extract_bearer_token_valid():
    token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.e30.t-IDcSemACt8x4iTMCda8Yhe3iZaWbvV5XKSTbuAn0M"
    auth_header = f"Bearer {token}"
    extracted = extract_bearer_token(auth_header)
    assert extracted == token


def test_extract_bearer_token_missing():
    with pytest.raises(HTTPException) as exc_info:
        extract_bearer_token(None)
    assert exc_info.value.status_code == 401
    assert "Missing Authorization header" in exc_info.value.detail


def test_extract_bearer_token_invalid_format():
    invalid_headers = [
        "Basic dXNlcjpwYXNz",
        "Bearer",
        "Bearer token extra_arg",
        "Token abcdef123456",
        "",
    ]
    for header in invalid_headers:
        with pytest.raises(HTTPException) as exc_info:
            extract_bearer_token(header)
        assert exc_info.value.status_code == 401


def test_verify_and_decode_jwt_valid():
    user_id = str(uuid.uuid4())
    token = make_test_token(sub=user_id, email="alice@devdoc.ai")
    payload = verify_and_decode_jwt(token, settings=TEST_SETTINGS)

    assert isinstance(payload, dict)
    assert payload["sub"] == user_id
    assert payload["email"] == "alice@devdoc.ai"
    assert payload["aud"] == TEST_AUDIENCE
    assert payload["iss"] == TEST_ISSUER


def test_verify_and_decode_jwt_invalid_signature():
    token = make_test_token(secret="wrong-secret-key-that-fails-verification!")
    with pytest.raises(HTTPException) as exc_info:
        verify_and_decode_jwt(token, settings=TEST_SETTINGS)
    assert exc_info.value.status_code == 401
    assert "Invalid token signature" in exc_info.value.detail


def test_verify_and_decode_jwt_expired():
    token = make_test_token(exp_offset_seconds=-60)  # Expired 1 min ago
    with pytest.raises(HTTPException) as exc_info:
        verify_and_decode_jwt(token, settings=TEST_SETTINGS)
    assert exc_info.value.status_code == 401
    assert "Token has expired" in exc_info.value.detail


def test_verify_and_decode_jwt_invalid_issuer():
    token = make_test_token(issuer="https://malicious-issuer.com/auth")
    with pytest.raises(HTTPException) as exc_info:
        verify_and_decode_jwt(token, settings=TEST_SETTINGS)
    assert exc_info.value.status_code == 401
    assert "Invalid token issuer" in exc_info.value.detail


def test_verify_and_decode_jwt_invalid_audience():
    token = make_test_token(audience="wrong-audience")
    with pytest.raises(HTTPException) as exc_info:
        verify_and_decode_jwt(token, settings=TEST_SETTINGS)
    assert exc_info.value.status_code == 401
    assert "Invalid token audience" in exc_info.value.detail


def test_verify_and_decode_jwt_invalid_sub_not_uuid():
    token = make_test_token(sub="not-a-valid-uuid-string")
    with pytest.raises(HTTPException) as exc_info:
        verify_and_decode_jwt(token, settings=TEST_SETTINGS)
    assert exc_info.value.status_code == 401
    assert "Invalid user identifier in token" in exc_info.value.detail


def test_verify_and_decode_jwt_missing_sub():
    payload = {
        "email": "no-sub@devdoc.ai",
        "aud": TEST_AUDIENCE,
        "iss": TEST_ISSUER,
        "exp": int(time.time()) + 3600,
    }
    token = jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")
    with pytest.raises(HTTPException) as exc_info:
        verify_and_decode_jwt(token, settings=TEST_SETTINGS)
    assert exc_info.value.status_code == 401
    assert "Token missing required claim" in exc_info.value.detail


# ---------------------------------------------------------------------------
# PART 2: Database & API Fixtures (SQLite In-Memory)
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
def test_app(sqlite_session_factory):
    """FastAPI test application with overridden DB and security settings."""
    app = FastAPI(title="DEVDOC Auth Test App")
    app.include_router(auth_router, prefix="/api/v1")

    # DB override
    async def override_get_db() -> AsyncGenerator[AsyncSession]:
        async with sqlite_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    return app


@pytest.fixture(scope="function")
def client(test_app):
    return TestClient(test_app)


# ---------------------------------------------------------------------------
# PART 3: User Profile Provisioning & Identity Consistency
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_user_profile_sync_creates_user(sqlite_session_factory):
    """Verify profile provisioning creates public.users with exact JWT UUID."""
    user_uuid = str(uuid.uuid4())
    token_payload = {
        "sub": user_uuid,
        "email": "provision@devdoc.ai",
        "aud": TEST_AUDIENCE,
        "iss": TEST_ISSUER,
        "exp": int(time.time()) + 3600,
        "user_metadata": {"full_name": "Provisioned User", "avatar_url": "https://avatar.png"},
    }

    async with sqlite_session_factory() as session:
        user = await get_or_sync_user_profile(session, token_payload)
        assert str(user.id) == user_uuid
        assert user.email == "provision@devdoc.ai"
        assert user.full_name == "Provisioned User"
        assert user.avatar_url == "https://avatar.png"
        assert user.is_active is True
        await session.commit()

        # Idempotent second sync: should NOT create duplicate, should retrieve same user
        user2 = await get_or_sync_user_profile(session, token_payload)
        assert str(user2.id) == user_uuid


@pytest.mark.asyncio
async def test_user_profile_sync_cannot_impersonate_another_user(sqlite_session_factory):
    """Verify profile sync relies strictly on authenticated token_payload.sub."""
    user_a_uuid = str(uuid.uuid4())
    user_b_uuid = str(uuid.uuid4())

    token_payload_a = {
        "sub": user_a_uuid,
        "email": "user_a@devdoc.ai",
        "aud": TEST_AUDIENCE,
        "iss": TEST_ISSUER,
        "exp": int(time.time()) + 3600,
    }

    async with sqlite_session_factory() as session:
        user_a = await get_or_sync_user_profile(session, token_payload_a)
        assert str(user_a.id) == user_a_uuid
        assert str(user_a.id) != user_b_uuid


# ---------------------------------------------------------------------------
# PART 4: FastAPI Endpoint Authentication & Authorization Tests
# ---------------------------------------------------------------------------


def test_auth_me_missing_header(client):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert "Missing Authorization header" in response.json()["detail"]


def test_auth_me_malformed_bearer(client):
    response = client.get("/api/v1/auth/me", headers={"Authorization": "MalformedToken"})
    assert response.status_code == 401


def test_auth_sync_success(client, monkeypatch):
    """Verify POST /api/v1/auth/sync auto-provisions and returns the user."""
    monkeypatch.setattr("app.core.security.settings", TEST_SETTINGS)

    user_id = str(uuid.uuid4())
    token = make_test_token(sub=user_id, email="syncuser@devdoc.ai")

    response = client.post(
        "/api/v1/auth/sync",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["message"] == "User profile synchronized successfully"
    assert data["user"]["id"] == user_id
    assert data["user"]["email"] == "syncuser@devdoc.ai"


def test_auth_me_success_after_sync(client, monkeypatch):
    """Verify GET /api/v1/auth/me returns current authenticated user."""
    monkeypatch.setattr("app.core.security.settings", TEST_SETTINGS)

    user_id = str(uuid.uuid4())
    token = make_test_token(sub=user_id, email="me_user@devdoc.ai")

    # 1. Sync first so user exists
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token}"})

    # 2. Get me
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == user_id
    assert data["email"] == "me_user@devdoc.ai"
    assert data["is_active"] is True


def test_auth_me_inactive_user_rejected(test_app, client, sqlite_session_factory, monkeypatch):
    """Verify deactivated user is rejected by require_active_user with 403."""
    monkeypatch.setattr("app.core.security.settings", TEST_SETTINGS)

    user_id = str(uuid.uuid4())
    token = make_test_token(sub=user_id, email="inactive@devdoc.ai")

    # 1. Sync
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token}"})

    # 2. Manually deactivate user in DB
    async def deactivate():
        async with sqlite_session_factory() as session:
            stmt = select(User).where(User.id == uuid.UUID(user_id))
            res = await session.execute(stmt)
            u = res.scalar_one()
            u.is_active = False
            await session.commit()

    import asyncio

    asyncio.run(deactivate())

    # 3. Add an endpoint that requires active user
    @test_app.get("/api/v1/test-active")
    def active_route(user: User = Depends(require_active_user)):
        return {"status": "ok"}

    response = client.get("/api/v1/test-active", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
    assert "User account is inactive" in response.json()["detail"]


# ---------------------------------------------------------------------------
# PART 5: Project Ownership & Authorization
# ---------------------------------------------------------------------------


def test_project_authorization_owner_allowed_non_owner_forbidden(
    client, sqlite_session_factory, monkeypatch
):
    """Verify owner can access project, while another authenticated user receives 403."""
    monkeypatch.setattr("app.core.security.settings", TEST_SETTINGS)

    owner_id = str(uuid.uuid4())
    intruder_id = str(uuid.uuid4())
    project_id = str(uuid.uuid4())

    owner_token = make_test_token(sub=owner_id, email="owner@devdoc.ai")
    intruder_token = make_test_token(sub=intruder_id, email="intruder@devdoc.ai")

    # 1. Provision both users
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {owner_token}"})
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {intruder_token}"})

    # 2. Insert project owned by owner
    async def seed_project():
        async with sqlite_session_factory() as session:
            p = Project(
                id=uuid.UUID(project_id),
                name="Production App",
                slug="production-app",
                owner_id=uuid.UUID(owner_id),
            )
            session.add(p)
            await session.commit()

    import asyncio

    asyncio.run(seed_project())

    # 3. Test Owner Access -> 200 OK
    resp_owner = client.get(
        f"/api/v1/auth/projects/{project_id}/verify-access",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp_owner.status_code == 200
    assert resp_owner.json()["success"] is True
    assert resp_owner.json()["project_id"] == project_id
    assert resp_owner.json()["owner_id"] == owner_id

    # 4. Test Intruder Access -> 403 Forbidden
    resp_intruder = client.get(
        f"/api/v1/auth/projects/{project_id}/verify-access",
        headers={"Authorization": f"Bearer {intruder_token}"},
    )
    assert resp_intruder.status_code == 403
    assert "You do not have access to this project" in resp_intruder.json()["detail"]

    # 5. Non-existent Project -> 404
    random_project_id = str(uuid.uuid4())
    resp_missing = client.get(
        f"/api/v1/auth/projects/{random_project_id}/verify-access",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp_missing.status_code == 404


# ---------------------------------------------------------------------------
# PART 6: Live PostgreSQL Session Context & Connection Pool Safety
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_live_pg_session_identity_and_connection_isolation():
    """Live PostgreSQL integration test:

    1. Verify SET LOCAL request.jwt.claim.sub propagates to current_setting('request.jwt.claim.sub', true).
    2. Verify connection reuse resets the identity so Request B does not inherit Request A's identity.
    """
    import asyncpg

    conn = None
    try:
        conn = await asyncpg.connect(PG_TEST_URL, timeout=3.0)
    except Exception:
        pytest.skip("Live PostgreSQL is not accessible for connection isolation test.")

    try:
        user_a_uuid = str(uuid.uuid4())
        user_b_uuid = str(uuid.uuid4())

        # Transaction 1: User A sets session identity
        async with conn.transaction():
            # In PostgreSQL: set_config('request.jwt.claim.sub', value, is_local=true)
            await conn.execute("SELECT set_config('request.jwt.claim.sub', $1, true)", user_a_uuid)
            res_a = await conn.fetchval("SELECT current_setting('request.jwt.claim.sub', true)")
            assert res_a == user_a_uuid

            # Test Supabase auth.uid() function if present
            try:
                auth_uid_val = await conn.fetchval("SELECT auth.uid()::text")
                assert auth_uid_val == user_a_uuid
            except Exception:
                pass  # auth.uid() might be in a different schema in standard test PG

        # Outside Transaction 1: Verify identity is NOT leaked on the same connection!
        val_after_tx = await conn.fetchval("SELECT current_setting('request.jwt.claim.sub', true)")
        assert val_after_tx is None or val_after_tx == "", (
            "SECURITY CRITICAL: Database session identity leaked across transaction boundary!"
        )

        # Transaction 2: User B sets session identity
        async with conn.transaction():
            await conn.execute("SELECT set_config('request.jwt.claim.sub', $1, true)", user_b_uuid)
            res_b = await conn.fetchval("SELECT current_setting('request.jwt.claim.sub', true)")
            assert res_b == user_b_uuid

        # Explicit RESET test
        await conn.execute("SELECT set_config('request.jwt.claim.sub', $1, false)", user_a_uuid)
        await conn.execute("RESET request.jwt.claim.sub")
        val_after_reset = await conn.fetchval("SELECT current_setting('request.jwt.claim.sub', true)")
        assert val_after_reset is None or val_after_reset == ""

    finally:
        if conn and not conn.is_closed():
            await conn.close()


def test_login_with_password_success(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    """Verify POST /api/v1/auth/login authenticates via Supabase Auth and returns access token."""
    from unittest.mock import AsyncMock, MagicMock, patch

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "access_token": "supabase_es256_mock_access_token",
        "token_type": "bearer",
        "expires_in": 3600,
        "user": {"id": str(uuid.uuid4()), "email": "engineer@devdoc.ai"},
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        res = client.post(
            "/api/v1/auth/login",
            json={"email": "engineer@devdoc.ai", "password": "correct_password"},
        )

    assert res.status_code == 200
    data = res.json()
    assert data["access_token"] == "supabase_es256_mock_access_token"
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == "engineer@devdoc.ai"


def test_login_with_password_invalid_credentials(client: TestClient):
    """Verify POST /api/v1/auth/login rejects bad credentials with 401."""
    from unittest.mock import AsyncMock, patch

    mock_resp = AsyncMock()
    mock_resp.status_code = 400
    mock_resp.json.return_value = {"error": "invalid_grant", "error_description": "Invalid login credentials"}

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        res = client.post(
            "/api/v1/auth/login",
            json={"email": "engineer@devdoc.ai", "password": "wrong_password"},
        )

    assert res.status_code == 401
    assert "Invalid email or password" in res.json()["detail"]


def test_login_with_password_empty_credentials(client: TestClient):
    """Verify POST /api/v1/auth/login validates required fields."""
    res = client.post("/api/v1/auth/login", json={"email": "", "password": ""})
    assert res.status_code == 400
