"""GitHub OAuth and account connection API endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.github_client import GitHubAPIClient
from app.core.logging import logger
from app.core.rate_limit import enforce_tenant_rate_limit
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


@router.get(
    "/connect",
    response_model=GitHubConnectResponse,
    dependencies=[Depends(enforce_tenant_rate_limit)],
)
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
@router.get("/callback/", response_model=GitHubConnectionResponse, include_in_schema=False)
async def github_oauth_callback(
    request: Request,
    state: str = Query(..., description="Cryptographically signed CSRF state token"),
    code: str | None = Query(default=None, description="Temporary OAuth authorization code"),
    error: str | None = Query(default=None, description="OAuth error code if authorization failed"),
    error_description: str | None = Query(default=None, description="OAuth error description"),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Handle GitHub OAuth authorization callback.

    Validates CSRF state, exchanges the authorization code for an access token,
    retrieves the remote GitHub user profile, and securely stores the credential.
    Never exposes credentials in the response.
    """
    accept_header = request.headers.get("accept", "")

    # Handle user cancellation or GitHub OAuth error response
    if error:
        logger.warning("GitHub OAuth callback error: %s (%s)", error, error_description)
        if "text/html" in accept_header:
            html_content = f"""<!DOCTYPE html>
<html>
<head><title>GitHub Connection Cancelled - DEVDOC</title></head>
<body style="background:#0b0f19;color:#e2e8f0;font-family:system-ui,-apple-system,sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;">
<div style="text-align:center;max-width:420px;padding:32px;background:#131c31;border-radius:12px;border:1px solid #1e293b;box-shadow:0 10px 25px rgba(0,0,0,0.5);">
  <div style="font-size:36px;margin-bottom:12px;">⚠️</div>
  <h2 style="margin:0 0 8px 0;font-size:18px;color:#f8fafc;">GitHub Authorization Cancelled</h2>
  <p style="margin:0;font-size:13px;color:#94a3b8;">{error_description or error}</p>
  <script>
    if (window.opener) {{
      window.opener.postMessage({{ type: 'DEVDOC_GITHUB_CANCELLED' }}, '*');
      window.close();
    }} else {{
      window.location.href = 'http://localhost:5173/?github_cancelled=true';
    }}
  </script>
</div>
</body>
</html>"""
            return HTMLResponse(content=html_content, status_code=200)

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"GitHub OAuth error: {error_description or error}",
        )

    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing OAuth authorization code in callback",
        )

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

    if "text/html" in accept_header:
        html_content = """<!DOCTYPE html>
<html>
<head><title>GitHub Connected - DEVDOC</title></head>
<body style="background:#0b0f19;color:#e2e8f0;font-family:system-ui,-apple-system,sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;">
<div style="text-align:center;max-width:420px;padding:32px;background:#131c31;border-radius:12px;border:1px solid #1e293b;box-shadow:0 10px 25px rgba(0,0,0,0.5);">
  <div style="font-size:36px;margin-bottom:12px;">✅</div>
  <h2 style="margin:0 0 8px 0;font-size:18px;color:#f8fafc;">GitHub Connected Successfully</h2>
  <p style="margin:0;font-size:13px;color:#94a3b8;">Returning to DEVDOC console...</p>
  <script>
    if (window.opener) {
      window.opener.postMessage({ type: 'DEVDOC_GITHUB_CONNECTED' }, '*');
      window.close();
    } else {
      window.location.href = 'http://localhost:5173/?github_connected=true';
    }
  </script>
</div>
</body>
</html>"""
        return HTMLResponse(content=html_content, status_code=200)

    return GitHubConnectionResponse(
        connected=True,
        github_user_id=conn.github_user_id,
        github_username=conn.github_username,
        avatar_url=conn.avatar_url,
        scope=conn.scope,
        created_at=conn.created_at,
        updated_at=conn.updated_at,
    )


@router.get(
    "/connection",
    response_model=GitHubConnectionResponse,
    dependencies=[Depends(enforce_tenant_rate_limit)],
)
async def get_github_connection(
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_authenticated_db),
) -> GitHubConnectionResponse:
    """Return safe GitHub connection status for the authenticated DEVDOC user."""
    return await GitHubIntegrationService.get_connection_status(db, current_user.id)


@router.delete(
    "/connection",
    response_model=GitHubDisconnectResponse,
    dependencies=[Depends(enforce_tenant_rate_limit)],
)
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


@router.get(
    "/repositories",
    response_model=GitHubRepositoriesListResponse,
    dependencies=[Depends(enforce_tenant_rate_limit)],
)
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
