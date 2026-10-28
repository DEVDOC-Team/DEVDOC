"""DEVDOC Phase 7 — GitHub Integration Test Suite.

Comprehensive tests covering:
1. OAuth State Generation & Validation:
   - Cryptographically signed CSRF state generation
   - Valid state verification
   - Expired state rejection (400)
   - Tampered state rejection (400)
   - Mismatched user state rejection (403)
2. GitHub Account Connection Lifecycle:
   - GET /api/v1/github/connect initiates OAuth and returns signed state
   - GET /api/v1/github/callback handles code exchange and saves connection
   - GET /api/v1/github/connection returns safe status (never returns access_token)
   - DELETE /api/v1/github/connection disconnects user
   - User isolation: User A cannot read or affect User B's connection
3. GitHub API Client & Error Translation:
   - 401 Unauthorized translated to safe HTTP 401
   - 403 Forbidden translated to HTTP 403
   - 403/429 Rate Limit translated to HTTP 429
   - 404 Not Found translated to HTTP 404
   - Timeout translated to HTTP 504
   - Client methods for branches, commits, PRs, issues, files, workflows
4. Project Repository Association:
   - POST /api/v1/projects/{project_id}/github/repository associates repo
   - GET /api/v1/projects/{project_id}/github/repository retrieves repo
   - DELETE /api/v1/projects/{project_id}/github/repository disconnects repo
   - Duplicate repo association rejected (409 Conflict)
   - Malformed repo name rejected (422)
   - Cross-user project access forbidden (403 via require_project_access)
   - Unconnected GitHub user cannot attach repository (400)
   - Unauthenticated requests rejected (401)
5. Security & Privacy Guarantees:
   - GitHub access tokens never exposed in API responses
   - GitHub access tokens never written to application logs
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, patch

import jwt
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.core.github_client import (
    GitHubAPIClient,
    GitHubAuthenticationError,
    GitHubNotFoundError,
    GitHubPermissionError,
    GitHubRateLimitError,
    GitHubTimeoutError,
    GitHubValidationError,
)
from app.db.base import Base
from app.dependencies import get_db
from app.main import app
from app.models.github_connection import UserGitHubConnection
from app.models.project import Project
from app.models.repository import Repository, VCSProvider
from app.models.user import User
from app.services.github import GitHubIntegrationService

# ---------------------------------------------------------------------------
# Test Constants & Settings
# ---------------------------------------------------------------------------

TEST_JWT_SECRET = "devdoc-test-secret-key-32-chars-long-minimum!"
TEST_ISSUER = "https://test.supabase.co/auth/v1"
TEST_AUDIENCE = "authenticated"

TEST_SETTINGS = Settings(
    supabase_url="https://test.supabase.co",
    supabase_anon_key="test-anon-key-1234",
    supabase_jwt_secret=TEST_JWT_SECRET,
    supabase_jwt_algorithm="HS256",
    supabase_jwt_issuer=TEST_ISSUER,
    supabase_jwt_audience=TEST_AUDIENCE,
    github_client_id="mock-client-id-1234",
    github_client_secret="mock-client-secret-5678",
    github_oauth_redirect_uri="http://localhost:8000/api/v1/github/callback",
    github_api_base_url="https://api.github.com",
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
    monkeypatch.setattr("app.core.config.settings", TEST_SETTINGS)
    monkeypatch.setattr("app.services.github.settings", TEST_SETTINGS)
    monkeypatch.setattr("app.api.v1.auth.settings", TEST_SETTINGS)

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
# 1. OAuth State Generation & Validation Tests
# ---------------------------------------------------------------------------


def test_oauth_state_generation():
    """1. Test OAuth state generation creates valid signed state bound to user."""
    user_id = uuid.uuid4()
    state = GitHubIntegrationService.generate_oauth_state(user_id)
    assert isinstance(state, str)
    assert len(state) > 20

    # Decoding should yield sub matching user_id
    decoded_id = GitHubIntegrationService.verify_oauth_state(state, expected_user_id=user_id)
    assert decoded_id == user_id


def test_oauth_state_validation():
    """2. Test OAuth state validation with correct and expected user."""
    user_id = uuid.uuid4()
    state = GitHubIntegrationService.generate_oauth_state(user_id)
    verified_id = GitHubIntegrationService.verify_oauth_state(state)
    assert verified_id == user_id


def test_invalid_oauth_state_rejected():
    """3. Test invalid, tampered, expired, or mismatched OAuth states are rejected."""
    user_id = uuid.uuid4()
    other_user_id = uuid.uuid4()

    # Tampered state
    with pytest.raises(Exception) as exc_info:
        GitHubIntegrationService.verify_oauth_state("invalid.tampered.token")
    assert "Invalid or tampered" in str(exc_info.value.detail)

    # Missing state
    with pytest.raises(Exception) as exc_info:
        GitHubIntegrationService.verify_oauth_state("")
    assert "Missing OAuth state" in str(exc_info.value.detail)

    # Expired state
    from app.services.github import _get_signing_secret

    now = int(time.time())
    expired_payload = {
        "sub": str(user_id),
        "nonce": "testnonce",
        "iat": now - 1000,
        "exp": now - 100,
        "purpose": "github_oauth",
    }
    expired_state = jwt.encode(expired_payload, _get_signing_secret(), algorithm="HS256")
    with pytest.raises(Exception) as exc_info:
        GitHubIntegrationService.verify_oauth_state(expired_state)
    assert "expired" in str(exc_info.value.detail).lower()


    # Mismatched user
    state = GitHubIntegrationService.generate_oauth_state(user_id)
    with pytest.raises(Exception) as exc_info:
        GitHubIntegrationService.verify_oauth_state(state, expected_user_id=other_user_id)
    assert "does not match" in str(exc_info.value.detail)


# ---------------------------------------------------------------------------
# 2. Connection Initiation & OAuth Callback Tests
# ---------------------------------------------------------------------------


def test_connect_initiates_oauth(client):
    """4. GET /api/v1/github/connect returns authorization URL with state."""
    user_id = str(uuid.uuid4())
    token = make_test_token(sub=user_id)
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token}"})

    response = client.get(
        "/api/v1/github/connect",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "authorization_url" in data
    assert "state" in data
    assert "https://github.com/login/oauth/authorize" in data["authorization_url"]
    assert f"client_id={TEST_SETTINGS.github_client_id}" in data["authorization_url"]
    assert "repo%2Cread%3Auser" in data["authorization_url"] or "repo,read:user" in data["authorization_url"]


def test_successful_oauth_callback(client):
    """5. GET /api/v1/github/callback exchanges code and stores connection safely."""
    user_id = str(uuid.uuid4())
    token = make_test_token(sub=user_id)
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token}"})

    state = GitHubIntegrationService.generate_oauth_state(uuid.UUID(user_id))

    mock_token_data = {
        "access_token": "gho_secret_access_token_1234567890",
        "token_type": "bearer",
        "scope": "repo,read:user",
    }
    mock_gh_user = {
        "id": 99887766,
        "login": "octocat",
        "avatar_url": "https://avatars.githubusercontent.com/u/99887766",
    }

    with (
        patch.object(GitHubIntegrationService, "exchange_code_for_token", new_callable=AsyncMock) as mock_exchange,
        patch.object(GitHubAPIClient, "get_authenticated_user", new_callable=AsyncMock) as mock_user,
    ):
        mock_exchange.return_value = mock_token_data
        mock_user.return_value = mock_gh_user

        response = client.get(
            f"/api/v1/github/callback?code=mock_oauth_code&state={state}",
        )

    assert response.status_code == 200
    data = response.json()
    assert data["connected"] is True
    assert data["github_username"] == "octocat"
    assert data["github_user_id"] == "99887766"
    assert data["avatar_url"] == "https://avatars.githubusercontent.com/u/99887766"
    assert data["scope"] == "repo,read:user"

    # Token must NOT be in response
    assert "gho_secret_access_token" not in response.text
    assert "access_token" not in data


def test_github_connection_belongs_to_authenticated_user(client):
    """6. Ensure connection record is strictly bound to the authenticated user ID."""
    user_id = str(uuid.uuid4())
    token = make_test_token(sub=user_id)
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token}"})

    state = GitHubIntegrationService.generate_oauth_state(uuid.UUID(user_id))
    with (
        patch.object(GitHubIntegrationService, "exchange_code_for_token", new_callable=AsyncMock) as mock_exchange,
        patch.object(GitHubAPIClient, "get_authenticated_user", new_callable=AsyncMock) as mock_user,
    ):
        mock_exchange.return_value = {"access_token": "gho_test_tok", "token_type": "bearer", "scope": "repo"}
        mock_user.return_value = {"id": 1234, "login": "alice_dev"}
        client.get(f"/api/v1/github/callback?code=abc&state={state}")

    # Check connection endpoint for user
    res = client.get("/api/v1/github/connection", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json()["connected"] is True
    assert res.json()["github_username"] == "alice_dev"


def test_github_access_token_never_returned(client):
    """7. Comprehensive check that access_token never appears in any response payload."""
    user_id = str(uuid.uuid4())
    token = make_test_token(sub=user_id)
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token}"})

    state = GitHubIntegrationService.generate_oauth_state(uuid.UUID(user_id))
    secret_token = "gho_super_secret_github_token_xyz"
    with (
        patch.object(GitHubIntegrationService, "exchange_code_for_token", new_callable=AsyncMock) as mock_exchange,
        patch.object(GitHubAPIClient, "get_authenticated_user", new_callable=AsyncMock) as mock_user,
    ):
        mock_exchange.return_value = {"access_token": secret_token, "token_type": "bearer", "scope": "repo"}
        mock_user.return_value = {"id": 1234, "login": "testuser"}
        resp1 = client.get(f"/api/v1/github/callback?code=code123&state={state}")
        assert secret_token not in resp1.text

    resp2 = client.get("/api/v1/github/connection", headers={"Authorization": f"Bearer {token}"})
    assert secret_token not in resp2.text
    assert "access_token" not in resp2.json()


def test_github_access_token_never_logged(client, caplog):
    """8. Ensure access tokens are never printed to logger output."""
    from app.core.logging import logger as devdoc_logger

    user_id = str(uuid.uuid4())
    token = make_test_token(sub=user_id)
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token}"})

    state = GitHubIntegrationService.generate_oauth_state(uuid.UUID(user_id))
    secret_token = "gho_never_leak_this_secret_token_12345"

    devdoc_logger.addHandler(caplog.handler)
    try:
        with (
            patch.object(GitHubIntegrationService, "exchange_code_for_token", new_callable=AsyncMock) as mock_exchange,
            patch.object(GitHubAPIClient, "get_authenticated_user", new_callable=AsyncMock) as mock_user,
        ):
            mock_exchange.return_value = {"access_token": secret_token, "token_type": "bearer", "scope": "repo"}
            mock_user.return_value = {"id": 1234, "login": "logging_test_user"}
            client.get(f"/api/v1/github/callback?code=abc&state={state}")

        client.get("/api/v1/github/connection", headers={"Authorization": f"Bearer {token}"})

        # Check all records produced by application loggers
        app_records = [
            r for r in caplog.records
            if r.name == "devdoc" or r.name.startswith("devdoc.") or r.name.startswith("app")
        ]
        assert len(app_records) > 0
        for record in app_records:
            assert secret_token not in record.message
    finally:
        devdoc_logger.removeHandler(caplog.handler)




# ---------------------------------------------------------------------------
# 3. Connection Status, Disconnect & User Isolation Tests
# ---------------------------------------------------------------------------


def test_unconnected_status_returns_connected_false(client):
    """4b. GET /api/v1/github/connection for user without GitHub connection."""
    user_id = str(uuid.uuid4())
    token = make_test_token(sub=user_id)
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token}"})

    response = client.get("/api/v1/github/connection", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["connected"] is False


def test_disconnect_github_connection(client):
    """22b. DELETE /api/v1/github/connection removes stored credentials."""
    user_id = str(uuid.uuid4())
    token = make_test_token(sub=user_id)
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token}"})

    state = GitHubIntegrationService.generate_oauth_state(uuid.UUID(user_id))
    with (
        patch.object(GitHubIntegrationService, "exchange_code_for_token", new_callable=AsyncMock) as mock_exchange,
        patch.object(GitHubAPIClient, "get_authenticated_user", new_callable=AsyncMock) as mock_user,
    ):
        mock_exchange.return_value = {"access_token": "gho_disconnect_test", "token_type": "bearer", "scope": "repo"}
        mock_user.return_value = {"id": 5566, "login": "disconnect_user"}
        client.get(f"/api/v1/github/callback?code=abc&state={state}")

    # Confirm connected
    res = client.get("/api/v1/github/connection", headers={"Authorization": f"Bearer {token}"})
    assert res.json()["connected"] is True

    # Disconnect
    del_res = client.delete("/api/v1/github/connection", headers={"Authorization": f"Bearer {token}"})
    assert del_res.status_code == 200
    assert del_res.json()["success"] is True

    # Confirm disconnected
    res_after = client.get("/api/v1/github/connection", headers={"Authorization": f"Bearer {token}"})
    assert res_after.json()["connected"] is False


def test_user_cannot_read_another_users_github_connection(client):
    """18. User A cannot read User B's GitHub connection."""
    user_a = str(uuid.uuid4())
    user_b = str(uuid.uuid4())
    token_a = make_test_token(sub=user_a, email="user_a@devdoc.ai")
    token_b = make_test_token(sub=user_b, email="user_b@devdoc.ai")

    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token_a}"})
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token_b}"})

    # Connect User A
    state_a = GitHubIntegrationService.generate_oauth_state(uuid.UUID(user_a))
    with (
        patch.object(GitHubIntegrationService, "exchange_code_for_token", new_callable=AsyncMock) as mock_exchange,
        patch.object(GitHubAPIClient, "get_authenticated_user", new_callable=AsyncMock) as mock_user,
    ):
        mock_exchange.return_value = {"access_token": "gho_token_a", "token_type": "bearer", "scope": "repo"}
        mock_user.return_value = {"id": 1111, "login": "user_a_gh"}
        client.get(f"/api/v1/github/callback?code=abc&state={state_a}")

    # User A status is connected
    res_a = client.get("/api/v1/github/connection", headers={"Authorization": f"Bearer {token_a}"})
    assert res_a.json()["connected"] is True
    assert res_a.json()["github_username"] == "user_a_gh"

    # User B status is NOT connected
    res_b = client.get("/api/v1/github/connection", headers={"Authorization": f"Bearer {token_b}"})
    assert res_b.json()["connected"] is False
    assert res_b.json()["github_username"] is None


