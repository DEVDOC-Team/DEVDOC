"""GitHub Integration Service.

Coordinates between FastAPI endpoints, database persistence (user_github_connections),
and the external GitHub REST API client (GitHubAPIClient).

Security Guarantees:
- Cryptographic state parameter verification for CSRF prevention in OAuth.
- Strict isolation: a user can only access their own GitHub connection.
- Project-scoped repository verification ensures the user has access to both the
  DEVDOC project and the remote GitHub repository.
- Tokens are never logged or leaked into error payloads.
"""

from __future__ import annotations

import hmac
import secrets
import time
import urllib.parse
import uuid
from typing import Any

import httpx
import jwt
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.github_client import (
    GitHubAPIClient,
    GitHubAPIError,
    GitHubAuthenticationError,
    GitHubNotFoundError,
    GitHubPermissionError,
    GitHubRateLimitError,
    GitHubTimeoutError,
    GitHubValidationError,
)
from app.core.logging import logger
from app.db.base import _utcnow
from app.models.github_connection import UserGitHubConnection
from app.models.project import Project
from app.models.repository import Repository, VCSProvider
from app.models.user import User
from app.schemas.github import (
    GitHubConnectionResponse,
    GitHubRepositoryInfo,
)

OAUTH_STATE_EXPIRATION_SECONDS = 600  # 10 minutes
GITHUB_OAUTH_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_OAUTH_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"


def _get_signing_secret() -> str:
    """Derive secret for signing OAuth CSRF state parameters."""
    secret = settings.supabase_jwt_secret.get_secret_value()
    if secret:
        return secret
    client_secret = settings.github_client_secret.get_secret_value()
    if client_secret:
        return client_secret
    return "devdoc-github-oauth-csrf-protection-secret-2026"


