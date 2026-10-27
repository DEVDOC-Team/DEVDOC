"""User profile management service."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.models.user import User
from app.schemas.user import UserUpdate


class UserService:
    """Service handling user profile updates and lifecycle operations."""

    @staticmethod
    async def update_profile(
        db: AsyncSession,
        current_user: User,
        data: UserUpdate,
    ) -> User:
        """Update mutable profile fields for the authenticated user."""
        update_dict = data.model_dump(exclude_unset=True)

        for field, value in update_dict.items():
            setattr(current_user, field, value)

        await db.commit()
        await db.refresh(current_user)

        logger.info("Updated user profile: %s", current_user.id)
        return current_user

    @staticmethod
    async def deactivate_user(
        db: AsyncSession,
        current_user: User,
    ) -> User:
        """Deactivate the authenticated user account (soft deletion)."""
        current_user.is_active = False
        await db.commit()
        await db.refresh(current_user)

        logger.info("Deactivated user account: %s", current_user.id)
        return current_user
