"""GitHub OAuth and account connection API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.github_client import GitHubAPIClient
from app.dependencies import get_authenticated_db, get_db, require_active_user
from app.models.user import User
from app.schemas.github import (
    GitHubConnectionResponse,
    GitHubConnectResponse,
    GitHubDisconnectResponse,
    GitHubRepositoriesListResponse,
)
from app.services.github import GitHubIntegrationService

router = APIRouter(prefix="/github", tags=["github"])


@router.get("/connect", response_model=GitHubConnectResponse)
async def initiate_github_connect(
    current_user: User = Depends(require_active_user),
) -> GitHubConnectResponse:
    """Initiate GitHub OAuth connection flow.

    Returns the GitHub OAuth authorization URL containing a cryptographically
    signed CSRF state token bound to the current user's session.
    """
    url, state = GitHubIntegrationService.get_authorization_url(current_user.id)
    return GitHubConnectResponse(authorization_url=url, state=state)


@router.get("/callback", response_model=GitHubConnectionResponse)
async def github_oauth_callback(
    code: str = Query(..., description="Temporary OAuth authorization code"),
    state: str = Query(..., description="Cryptographically signed CSRF state token"),
    db: AsyncSession = Depends(get_db),
) -> GitHubConnectionResponse:
    """Handle GitHub OAuth authorization callback.

    Validates CSRF state, exchanges the authorization code for an access token,
    retrieves the remote GitHub user profile, and securely stores the credential.
    Never exposes credentials in the response.
    """
    user_id = GitHubIntegrationService.verify_oauth_state(state)

    token_data = await GitHubIntegrationService.exchange_code_for_token(code)

    gh_client = GitHubAPIClient(access_token=token_data["access_token"])
    gh_user = await gh_client.get_authenticated_user()

    conn = await GitHubIntegrationService.save_or_update_connection(
        db=db,
        user_id=user_id,
        token_data=token_data,
        github_user=gh_user,
    )

    return GitHubConnectionResponse(
        connected=True,
        github_user_id=conn.github_user_id,
        github_username=conn.github_username,
        avatar_url=conn.avatar_url,
        scope=conn.scope,
        created_at=conn.created_at,
        updated_at=conn.updated_at,
    )


@router.get("/connection", response_model=GitHubConnectionResponse)
async def get_github_connection(
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_authenticated_db),
) -> GitHubConnectionResponse:
    """Return safe GitHub connection status for the authenticated DEVDOC user."""
    return await GitHubIntegrationService.get_connection_status(db, current_user.id)


@router.delete("/connection", response_model=GitHubDisconnectResponse)
async def disconnect_github(
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_authenticated_db),
) -> GitHubDisconnectResponse:
    """Disconnect and revoke stored GitHub integration credentials for the current user."""
    await GitHubIntegrationService.disconnect_user(db, current_user.id)
    return GitHubDisconnectResponse(
        success=True,
        message="GitHub connection removed successfully",
    )


@router.get("/repositories", response_model=GitHubRepositoriesListResponse)
async def list_github_repositories(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(30, ge=1, le=100, description="Items per page"),
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_authenticated_db),
) -> GitHubRepositoriesListResponse:
    """List repositories accessible to the user's connected GitHub account."""
    repos = await GitHubIntegrationService.list_repositories(
        db=db,
        user_id=current_user.id,
        page=page,
        per_page=per_page,
    )
    return GitHubRepositoriesListResponse(
        items=repos,
        page=page,
        per_page=per_page,
        total=len(repos),
    )