class GitHubIntegrationService:
    """Service handling GitHub OAuth and repository lifecycle."""

    # -----------------------------------------------------------------------
    # OAuth CSRF State Management
    # -----------------------------------------------------------------------

    @staticmethod
    def generate_oauth_state(user_id: uuid.UUID) -> str:
        """Generate a cryptographically signed CSRF state token bound to a DEVDOC user."""
        now = int(time.time())
        payload = {
            "sub": str(user_id),
            "nonce": secrets.token_hex(16),
            "iat": now,
            "exp": now + OAUTH_STATE_EXPIRATION_SECONDS,
            "purpose": "github_oauth",
        }
        return jwt.encode(payload, _get_signing_secret(), algorithm="HS256")

    @staticmethod
    def verify_oauth_state(state: str, expected_user_id: uuid.UUID | None = None) -> uuid.UUID:
        """Verify CSRF state signature and expiration, ensuring binding to the user."""
        if not state:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing OAuth state parameter",
            )
        try:
            payload = jwt.decode(
                state,
                _get_signing_secret(),
                algorithms=["HS256"],
                options={"verify_signature": True, "verify_exp": True},
            )
        except jwt.ExpiredSignatureError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="OAuth state parameter has expired. Please initiate connection again.",
            ) from exc
        except (jwt.DecodeError, jwt.InvalidTokenError) as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or tampered OAuth state parameter",
            ) from exc

        if payload.get("purpose") != "github_oauth":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid OAuth state purpose",
            )

        sub_str = payload.get("sub")
        if not sub_str:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid user reference in OAuth state",
            )

        try:
            state_user_id = uuid.UUID(sub_str)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Malformed user ID in OAuth state",
            ) from exc

        if expected_user_id is not None and not hmac.compare_digest(str(state_user_id), str(expected_user_id)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="OAuth state does not match the authenticated user",
            )

        return state_user_id

    # -----------------------------------------------------------------------
    # Authorization URL & Token Exchange
    # -----------------------------------------------------------------------

    @classmethod
    def get_authorization_url(cls, user_id: uuid.UUID) -> tuple[str, str]:
        """Construct the GitHub OAuth authorization URL with CSRF state token."""
        client_id = settings.github_client_id.strip().strip("'\"").strip()
        redirect_uri = settings.github_oauth_redirect_uri.strip().strip("'\"").strip()
        if not client_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="GitHub OAuth is not configured: missing client ID",
            )

        state = cls.generate_oauth_state(user_id)
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": "repo,read:user",
            "state": state,
            "allow_signup": "true",
        }
        url = f"{GITHUB_OAUTH_AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"
        return url, state

    @staticmethod
    async def exchange_code_for_token(
        code: str,
        http_client: httpx.AsyncClient | None = None,
    ) -> dict[str, Any]:
        """Exchange the temporary OAuth code for a GitHub access token."""
        client_id = settings.github_client_id.strip().strip("'\"").strip()
        client_secret = settings.github_client_secret.get_secret_value().strip().strip("'\"").strip()
        redirect_uri = settings.github_oauth_redirect_uri.strip().strip("'\"").strip()
        clean_code = (code or "").strip()

        if not client_id or not client_secret:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="GitHub OAuth is not configured: missing client credentials",
            )
        if not clean_code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing OAuth authorization code in callback",
            )

        payload = {
            "client_id": client_id,
            "client_secret": client_secret,
            "code": clean_code,
            "redirect_uri": redirect_uri,
        }
        headers = {"Accept": "application/json"}

        should_close = False
        client = http_client
        if client is None:
            client = httpx.AsyncClient(timeout=10.0)
            should_close = True

        try:
            # GitHub's app user-authorization code exchange expects form-encoded
            # parameters. Sending JSON can make valid credentials appear missing.
            resp = await client.post(GITHUB_OAUTH_TOKEN_URL, data=payload, headers=headers)
        except httpx.RequestError as exc:
            logger.error("Network error during GitHub OAuth token exchange: %s", type(exc).__name__)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to reach GitHub for OAuth exchange",
            ) from exc
        finally:
            if should_close:
                await client.aclose()

        if resp.status_code != 200:
            logger.error("GitHub token exchange returned HTTP %d", resp.status_code)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="GitHub OAuth exchange endpoint returned an error",
            )

        data = resp.json()
        if "error" in data:
            error_code = data.get("error")
            error_desc = data.get("error_description", "OAuth code exchange failed")
            logger.warning("GitHub OAuth exchange error: %s", error_code)
            if error_code == "incorrect_client_credentials":
                error_desc = (
                    "GitHub rejected the OAuth credentials sent by the backend. Use "
                    "the OAuth App Client ID (not its App ID) and the generated Client "
                    "Secret value from that same app. The authorizing GitHub account "
                    "can be different from the app owner's. After updating backend/.env, "
                    "fully restart the backend and start a new connection."
                )
            elif error_code == "bad_verification_code":
                error_desc = "GitHub authorization code expired or was already used. Start the connection again."
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"GitHub OAuth error: {error_desc}",
            )

        access_token = data.get("access_token")
        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Invalid response from GitHub: missing access token",
            )

        return data

    # -----------------------------------------------------------------------
    # User Connection Persistence & Status
    # -----------------------------------------------------------------------

    @staticmethod
    async def get_user_connection(
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> UserGitHubConnection | None:
        """Fetch the GitHub connection record for the specified user."""
        stmt = select(UserGitHubConnection).where(UserGitHubConnection.user_id == user_id)
        res = await db.execute(stmt)
        return res.scalar_one_or_none()

    @classmethod
    async def get_connection_status(
        cls,
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> GitHubConnectionResponse:
        """Return safe, non-sensitive connection status."""
        conn = await cls.get_user_connection(db, user_id)
        if conn is None:
            return GitHubConnectionResponse(connected=False)

        return GitHubConnectionResponse(
            connected=True,
            github_user_id=conn.github_user_id,
            github_username=conn.github_username,
            avatar_url=conn.avatar_url,
            scope=conn.scope,
            created_at=conn.created_at,
            updated_at=conn.updated_at,
        )

    @classmethod
    async def save_or_update_connection(
        cls,
        db: AsyncSession,
        user_id: uuid.UUID,
        token_data: dict[str, Any],
        github_user: dict[str, Any],
    ) -> UserGitHubConnection:
        """Persist or update the user's GitHub connection."""
        conn = await cls.get_user_connection(db, user_id)

        access_token = token_data["access_token"]
        token_type = token_data.get("token_type", "bearer")
        scope = token_data.get("scope")

        gh_id = str(github_user["id"])
        gh_username = github_user.get("login", "")
        avatar = github_user.get("avatar_url")

        if conn is None:
            conn = UserGitHubConnection(
                id=uuid.uuid4(),
                user_id=user_id,
                github_user_id=gh_id,
                github_username=gh_username,
                avatar_url=avatar,
                access_token=access_token,
                token_type=token_type,
                scope=scope,
            )
            db.add(conn)
        else:
            conn.github_user_id = gh_id
            conn.github_username = gh_username
            conn.avatar_url = avatar
            conn.access_token = access_token
            conn.token_type = token_type
            conn.scope = scope
            conn.updated_at = _utcnow()

        await db.commit()
        await db.refresh(conn)

        logger.info("Saved GitHub connection for user %s (GitHub: %s)", user_id, gh_username)
        return conn

    @classmethod
    async def disconnect_user(cls, db: AsyncSession, user_id: uuid.UUID) -> bool:
        """Disconnect and remove GitHub credentials for the user."""
        conn = await cls.get_user_connection(db, user_id)
        if conn is None:
            return False

        await db.delete(conn)
        await db.commit()
        logger.info("Disconnected GitHub integration for user %s", user_id)
        return True

    # -----------------------------------------------------------------------
    # GitHub API Client Factory & Error Translation
    # -----------------------------------------------------------------------

    @classmethod
    async def get_client_for_user(
        cls,
        db: AsyncSession,
        user_id: uuid.UUID,
        http_client: httpx.AsyncClient | None = None,
    ) -> tuple[GitHubAPIClient, UserGitHubConnection]:
        """Obtain an authenticated GitHub API client for the user."""
        conn = await cls.get_user_connection(db, user_id)
        if conn is None or not conn.access_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="GitHub account is not connected",
            )
        client = GitHubAPIClient(access_token=conn.access_token, client=http_client)
        return client, conn

    # -----------------------------------------------------------------------
    # Repository Discovery & Project Association
    # -----------------------------------------------------------------------

    @classmethod
    async def list_repositories(
        cls,
        db: AsyncSession,
        user_id: uuid.UUID,
        page: int = 1,
        per_page: int = 30,
        http_client: httpx.AsyncClient | None = None,
    ) -> list[GitHubRepositoryInfo]:
        """List repositories accessible to the user's connected GitHub account."""
        client, _ = await cls.get_client_for_user(db, user_id, http_client=http_client)

        try:
            raw_repos = await client.list_user_repositories(page=page, per_page=per_page)
        except GitHubAuthenticationError as exc:
            raise HTTPException(
                status_code=status.HTTP_428_PRECONDITION_REQUIRED,
                detail="GitHub access needs to be reauthorized. Reconnect your GitHub account and try again.",
            ) from exc
        except GitHubRateLimitError as exc:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="GitHub API rate limit exceeded. Please try again later.",
            ) from exc
        except GitHubTimeoutError as exc:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="GitHub API request timed out",
            ) from exc
        except GitHubAPIError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"GitHub API error: {exc.message}",
            ) from exc

        results = []
        for r in raw_repos:
            try:
                results.append(
                    GitHubRepositoryInfo(
                        id=r["id"],
                        name=r["name"],
                        full_name=r["full_name"],
                        owner=r["owner"]["login"] if isinstance(r.get("owner"), dict) else str(r.get("owner", "")),
                        is_private=r.get("private", False),
                        html_url=r.get("html_url", ""),
                        description=r.get("description"),
                        default_branch=r.get("default_branch", "main"),
                        language=r.get("language"),
                        fork=r.get("fork", False),
                    )
                )
            except Exception as exc:
                logger.warning("Skipping malformed repo entry: %s", exc)
                continue

        return results

    @classmethod
    async def attach_repository_to_project(
        cls,
        db: AsyncSession,
        current_user: User,
        project: Project,
        full_name: str,
        http_client: httpx.AsyncClient | None = None,
    ) -> Repository:
        """Verify remote access on GitHub and associate the repository with the DEVDOC project."""
        parts = full_name.strip().split("/")
        if (
            len(parts) != 2
            or not parts[0]
            or not parts[1]
            or ".." in parts[0]
            or ".." in parts[1]
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Repository full_name must be in 'owner/repo' format without traversal elements",
            )
        owner, repo_name = parts[0], parts[1]


        # Verify project does not already have an active repository with this name
        stmt = select(Repository).where(
            Repository.project_id == project.id,
            Repository.full_name == full_name,
            Repository.is_active.is_(True),
        )
        existing = (await db.execute(stmt)).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Repository '{full_name}' is already connected to this project",
            )

        # Retrieve user GitHub client to verify authorization on GitHub
        client, _ = await cls.get_client_for_user(db, current_user.id, http_client=http_client)

        try:
            repo_meta = await client.get_repository(owner, repo_name)
        except GitHubNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"GitHub repository '{full_name}' not found or access denied by GitHub",
            ) from exc
        except GitHubAuthenticationError as exc:
            raise HTTPException(
                status_code=status.HTTP_428_PRECONDITION_REQUIRED,
                detail="GitHub access needs to be reauthorized. Reconnect your GitHub account and try again.",
            ) from exc
        except GitHubPermissionError as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions on GitHub to access repository '{full_name}'",
            ) from exc
        except GitHubRateLimitError as exc:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="GitHub API rate limit exceeded",
            ) from exc
        except (GitHubValidationError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid repository parameters: {exc}",
            ) from exc
        except GitHubAPIError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to verify repository on GitHub: {exc.message}",
            ) from exc

        # Create repository record
        repo = Repository(
            id=uuid.uuid4(),
            project_id=project.id,
            provider=VCSProvider.GITHUB,
            full_name=repo_meta["full_name"],
            provider_repo_id=str(repo_meta["id"]),
            clone_url=repo_meta.get("clone_url"),
            default_branch=repo_meta.get("default_branch", "main"),
            description=repo_meta.get("description"),
            language=repo_meta.get("language"),
            is_active=True,
            last_synced_at=_utcnow(),
        )
        db.add(repo)
        await db.commit()
        await db.refresh(repo)

        logger.info(
            "Attached GitHub repository '%s' to project %s (%s)",
            repo.full_name,
            project.name,
            project.id,
        )
        return repo

    @classmethod
    async def get_project_repository(
        cls,
        db: AsyncSession,
        project: Project,
    ) -> Repository:
        """Retrieve the active connected GitHub repository for the project."""
        stmt = (
            select(Repository)
            .where(
                Repository.project_id == project.id,
                Repository.provider == VCSProvider.GITHUB,
                Repository.is_active.is_(True),
            )
            .order_by(Repository.created_at.desc())
        )
        repo = (await db.execute(stmt)).scalars().first()
        if repo is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No GitHub repository is connected to this project",
            )
        return repo

    @classmethod
    async def disconnect_project_repository(
        cls,
        db: AsyncSession,
        project: Project,
    ) -> uuid.UUID:
        """Disconnect the active GitHub repository from the project."""
        repo = await cls.get_project_repository(db, project)
        repo_id = repo.id
        await db.delete(repo)
        await db.commit()

        logger.info("Disconnected repository %s from project %s", repo_id, project.id)
        return repo_id

    # -----------------------------------------------------------------------
    # Evidence & Inspection Retrieval (for investigation pipeline)
    # -----------------------------------------------------------------------

    @classmethod
    async def list_project_branches(
        cls,
        db: AsyncSession,
        user_id: uuid.UUID,
        project: Project,
        page: int = 1,
        per_page: int = 30,
        http_client: httpx.AsyncClient | None = None,
    ) -> list[dict[str, Any]]:
        repo = await cls.get_project_repository(db, project)
        owner, repo_name = repo.full_name.split("/")
        client, _ = await cls.get_client_for_user(db, user_id, http_client=http_client)
        return await client.list_branches(owner, repo_name, page=page, per_page=per_page)

    @classmethod
    async def list_project_commits(
        cls,
        db: AsyncSession,
        user_id: uuid.UUID,
        project: Project,
        sha: str | None = None,
        page: int = 1,
        per_page: int = 30,
        http_client: httpx.AsyncClient | None = None,
    ) -> list[dict[str, Any]]:
        repo = await cls.get_project_repository(db, project)
        owner, repo_name = repo.full_name.split("/")
        client, _ = await cls.get_client_for_user(db, user_id, http_client=http_client)
        return await client.list_commits(owner, repo_name, sha=sha, page=page, per_page=per_page)

    @classmethod
    async def list_project_pulls(
        cls,
        db: AsyncSession,
        user_id: uuid.UUID,
        project: Project,
        state: str = "open",
        page: int = 1,
        per_page: int = 30,
        http_client: httpx.AsyncClient | None = None,
    ) -> list[dict[str, Any]]:
        repo = await cls.get_project_repository(db, project)
        owner, repo_name = repo.full_name.split("/")
        client, _ = await cls.get_client_for_user(db, user_id, http_client=http_client)
        return await client.list_pull_requests(owner, repo_name, state=state, page=page, per_page=per_page)

    @classmethod
    async def list_project_issues(
        cls,
        db: AsyncSession,
        user_id: uuid.UUID,
        project: Project,
        state: str = "open",
        page: int = 1,
        per_page: int = 30,
        http_client: httpx.AsyncClient | None = None,
    ) -> list[dict[str, Any]]:
        repo = await cls.get_project_repository(db, project)
        owner, repo_name = repo.full_name.split("/")
        client, _ = await cls.get_client_for_user(db, user_id, http_client=http_client)
        return await client.list_issues(owner, repo_name, state=state, page=page, per_page=per_page)

    @classmethod
    async def get_project_file_content(
        cls,
        db: AsyncSession,
        user_id: uuid.UUID,
        project: Project,
        path: str,
        ref: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> dict[str, Any]:
        repo = await cls.get_project_repository(db, project)
        owner, repo_name = repo.full_name.split("/")
        client, _ = await cls.get_client_for_user(db, user_id, http_client=http_client)
        return await client.get_file_contents(owner, repo_name, path=path, ref=ref)

    @classmethod
    async def list_project_workflow_runs(
        cls,
        db: AsyncSession,
        user_id: uuid.UUID,
        project: Project,
        page: int = 1,
        per_page: int = 30,
        http_client: httpx.AsyncClient | None = None,
    ) -> dict[str, Any]:
        repo = await cls.get_project_repository(db, project)
        owner, repo_name = repo.full_name.split("/")
        client, _ = await cls.get_client_for_user(db, user_id, http_client=http_client)
        return await client.list_workflow_runs(owner, repo_name, page=page, per_page=per_page)
