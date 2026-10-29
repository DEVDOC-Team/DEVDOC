"""Authentication API router for DEVDOC."""

from __future__ import annotations

import re
import urllib.parse
import uuid

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import logger
from app.core.rate_limit import enforce_tenant_rate_limit
from app.core.security import extract_bearer_token
from app.db.session import get_db
from app.dependencies import (
    get_token_payload,
    require_active_user,
    require_project_access,
)
from app.models.project import Project
from app.models.user import User
from app.schemas.auth import (
    AuthSyncResponse,
    LoginRequest,
    LoginResponse,
    OAuthAuthorizeUrlResponse,
    OAuthExchangeRequest,
    OAuthProviderInfo,
)
from app.schemas.user import UserResponse
from app.services.auth import get_or_sync_user_profile

router = APIRouter(prefix="/auth", tags=["auth"])

SUPPORTED_OAUTH_PROVIDERS: set[str] = {"google", "github"}

DEFAULT_ALLOWED_REDIRECT_ORIGINS: set[str] = {
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
}


def _validate_oauth_redirect_url(redirect_to: str | None) -> str:
    """Validate and sanitize an OAuth redirect destination against an allowlist."""
    if not redirect_to:
        return "http://localhost:5173"

    try:
        parsed = urllib.parse.urlparse(redirect_to)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Malformed redirect URI",
        ) from None

    if not parsed.scheme or not parsed.netloc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Redirect URI must be an absolute URL with scheme and host",
        )

    if parsed.scheme not in ("http", "https"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported redirect URI scheme",
        )

    origin = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
    allowed_origins = set(DEFAULT_ALLOWED_REDIRECT_ORIGINS)
    if settings.cors_origins:
        for co in settings.cors_origins:
            if co and co != "*":
                allowed_origins.add(co.rstrip("/"))

    if origin not in allowed_origins:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Redirect URI origin '{origin}' is not authorized. Must match an approved client origin.",
        )

    return redirect_to


@router.get("/oauth/providers", response_model=list[OAuthProviderInfo])
async def list_oauth_providers() -> list[OAuthProviderInfo]:
    """List supported OAuth authentication providers and their configuration availability."""
    is_configured = bool(settings.supabase_url and settings.supabase_anon_key)
    return [
        OAuthProviderInfo(id="google", name="Google", enabled=is_configured),
        OAuthProviderInfo(id="github", name="GitHub", enabled=is_configured),
    ]


@router.get("/oauth/{provider}/url", response_model=OAuthAuthorizeUrlResponse)
async def get_oauth_authorization_url(
    provider: str,
    redirect_to: str | None = None,
    code_challenge: str | None = None,
) -> OAuthAuthorizeUrlResponse:
    """Generate a validated Supabase GoTrue OAuth authorization URL for Google or GitHub."""
    provider_clean = provider.strip().lower()
    if provider_clean not in SUPPORTED_OAUTH_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported OAuth provider '{provider}'. Supported providers: {', '.join(sorted(SUPPORTED_OAUTH_PROVIDERS))}",
        )

    supabase_url = settings.supabase_url
    anon_key = settings.supabase_anon_key
    if not supabase_url or not anon_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service is not configured",
        )

    validated_redirect = _validate_oauth_redirect_url(redirect_to)
    params = {
        "provider": provider_clean,
        "redirect_to": validated_redirect,
    }
    if code_challenge is not None:
        if not re.fullmatch(r"[A-Za-z0-9_-]{43}", code_challenge):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid OAuth PKCE code challenge",
            )
        params["code_challenge"] = code_challenge
        params["code_challenge_method"] = "s256"
    encoded_params = urllib.parse.urlencode(params)
    auth_url = f"{supabase_url.rstrip('/')}/auth/v1/authorize?{encoded_params}"

    return OAuthAuthorizeUrlResponse(
        provider=provider_clean,
        authorization_url=auth_url,
        redirect_to=validated_redirect,
    )


@router.post("/oauth/exchange", response_model=LoginResponse)
async def exchange_oauth_code(req: OAuthExchangeRequest) -> LoginResponse:
    """Exchange an OAuth PKCE / authorization code for a Supabase session."""
    if not req.auth_code.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Authorization code is required",
        )

    supabase_url = settings.supabase_url
    anon_key = settings.supabase_anon_key
    if not supabase_url or not anon_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service is not configured",
        )

    token_endpoint = f"{supabase_url.rstrip('/')}/auth/v1/token?grant_type=pkce"
    payload: dict = {
        "auth_code": req.auth_code.strip(),
    }
    if req.code_verifier:
        payload["code_verifier"] = req.code_verifier.strip()

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                token_endpoint,
                headers={
                    "apikey": anon_key,
                    "Authorization": f"Bearer {anon_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="OAuth token exchange timed out",
        ) from None
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OAuth authentication service unavailable",
        ) from exc

    if resp.status_code != 200:
        error_msg = "Invalid or expired authorization code"
        try:
            err_data = resp.json()
            if isinstance(err_data, dict):
                error_msg = str(
                    err_data.get("msg")
                    or err_data.get("error_description")
                    or error_msg
                )
        except Exception:
            pass

        if resp.status_code >= 500:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication provider service unavailable",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg,
        )

    data = resp.json()
    access_token = data.get("access_token")
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No access token returned by authentication provider",
        )

    return LoginResponse(
        access_token=access_token,
        token_type=data.get("token_type", "bearer"),
        expires_in=data.get("expires_in"),
        user=data.get("user"),
    )