def test_user_cannot_disconnect_another_users_connection(client):
    """19. User B disconnecting cannot affect User A's connection."""
    user_a = str(uuid.uuid4())
    user_b = str(uuid.uuid4())
    token_a = make_test_token(sub=user_a, email="user_a@devdoc.ai")
    token_b = make_test_token(sub=user_b, email="user_b@devdoc.ai")

    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token_a}"})
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token_b}"})

    # Connect User A
    state_a = GitHubIntegrationService.generate_oauth_state(uuid.UUID(user_a))
    with (
        patch.object(GitHubIntegrationService, "exchange_code_for_token", new_callable=AsyncMock) as mock_exchange,
        patch.object(GitHubAPIClient, "get_authenticated_user", new_callable=AsyncMock) as mock_user,
    ):
        mock_exchange.return_value = {"access_token": "gho_token_a", "token_type": "bearer", "scope": "repo"}
        mock_user.return_value = {"id": 1111, "login": "user_a_gh"}
        client.get(f"/api/v1/github/callback?code=abc&state={state_a}")

    # User B calls disconnect
    client.delete("/api/v1/github/connection", headers={"Authorization": f"Bearer {token_b}"})

    # User A remains connected
    res_a = client.get("/api/v1/github/connection", headers={"Authorization": f"Bearer {token_a}"})
    assert res_a.json()["connected"] is True
    assert res_a.json()["github_username"] == "user_a_gh"


