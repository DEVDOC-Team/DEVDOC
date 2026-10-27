"""Authentication API router for DEVDOC."""

from __future__ import annotations

import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import logger
from app.db.session import get_db
from app.dependencies import (
    get_token_payload,
    require_active_user,
    require_project_access,
)
from app.models.project import Project
from app.models.user import User
from app.schemas.auth import AuthSyncResponse, LoginRequest, LoginResponse
from app.schemas.user import UserResponse
from app.services.auth import get_or_sync_user_profile

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login_with_password(req: LoginRequest) -> LoginResponse:
    """Authenticate registered user via Supabase Auth password endpoint."""
    email = req.email.strip()
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
        )
    except Exception as exc:
        logger.error("Failed to connect to Supabase Auth: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        )

    if resp.status_code != 200:
        logger.warning("Supabase Auth rejected password sign-in for %s (status %d)", email, resp.status_code)
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
) -> User:
    """Return the profile of the currently authenticated user."""
    return current_user


@router.post("/sync", response_model=AuthSyncResponse)
async def sync_profile(
    token_payload: dict = Depends(get_token_payload),
    db: AsyncSession = Depends(get_db),
) -> AuthSyncResponse:
    """Explicitly synchronize the authenticated Supabase user profile with public.users."""
    user = await get_or_sync_user_profile(db, token_payload)
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
) -> dict:
    """Verify application-level project authorization for the current user."""
    return {
        "success": True,
        "project_id": str(project.id),
        "project_name": project.name,
        "owner_id": str(project.owner_id),
        "caller_id": str(current_user.id),
    }