@router.post("/login", response_model=LoginResponse)
async def login_with_password(req: LoginRequest) -> LoginResponse:
    """Authenticate registered user via Supabase Auth password endpoint."""
    email = req.email.strip().lower()
    if not email or not req.password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email and password are required",
        )

    supabase_url = settings.supabase_url
    anon_key = settings.supabase_anon_key
    if not supabase_url or not anon_key:
        logger.error("Supabase Auth is not configured on backend")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service is not configured",
        )

    auth_endpoint = f"{supabase_url.rstrip('/')}/auth/v1/token?grant_type=password"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                auth_endpoint,
                headers={
                    "apikey": anon_key,
                    "Authorization": f"Bearer {anon_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "email": email,
                    "password": req.password,
                },
            )
    except httpx.TimeoutException:
        logger.warning("Supabase Auth password sign-in timed out for %s", email)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Authentication request timed out",
        ) from None
    except Exception as exc:
        logger.error("Failed to connect to Supabase Auth: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        ) from exc

    if resp.status_code != 200:
        error_code = ""
        error_msg = ""
        try:
            err_data = resp.json()
            if isinstance(err_data, dict):
                error_code = str(err_data.get("error_code") or err_data.get("error") or "").lower()
                error_msg = str(
                    err_data.get("msg")
                    or err_data.get("error_description")
                    or err_data.get("message")
                    or ""
                )
        except Exception:
            err_data = None

        logger.warning(
            "Supabase Auth rejected password sign-in for %s (status %d, code: %s, msg: %s)",
            email,
            resp.status_code,
            error_code,
            error_msg,
        )

        if resp.status_code == 429 or "rate_limit" in error_code or "too many" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many authentication attempts. Please try again later.",
            )

        if "email_not_confirmed" in error_code or "confirm" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email address has not been confirmed. Please check your inbox for the confirmation link.",
            )

        if resp.status_code in (401, 403) and ("api key" in error_msg.lower() or "apikey" in error_code):
            logger.error("Backend SUPABASE_ANON_KEY was rejected by Supabase API gateway")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Authentication service configuration error: invalid API key",
            )

        if resp.status_code == 404:
            logger.error("Supabase Auth endpoint not found at %s", auth_endpoint)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Authentication service endpoint not found",
            )

        if resp.status_code >= 500:
            logger.error("Supabase Auth service returned %d: %s", resp.status_code, error_msg)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service is temporarily unavailable",
            )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    data = resp.json()
    access_token = data.get("access_token")
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No access token returned by authentication service",
        )

    return LoginResponse(
        access_token=access_token,
        token_type=data.get("token_type", "bearer"),
        expires_in=data.get("expires_in"),
        user=data.get("user"),
    )


@router.get("/me", response_model=UserResponse)
async def get_my_profile(
    current_user: User = Depends(require_active_user),
    _: None = Depends(enforce_tenant_rate_limit),
) -> User:
    """Return the profile of the currently authenticated user."""
    return current_user


@router.post("/sync", response_model=AuthSyncResponse)
async def sync_profile(
    token_payload: dict = Depends(get_token_payload),
    authorization: str | None = Header(None, alias="Authorization"),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(enforce_tenant_rate_limit),
) -> AuthSyncResponse:
    """Explicitly synchronize the authenticated Supabase user profile with public.users."""
    access_token = extract_bearer_token(authorization)
    user = await get_or_sync_user_profile(db, token_payload, access_token)
    return AuthSyncResponse(
        success=True,
        message="User profile synchronized successfully",
        user=UserResponse.model_validate(user),
    )


@router.get("/projects/{project_id}/verify-access")
async def verify_project_access(
    project_id: uuid.UUID,
    project: Project = Depends(require_project_access),
    current_user: User = Depends(require_active_user),
    _: None = Depends(enforce_tenant_rate_limit),
) -> dict:
    """Verify application-level project authorization for the current user."""
    return {
        "success": True,
        "project_id": str(project.id),
        "project_name": project.name,
        "owner_id": str(project.owner_id),
        "caller_id": str(current_user.id),
    }