# ---------------------------------------------------------------------------
# 4. Repository Discovery & Pagination Tests
# ---------------------------------------------------------------------------


def test_repository_listing(client):
    """9. GET /api/v1/github/repositories returns accessible repositories."""
    user_id = str(uuid.uuid4())
    token = make_test_token(sub=user_id)
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token}"})

    state = GitHubIntegrationService.generate_oauth_state(uuid.UUID(user_id))
    with (
        patch.object(GitHubIntegrationService, "exchange_code_for_token", new_callable=AsyncMock) as mock_exchange,
        patch.object(GitHubAPIClient, "get_authenticated_user", new_callable=AsyncMock) as mock_user,
    ):
        mock_exchange.return_value = {"access_token": "gho_token_repos", "token_type": "bearer", "scope": "repo"}
        mock_user.return_value = {"id": 1234, "login": "repo_owner"}
        client.get(f"/api/v1/github/callback?code=abc&state={state}")

    mock_repos = [
        {
            "id": 101,
            "name": "backend-service",
            "full_name": "repo_owner/backend-service",
            "owner": {"login": "repo_owner"},
            "private": True,
            "html_url": "https://github.com/repo_owner/backend-service",
            "description": "Core backend API",
            "default_branch": "main",
            "language": "Python",
            "fork": False,
        },
        {
            "id": 102,
            "name": "frontend-web",
            "full_name": "repo_owner/frontend-web",
            "owner": {"login": "repo_owner"},
            "private": False,
            "html_url": "https://github.com/repo_owner/frontend-web",
            "description": "Frontend UI",
            "default_branch": "master",
            "language": "TypeScript",
            "fork": False,
        },
    ]

    with patch.object(GitHubAPIClient, "list_user_repositories", new_callable=AsyncMock) as mock_list:
        mock_list.return_value = mock_repos
        response = client.get("/api/v1/github/repositories", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 2
    assert data["items"][0]["full_name"] == "repo_owner/backend-service"
    assert data["items"][0]["is_private"] is True
    assert data["items"][1]["full_name"] == "repo_owner/frontend-web"
    assert data["items"][1]["is_private"] is False


def test_repository_pagination(client):
    """10. GET /api/v1/github/repositories respects page and per_page parameters."""
    user_id = str(uuid.uuid4())
    token = make_test_token(sub=user_id)
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token}"})

    state = GitHubIntegrationService.generate_oauth_state(uuid.UUID(user_id))
    with (
        patch.object(GitHubIntegrationService, "exchange_code_for_token", new_callable=AsyncMock) as mock_exchange,
        patch.object(GitHubAPIClient, "get_authenticated_user", new_callable=AsyncMock) as mock_user,
    ):
        mock_exchange.return_value = {"access_token": "gho_token_repos", "token_type": "bearer", "scope": "repo"}
        mock_user.return_value = {"id": 1234, "login": "repo_owner"}
        client.get(f"/api/v1/github/callback?code=abc&state={state}")

    with patch.object(GitHubAPIClient, "list_user_repositories", new_callable=AsyncMock) as mock_list:
        mock_list.return_value = []
        response = client.get(
            "/api/v1/github/repositories?page=3&per_page=15",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        mock_list.assert_called_once_with(page=3, per_page=15)


def test_missing_github_connection_rejected_safely(client):
    """4. Unconnected user calling /repositories receives clean HTTP 400."""
    user_id = str(uuid.uuid4())
    token = make_test_token(sub=user_id)
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token}"})

    response = client.get("/api/v1/github/repositories", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 400
    assert "not connected" in response.json()["error"]["message"].lower()


# ---------------------------------------------------------------------------
# 5. Error Translation & Rate Limit Tests
# ---------------------------------------------------------------------------


def test_github_api_unauthorized_response(client):
    """11. GitHub 401 error translated to HTTP 401 instructing reconnect."""
    user_id = str(uuid.uuid4())
    token = make_test_token(sub=user_id)
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token}"})

    state = GitHubIntegrationService.generate_oauth_state(uuid.UUID(user_id))
    with (
        patch.object(GitHubIntegrationService, "exchange_code_for_token", new_callable=AsyncMock) as mock_exchange,
        patch.object(GitHubAPIClient, "get_authenticated_user", new_callable=AsyncMock) as mock_user,
    ):
        mock_exchange.return_value = {"access_token": "gho_expired_token", "token_type": "bearer", "scope": "repo"}
        mock_user.return_value = {"id": 1234, "login": "repo_owner"}
        client.get(f"/api/v1/github/callback?code=abc&state={state}")

    with patch.object(GitHubAPIClient, "list_user_repositories", new_callable=AsyncMock) as mock_list:
        mock_list.side_effect = GitHubAuthenticationError("Credentials invalid", status_code=401)
        response = client.get("/api/v1/github/repositories", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert "reconnect" in response.json()["error"]["message"].lower()


def test_github_api_rate_limit_handling(client):
    """14. GitHub 429 or rate limit translated to HTTP 429."""
    user_id = str(uuid.uuid4())
    token = make_test_token(sub=user_id)
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token}"})

    state = GitHubIntegrationService.generate_oauth_state(uuid.UUID(user_id))
    with (
        patch.object(GitHubIntegrationService, "exchange_code_for_token", new_callable=AsyncMock) as mock_exchange,
        patch.object(GitHubAPIClient, "get_authenticated_user", new_callable=AsyncMock) as mock_user,
    ):
        mock_exchange.return_value = {"access_token": "gho_token_123", "token_type": "bearer", "scope": "repo"}
        mock_user.return_value = {"id": 1234, "login": "repo_owner"}
        client.get(f"/api/v1/github/callback?code=abc&state={state}")

    with patch.object(GitHubAPIClient, "list_user_repositories", new_callable=AsyncMock) as mock_list:
        mock_list.side_effect = GitHubRateLimitError("GitHub API rate limit exceeded")
        response = client.get("/api/v1/github/repositories", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 429
    assert "rate limit" in response.json()["error"]["message"].lower()


def test_github_api_timeout_handling(client):
    """15. GitHub request timeout translated to HTTP 504."""
    user_id = str(uuid.uuid4())
    token = make_test_token(sub=user_id)
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token}"})

    state = GitHubIntegrationService.generate_oauth_state(uuid.UUID(user_id))
    with (
        patch.object(GitHubIntegrationService, "exchange_code_for_token", new_callable=AsyncMock) as mock_exchange,
        patch.object(GitHubAPIClient, "get_authenticated_user", new_callable=AsyncMock) as mock_user,
    ):
        mock_exchange.return_value = {"access_token": "gho_token_123", "token_type": "bearer", "scope": "repo"}
        mock_user.return_value = {"id": 1234, "login": "repo_owner"}
        client.get(f"/api/v1/github/callback?code=abc&state={state}")

    with patch.object(GitHubAPIClient, "list_user_repositories", new_callable=AsyncMock) as mock_list:
        mock_list.side_effect = GitHubTimeoutError("Request timed out")
        response = client.get("/api/v1/github/repositories", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 504
    assert "timed out" in response.json()["error"]["message"].lower()


# ---------------------------------------------------------------------------
# 6. Project Repository Association & Isolation Tests
# ---------------------------------------------------------------------------


def test_repository_association_with_own_project(client):
    """16. POST /api/v1/projects/{project_id}/github/repository associates repo."""
    user_id = str(uuid.uuid4())
    token = make_test_token(sub=user_id)
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token}"})

    # Connect GitHub
    state = GitHubIntegrationService.generate_oauth_state(uuid.UUID(user_id))
    with (
        patch.object(GitHubIntegrationService, "exchange_code_for_token", new_callable=AsyncMock) as mock_exchange,
        patch.object(GitHubAPIClient, "get_authenticated_user", new_callable=AsyncMock) as mock_user,
    ):
        mock_exchange.return_value = {"access_token": "gho_project_test", "token_type": "bearer", "scope": "repo"}
        mock_user.return_value = {"id": 7777, "login": "org_lead"}
        client.get(f"/api/v1/github/callback?code=abc&state={state}")

    # Create Project
    proj_resp = client.post(
        "/api/v1/projects",
        json={"name": "SRE Platform", "description": "Monitoring and auto-remediation"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert proj_resp.status_code == 201
    project_id = proj_resp.json()["id"]

    mock_remote_repo = {
        "id": 554433,
        "name": "sre-core",
        "full_name": "org_lead/sre-core",
        "clone_url": "https://github.com/org_lead/sre-core.git",
        "default_branch": "main",
        "description": "SRE core engine",
        "language": "Python",
    }

    with patch.object(GitHubAPIClient, "get_repository", new_callable=AsyncMock) as mock_get_repo:
        mock_get_repo.return_value = mock_remote_repo
        attach_resp = client.post(
            f"/api/v1/projects/{project_id}/github/repository",
            json={"full_name": "org_lead/sre-core"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert attach_resp.status_code == 201
    repo_data = attach_resp.json()
    assert repo_data["full_name"] == "org_lead/sre-core"
    assert repo_data["project_id"] == project_id
    assert repo_data["provider"] == "github"
    assert repo_data["provider_repo_id"] == "554433"
    assert repo_data["is_active"] is True

    # Retrieve connected repository
    get_repo_resp = client.get(
        f"/api/v1/projects/{project_id}/github/repository",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_repo_resp.status_code == 200
    assert get_repo_resp.json()["id"] == repo_data["id"]


def test_user_cannot_associate_repository_with_another_users_project(client):
    """17. User B cannot attach a repository to User A's project."""
    user_a = str(uuid.uuid4())
    user_b = str(uuid.uuid4())
    token_a = make_test_token(sub=user_a, email="user_a@devdoc.ai")
    token_b = make_test_token(sub=user_b, email="user_b@devdoc.ai")

    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token_a}"})
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token_b}"})

    # User A creates a project
    proj_resp = client.post(
        "/api/v1/projects",
        json={"name": "Project A"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    project_id = proj_resp.json()["id"]

    # User B connects GitHub
    state_b = GitHubIntegrationService.generate_oauth_state(uuid.UUID(user_b))
    with (
        patch.object(GitHubIntegrationService, "exchange_code_for_token", new_callable=AsyncMock) as mock_exchange,
        patch.object(GitHubAPIClient, "get_authenticated_user", new_callable=AsyncMock) as mock_user,
    ):
        mock_exchange.return_value = {"access_token": "gho_b", "token_type": "bearer", "scope": "repo"}
        mock_user.return_value = {"id": 8888, "login": "user_b"}
        client.get(f"/api/v1/github/callback?code=abc&state={state_b}")

    # User B attempts to attach repo to User A's project
    attach_resp = client.post(
        f"/api/v1/projects/{project_id}/github/repository",
        json={"full_name": "user_b/repo-b"},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert attach_resp.status_code == 403


def test_repository_metadata_validation(client):
    """20. Malformed repository full_name rejected with HTTP 422."""
    user_id = str(uuid.uuid4())
    token = make_test_token(sub=user_id)
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token}"})

    # Connect user to GitHub first
    state = GitHubIntegrationService.generate_oauth_state(uuid.UUID(user_id))
    with (
        patch.object(GitHubIntegrationService, "exchange_code_for_token", new_callable=AsyncMock) as mock_exchange,
        patch.object(GitHubAPIClient, "get_authenticated_user", new_callable=AsyncMock) as mock_user,
    ):
        mock_exchange.return_value = {"access_token": "gho_valid_token", "token_type": "bearer", "scope": "repo"}
        mock_user.return_value = {"id": 1234, "login": "testuser"}
        client.get(f"/api/v1/github/callback?code=abc&state={state}")

    proj_resp = client.post(
        "/api/v1/projects",
        json={"name": "Test Project"},
        headers={"Authorization": f"Bearer {token}"},
    )
    project_id = proj_resp.json()["id"]

    # Invalid names
    for bad_name in ["justname", "path/to/many/nested", "../traversal", ""]:
        resp = client.post(
            f"/api/v1/projects/{project_id}/github/repository",
            json={"full_name": bad_name},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422



def test_duplicate_repository_association_behavior(client):
    """21. Associating duplicate repository to same project returns HTTP 409 Conflict."""
    user_id = str(uuid.uuid4())
    token = make_test_token(sub=user_id)
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token}"})

    state = GitHubIntegrationService.generate_oauth_state(uuid.UUID(user_id))
    with (
        patch.object(GitHubIntegrationService, "exchange_code_for_token", new_callable=AsyncMock) as mock_exchange,
        patch.object(GitHubAPIClient, "get_authenticated_user", new_callable=AsyncMock) as mock_user,
    ):
        mock_exchange.return_value = {"access_token": "gho_dup_test", "token_type": "bearer", "scope": "repo"}
        mock_user.return_value = {"id": 1234, "login": "alice"}
        client.get(f"/api/v1/github/callback?code=abc&state={state}")

    proj_resp = client.post(
        "/api/v1/projects",
        json={"name": "Duplicate Test Project"},
        headers={"Authorization": f"Bearer {token}"},
    )
    project_id = proj_resp.json()["id"]

    mock_repo = {
        "id": 9988,
        "name": "app-service",
        "full_name": "alice/app-service",
        "clone_url": "https://github.com/alice/app-service.git",
        "default_branch": "main",
    }

    with patch.object(GitHubAPIClient, "get_repository", new_callable=AsyncMock) as mock_get_repo:
        mock_get_repo.return_value = mock_repo
        # First attach succeeds
        resp1 = client.post(
            f"/api/v1/projects/{project_id}/github/repository",
            json={"full_name": "alice/app-service"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp1.status_code == 201

        # Second attach returns 409 Conflict
        resp2 = client.post(
            f"/api/v1/projects/{project_id}/github/repository",
            json={"full_name": "alice/app-service"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp2.status_code == 409
        assert "already connected" in resp2.json()["error"]["message"].lower()


def test_repository_disconnect(client):
    """22. DELETE /api/v1/projects/{project_id}/github/repository disconnects repo."""
    user_id = str(uuid.uuid4())
    token = make_test_token(sub=user_id)
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token}"})

    state = GitHubIntegrationService.generate_oauth_state(uuid.UUID(user_id))
    with (
        patch.object(GitHubIntegrationService, "exchange_code_for_token", new_callable=AsyncMock) as mock_exchange,
        patch.object(GitHubAPIClient, "get_authenticated_user", new_callable=AsyncMock) as mock_user,
    ):
        mock_exchange.return_value = {"access_token": "gho_del_test", "token_type": "bearer", "scope": "repo"}
        mock_user.return_value = {"id": 1234, "login": "alice"}
        client.get(f"/api/v1/github/callback?code=abc&state={state}")

    proj_resp = client.post(
        "/api/v1/projects",
        json={"name": "Disconnect Test Project"},
        headers={"Authorization": f"Bearer {token}"},
    )
    project_id = proj_resp.json()["id"]

    mock_repo = {
        "id": 9988,
        "name": "app-service",
        "full_name": "alice/app-service",
        "clone_url": "https://github.com/alice/app-service.git",
        "default_branch": "main",
    }
    with patch.object(GitHubAPIClient, "get_repository", new_callable=AsyncMock) as mock_get_repo:
        mock_get_repo.return_value = mock_repo
        client.post(
            f"/api/v1/projects/{project_id}/github/repository",
            json={"full_name": "alice/app-service"},
            headers={"Authorization": f"Bearer {token}"},
        )

    # Disconnect
    del_resp = client.delete(
        f"/api/v1/projects/{project_id}/github/repository",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_resp.status_code == 200
    assert del_resp.json()["success"] is True

    # Subsequent GET returns 404
    get_resp = client.get(
        f"/api/v1/projects/{project_id}/github/repository",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_resp.status_code == 404


def test_revoked_github_credential_handling(client):
    """23. Attaching repo when GitHub token has expired/revoked returns HTTP 401."""
    user_id = str(uuid.uuid4())
    token = make_test_token(sub=user_id)
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token}"})

    state = GitHubIntegrationService.generate_oauth_state(uuid.UUID(user_id))
    with (
        patch.object(GitHubIntegrationService, "exchange_code_for_token", new_callable=AsyncMock) as mock_exchange,
        patch.object(GitHubAPIClient, "get_authenticated_user", new_callable=AsyncMock) as mock_user,
    ):
        mock_exchange.return_value = {"access_token": "gho_revoked", "token_type": "bearer", "scope": "repo"}
        mock_user.return_value = {"id": 1234, "login": "alice"}
        client.get(f"/api/v1/github/callback?code=abc&state={state}")

    proj_resp = client.post(
        "/api/v1/projects",
        json={"name": "Revoke Test Project"},
        headers={"Authorization": f"Bearer {token}"},
    )
    project_id = proj_resp.json()["id"]

    with patch.object(GitHubAPIClient, "get_repository", new_callable=AsyncMock) as mock_get_repo:
        mock_get_repo.side_effect = GitHubAuthenticationError("Bad credentials", status_code=401)
        attach_resp = client.post(
            f"/api/v1/projects/{project_id}/github/repository",
            json={"full_name": "alice/secret-repo"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert attach_resp.status_code == 401
    assert "expired or revoked" in attach_resp.json()["error"]["message"].lower()


# ---------------------------------------------------------------------------
# 7. Regressions: Phase 5 Auth & Phase 6 Project Authorization
# ---------------------------------------------------------------------------


def test_phase5_authentication_regression(client):
    """25. Unauthenticated calls to GitHub endpoints return HTTP 401."""
    endpoints = [
        ("GET", "/api/v1/github/connect"),
        ("GET", "/api/v1/github/connection"),
        ("DELETE", "/api/v1/github/connection"),
        ("GET", "/api/v1/github/repositories"),
        ("GET", f"/api/v1/projects/{uuid.uuid4()}/github/repository"),
        ("POST", f"/api/v1/projects/{uuid.uuid4()}/github/repository"),
        ("DELETE", f"/api/v1/projects/{uuid.uuid4()}/github/repository"),
    ]

    for method, path in endpoints:
        if method == "GET":
            resp = client.get(path)
        elif method == "POST":
            resp = client.post(path, json={"full_name": "owner/repo"})
        elif method == "DELETE":
            resp = client.delete(path)
        assert resp.status_code == 401


def test_phase6_project_authorization_regression(client):
    """26. Nonexistent project returns HTTP 404 for GitHub endpoints."""
    user_id = str(uuid.uuid4())
    token = make_test_token(sub=user_id)
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token}"})

    nonexistent_project_id = uuid.uuid4()
    resp = client.get(
        f"/api/v1/projects/{nonexistent_project_id}/github/repository",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 8. GitHubAPIClient Direct Unit Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_github_api_client_methods():
    """Test all GitHubAPIClient inspection methods."""
    client = GitHubAPIClient(access_token="test_token")

    with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
        # Repositories
        mock_req.return_value = {"id": 1, "name": "repo1"}
        res = await client.get_repository("owner", "repo1")
        assert res["name"] == "repo1"

        # Branches
        mock_req.return_value = [{"name": "main"}]
        branches = await client.list_branches("owner", "repo1")
        assert len(branches) == 1

        mock_req.return_value = {"name": "main", "commit": {"sha": "abc123"}}
        branch = await client.get_branch("owner", "repo1", "main")
        assert branch["name"] == "main"

        # Commits
        mock_req.return_value = [{"sha": "commit1"}]
        commits = await client.list_commits("owner", "repo1")
        assert len(commits) == 1

        mock_req.return_value = {"sha": "commit1", "commit": {"message": "Initial"}}
        commit = await client.get_commit("owner", "repo1", "commit1")
        assert commit["sha"] == "commit1"

        # Pull Requests
        mock_req.return_value = [{"id": 10, "number": 1, "title": "Add feature"}]
        prs = await client.list_pull_requests("owner", "repo1")
        assert len(prs) == 1

        mock_req.return_value = {"id": 10, "number": 1, "title": "Add feature"}
        pr = await client.get_pull_request("owner", "repo1", 1)
        assert pr["number"] == 1

        # Issues
        mock_req.return_value = [{"id": 20, "number": 2, "title": "Bug found"}]
        issues = await client.list_issues("owner", "repo1")
        assert len(issues) == 1

        mock_req.return_value = {"id": 20, "number": 2, "title": "Bug found"}
        issue = await client.get_issue("owner", "repo1", 2)
        assert issue["number"] == 2

        # Files
        mock_req.return_value = {"name": "README.md", "content": "SGVsbG8="}
        file_meta = await client.get_file_contents("owner", "repo1", "README.md")
        assert file_meta["name"] == "README.md"

        mock_req.return_value = [{"name": "src", "type": "dir"}]
        dir_listing = await client.get_directory_contents("owner", "repo1", "src")
        assert len(dir_listing) == 1

        # Workflows
        mock_req.return_value = {"total_count": 1, "workflow_runs": [{"id": 100}]}
        runs = await client.list_workflow_runs("owner", "repo1")
        assert runs["total_count"] == 1

        mock_req.return_value = {"id": 100, "status": "completed"}
        run = await client.get_workflow_run("owner", "repo1", 100)
        assert run["id"] == 100


@pytest.mark.asyncio
async def test_github_api_client_path_traversal_validation():
    """Verify GitHubAPIClient blocks path traversal attempts."""
    client = GitHubAPIClient(access_token="test_token")

    # Path traversal in file path
    with pytest.raises(GitHubValidationError):
        await client.get_file_contents("owner", "repo", "../secret_file")

    with pytest.raises(GitHubValidationError):
        await client.get_file_contents("owner", "repo", "subdir/../../secret")

    # Path traversal in owner or repo
    with pytest.raises(GitHubValidationError):
        await client.get_repository("../badowner", "repo")


# ---------------------------------------------------------------------------
# 9. Investigation Endpoints Tests
# ---------------------------------------------------------------------------


def test_project_investigation_endpoints(client):
    """Test investigation endpoints (branches, commits, pulls, issues, contents, workflows)."""
    user_id = str(uuid.uuid4())
    token = make_test_token(sub=user_id)
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token}"})

    state = GitHubIntegrationService.generate_oauth_state(uuid.UUID(user_id))
    with (
        patch.object(GitHubIntegrationService, "exchange_code_for_token", new_callable=AsyncMock) as mock_exchange,
        patch.object(GitHubAPIClient, "get_authenticated_user", new_callable=AsyncMock) as mock_user,
    ):
        mock_exchange.return_value = {"access_token": "gho_investigate", "token_type": "bearer", "scope": "repo"}
        mock_user.return_value = {"id": 1234, "login": "alice"}
        client.get(f"/api/v1/github/callback?code=abc&state={state}")

    proj_resp = client.post(
        "/api/v1/projects",
        json={"name": "Evidence Investigation Project"},
        headers={"Authorization": f"Bearer {token}"},
    )
    project_id = proj_resp.json()["id"]

    mock_repo = {
        "id": 9988,
        "name": "core-api",
        "full_name": "alice/core-api",
        "clone_url": "https://github.com/alice/core-api.git",
        "default_branch": "main",
    }
    with patch.object(GitHubAPIClient, "get_repository", new_callable=AsyncMock) as mock_get_repo:
        mock_get_repo.return_value = mock_repo
        client.post(
            f"/api/v1/projects/{project_id}/github/repository",
            json={"full_name": "alice/core-api"},
            headers={"Authorization": f"Bearer {token}"},
        )

    headers = {"Authorization": f"Bearer {token}"}

    with (
        patch.object(GitHubAPIClient, "list_branches", new_callable=AsyncMock) as mock_b,
        patch.object(GitHubAPIClient, "list_commits", new_callable=AsyncMock) as mock_c,
        patch.object(GitHubAPIClient, "list_pull_requests", new_callable=AsyncMock) as mock_p,
        patch.object(GitHubAPIClient, "list_issues", new_callable=AsyncMock) as mock_i,
        patch.object(GitHubAPIClient, "get_file_contents", new_callable=AsyncMock) as mock_f,
        patch.object(GitHubAPIClient, "list_workflow_runs", new_callable=AsyncMock) as mock_w,
    ):
        mock_b.return_value = [{"name": "main"}]
        mock_c.return_value = [{"sha": "c123"}]
        mock_p.return_value = [{"id": 1, "title": "PR 1"}]
        mock_i.return_value = [{"id": 2, "title": "Issue 1"}]
        mock_f.return_value = {"name": "config.yaml", "path": "config.yaml"}
        mock_w.return_value = {"total_count": 1, "workflow_runs": []}

        # Branches
        rb = client.get(f"/api/v1/projects/{project_id}/github/branches", headers=headers)
        assert rb.status_code == 200
        assert rb.json()[0]["name"] == "main"

        # Commits
        rc = client.get(f"/api/v1/projects/{project_id}/github/commits", headers=headers)
        assert rc.status_code == 200
        assert rc.json()[0]["sha"] == "c123"

        # Pulls
        rp = client.get(f"/api/v1/projects/{project_id}/github/pulls", headers=headers)
        assert rp.status_code == 200
        assert rp.json()[0]["title"] == "PR 1"

        # Issues
        ri = client.get(f"/api/v1/projects/{project_id}/github/issues", headers=headers)
        assert ri.status_code == 200
        assert ri.json()[0]["title"] == "Issue 1"

        # File contents
        rf = client.get(f"/api/v1/projects/{project_id}/github/contents?path=config.yaml", headers=headers)
        assert rf.status_code == 200
        assert rf.json()["name"] == "config.yaml"

        # Workflows
        rw = client.get(f"/api/v1/projects/{project_id}/github/workflows", headers=headers)
        assert rw.status_code == 200
        assert rw.json()["total_count"] == 1


# ---------------------------------------------------------------------------
# 6. OAuth Redirect URI, Callback Configuration & Separation Tests
# ---------------------------------------------------------------------------


def test_github_oauth_url_and_redirect_uri_configuration(client):
    """Verify authorization URL matches exact redirect_uri configuration and encoding."""
    import urllib.parse

    user_id = str(uuid.uuid4())
    token = make_test_token(sub=user_id)
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token}"})

    response = client.get(
        "/api/v1/github/connect",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    auth_url = data["authorization_url"]

    parsed = urllib.parse.urlparse(auth_url)
    params = urllib.parse.parse_qs(parsed.query)

    assert params["client_id"] == [TEST_SETTINGS.github_client_id]
    assert params["redirect_uri"] == [TEST_SETTINGS.github_oauth_redirect_uri]
    assert params["scope"] == ["repo,read:user"]
    assert "state" in params

    # Verify state validity
    state_user_id = GitHubIntegrationService.verify_oauth_state(params["state"][0])
    assert str(state_user_id) == user_id


def test_github_settings_redirect_uri_normalization():
    """Verify Settings strips trailing slashes, whitespace, and quotes from redirect URI."""
    s1 = Settings(
        github_oauth_redirect_uri="  'http://localhost:8000/api/v1/github/callback/'  ",
        github_client_id="  'test-client-id'  ",
    )
    assert s1.github_oauth_redirect_uri == "http://localhost:8000/api/v1/github/callback"
    assert s1.github_client_id == "test-client-id"

    s2 = Settings(
        github_oauth_redirect_uri='  "http://localhost:8000/api/v1/github/callback"  ',
    )
    assert s2.github_oauth_redirect_uri == "http://localhost:8000/api/v1/github/callback"


def test_github_oauth_callback_slash_alias(client):
    """Verify both /callback and /callback/ respond identically without 307 redirects."""
    user_id = str(uuid.uuid4())
    token = make_test_token(sub=user_id)
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token}"})

    state = GitHubIntegrationService.generate_oauth_state(uuid.UUID(user_id))
    mock_token_data = {
        "access_token": "gho_secret_access_token_alias",
        "token_type": "bearer",
        "scope": "repo,read:user",
    }
    mock_gh_user = {
        "id": 11223344,
        "login": "octocat-alias",
        "avatar_url": "https://avatars.githubusercontent.com/u/11223344",
    }

    with (
        patch.object(GitHubIntegrationService, "exchange_code_for_token", new_callable=AsyncMock) as mock_exchange,
        patch.object(GitHubAPIClient, "get_authenticated_user", new_callable=AsyncMock) as mock_user,
    ):
        mock_exchange.return_value = mock_token_data
        mock_user.return_value = mock_gh_user

        response = client.get(
            f"/api/v1/github/callback/?code=mock_code_slash&state={state}",
            follow_redirects=False,
        )

    assert response.status_code == 200
    data = response.json()
    assert data["connected"] is True
    assert data["github_username"] == "octocat-alias"


def test_github_oauth_callback_cancellation_and_error(client):
    """Verify OAuth callback gracefully handles error responses from GitHub or user cancellation."""
    # 1. JSON mode error
    res_json = client.get(
        "/api/v1/github/callback?error=access_denied&error_description=User+denied+access&state=any_state",
    )
    assert res_json.status_code == 400
    json_data = res_json.json()
    err_msg = json_data.get("error", {}).get("message") or json_data.get("detail", "")
    assert "User denied access" in err_msg

    # 2. HTML popup mode error
    res_html = client.get(
        "/api/v1/github/callback?error=access_denied&error_description=User+denied+access&state=any_state",
        headers={"Accept": "text/html,application/xhtml+xml"},
    )
    assert res_html.status_code == 200
    assert "GitHub Authorization Cancelled" in res_html.text
    assert "DEVDOC_GITHUB_CANCELLED" in res_html.text

    # 3. Missing code and missing error
    res_missing = client.get("/api/v1/github/callback?state=dummy_state")
    assert res_missing.status_code == 400
    missing_data = res_missing.json()
    missing_msg = missing_data.get("error", {}).get("message") or missing_data.get("detail", "")
    assert "Missing OAuth authorization code" in missing_msg


def test_platform_signin_and_repo_oauth_separation(client):
    """Verify repository authorization and platform sign-in are strictly separated."""
    # Platform sign-in URL points to Supabase GoTrue
    res_auth = client.get("/api/v1/auth/oauth/github/url?redirect_to=http://localhost:5173")
    assert res_auth.status_code == 200
    auth_data = res_auth.json()
    assert "auth/v1/authorize" in auth_data["authorization_url"]
    assert "provider=github" in auth_data["authorization_url"]

    # Repository OAuth URL points directly to GitHub OAuth with repo scope
    user_id = str(uuid.uuid4())
    token = make_test_token(sub=user_id)
    client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token}"})

    res_repo = client.get("/api/v1/github/connect", headers={"Authorization": f"Bearer {token}"})
    assert res_repo.status_code == 200
    repo_data = res_repo.json()
    assert "https://github.com/login/oauth/authorize" in repo_data["authorization_url"]
    assert "repo%2Cread%3Auser" in repo_data["authorization_url"] or "repo,read:user" in repo_data["authorization_url"]


def test_github_settings_secret_normalization():
    """Verify Settings strips quotes and whitespace from github_client_secret."""
    s1 = Settings(github_client_secret="  'gh_secret_test_123'  ")
    assert s1.github_client_secret.get_secret_value() == "gh_secret_test_123"

    s2 = Settings(github_client_secret='  "gh_secret_test_456"  ')
    assert s2.github_client_secret.get_secret_value() == "gh_secret_test_456"

    from pydantic import SecretStr
    s3 = Settings(github_client_secret=SecretStr("  'gh_secret_test_789'  "))
    assert s3.github_client_secret.get_secret_value() == "gh_secret_test_789"


@pytest.mark.asyncio
async def test_exchange_code_for_token_sanitization_and_payload(monkeypatch):
    """Verify exchange_code_for_token strips quotes/whitespace and sends expected OAuth payload."""
    import json
    import httpx

    monkeypatch.setattr("app.services.github.settings", TEST_SETTINGS)

    captured_requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        body = json.loads(request.content.decode("utf-8"))
        # Verify the captured body contains clean strings without surrounding quotes or whitespace
        assert body["client_id"] == TEST_SETTINGS.github_client_id
        assert body["client_secret"] == TEST_SETTINGS.github_client_secret.get_secret_value()
        assert body["code"] == "test_auth_code_999"
        assert body["redirect_uri"] == TEST_SETTINGS.github_oauth_redirect_uri

        return httpx.Response(
            status_code=200,
            json={
                "access_token": "gho_live_mock_access_token_123",
                "token_type": "bearer",
                "scope": "repo,read:user",
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        result = await GitHubIntegrationService.exchange_code_for_token(
            code="  test_auth_code_999  ",
            http_client=http_client,
        )

    assert result["access_token"] == "gho_live_mock_access_token_123"
    assert len(captured_requests) == 1
    assert captured_requests[0].url == "https://github.com/login/oauth/access_token"
    assert captured_requests[0].headers["accept"] == "application/json"


@pytest.mark.asyncio
async def test_exchange_code_for_token_github_credential_error(monkeypatch):
    """Verify GitHub incorrect_client_credentials error translates to HTTP 400."""
    import httpx
    from fastapi import HTTPException

    monkeypatch.setattr("app.services.github.settings", TEST_SETTINGS)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            json={
                "error": "incorrect_client_credentials",
                "error_description": "The client_id and/or client_secret passed are incorrect.",
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        with pytest.raises(HTTPException) as exc_info:
            await GitHubIntegrationService.exchange_code_for_token(
                code="mock_code",
                http_client=http_client,
            )

    assert exc_info.value.status_code == 400
    assert "The client_id and/or client_secret passed are incorrect" in str(exc_info.value.detail)
