"""Authentication API router for DEVDOC."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies import (
    get_token_payload,
    require_active_user,
    require_project_access,
)
from app.models.project import Project
from app.models.user import User
from app.schemas.auth import AuthSyncResponse
from app.schemas.user import UserResponse
from app.services.auth import get_or_sync_user_profile

router = APIRouter(prefix="/auth", tags=["auth"])


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
