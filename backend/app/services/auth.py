"""Authentication and user provisioning services."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.models.user import User


async def get_or_sync_user_profile(
    db: AsyncSession,
    token_payload: dict[str, Any],
) -> User:
    """Synchronize a verified Supabase auth identity with a public.users record.

    Ensures that public.users.id strictly matches Supabase auth.users.id (JWT sub).
    Guarantees idempotency and safe profile provisioning without allowing arbitrary
    user impersonation.

    Args:
        db: Active async database session.
        token_payload: Verified JWT claims dictionary.

    Returns:
        User: Authoritative user profile entity.
    """
    sub_raw = token_payload.get("sub")
    user_id = uuid.UUID(str(sub_raw))

    # Query existing profile by authoritative UUID
    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    now = datetime.now(UTC)

    # Extract claims safely from standard Supabase JWT structure
    user_metadata = token_payload.get("user_metadata") or {}
    app_metadata = token_payload.get("app_metadata") or {}

    email = (
        token_payload.get("email")
        or user_metadata.get("email")
        or f"{user_id}@auth.local"
    )
    full_name = (
        user_metadata.get("full_name")
        or user_metadata.get("name")
        or token_payload.get("full_name")
    )
    avatar_url = (
        user_metadata.get("avatar_url")
        or user_metadata.get("picture")
        or token_payload.get("avatar_url")
    )
    provider = app_metadata.get("provider") or token_payload.get("provider")

    if user is not None:
        # Existing user: update last_sign_in_at timestamp
        user.last_sign_in_at = now
        if full_name and not user.full_name:
            user.full_name = full_name
        if avatar_url and not user.avatar_url:
            user.avatar_url = avatar_url
        await db.flush()
        logger.info("Synchronized existing user profile: %s", user_id)
        return user

    # First-time sign-in: provision new public.users record
    new_user = User(
        id=user_id,
        email=email,
        full_name=full_name,
        avatar_url=avatar_url,
        is_active=True,
        is_superuser=False,
        provider=provider,
        last_sign_in_at=now,
    )
    db.add(new_user)
    await db.flush()
    logger.info("Provisioned new user profile: %s", user_id)
    return new_user
