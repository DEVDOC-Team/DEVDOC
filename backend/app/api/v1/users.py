"""User API router for DEVDOC."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_authenticated_db, require_active_user
from app.models.user import User
from app.schemas.user import UserDeactivateResponse, UserResponse, UserUpdate
from app.services.user import UserService

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
async def get_my_profile(
    current_user: User = Depends(require_active_user),
) -> UserResponse:
    """Return the profile of the currently authenticated user."""
    return UserResponse.model_validate(current_user)


@router.patch("/me", response_model=UserResponse)
async def update_my_profile(
    update_data: UserUpdate,
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_authenticated_db),
) -> UserResponse:
    """Update mutable profile fields for the authenticated user."""
    updated_user = await UserService.update_profile(db, current_user, update_data)
    return UserResponse.model_validate(updated_user)


@router.delete("/me", response_model=UserDeactivateResponse)
async def delete_my_account(
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_authenticated_db),
) -> UserDeactivateResponse:
    """Deactivate the authenticated user's account."""
    deactivated_user = await UserService.deactivate_user(db, current_user)
    return UserDeactivateResponse(
        success=True,
        message="User account deactivated successfully",
        user_id=deactivated_user.id,
    )
