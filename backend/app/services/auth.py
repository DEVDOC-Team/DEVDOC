"""Authentication and user provisioning services."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import HTTPException, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import logger
from app.db.base import Base
from app.models.user import User


async def _email_is_verified(access_token: str | None, email: str) -> bool:
    """Ask Supabase Auth for authoritative email confirmation state.

    ``user_metadata`` is user-editable and must not be used as proof of email
    ownership. The Auth user endpoint derives confirmation from its own record.
    """
    if not access_token or not settings.supabase_url or not settings.supabase_anon_key:
        return False

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{settings.supabase_url.rstrip('/')}/auth/v1/user",
                headers={
                    "apikey": settings.supabase_anon_key,
                    "Authorization": f"Bearer {access_token}",
                },
            )
    except httpx.HTTPError as exc:
        logger.warning("Could not confirm Supabase email ownership: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase Auth is temporarily unavailable; retry sign-in shortly.",
        ) from exc

    if response.status_code != status.HTTP_200_OK:
        logger.warning("Supabase Auth could not confirm email ownership (status %s)", response.status_code)
        return False

    try:
        auth_user = response.json()
    except ValueError:
        return False

    confirmed_email = auth_user.get("email")
    email_confirmed_at = auth_user.get("email_confirmed_at")
    return (
        isinstance(confirmed_email, str)
        and confirmed_email.strip().lower() == email
        and bool(email_confirmed_at)
    )


async def _reconcile_email_profile(
    db: AsyncSession,
    existing: User,
    user_id: uuid.UUID,
    email: str,
    full_name: str | None,
    avatar_url: str | None,
    provider: str | None,
    provider_user_id: str | None,
    now: datetime,
) -> User:
    """Move a verified-email profile to its current Supabase subject, retaining references."""
    if existing.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This verified email belongs to a privileged DEVDOC profile with another Supabase identity. Ask an administrator to reconcile the account.",
        )

    old_id = existing.id
    retired_email = f"identity-migrated-{old_id.hex}@auth.local"

    # Free the unique email inside this transaction, then create the profile using
    # the current Supabase subject. The row lock in the caller prevents concurrent
    # sign-ins from reconciling the same email at the same time.
    existing.email = retired_email
    await db.flush()

    new_user = User(
        id=user_id,
        email=email,
        full_name=existing.full_name or full_name,
        avatar_url=existing.avatar_url or avatar_url,
        is_active=existing.is_active,
        is_superuser=False,
        provider=provider or existing.provider,
        provider_user_id=(
            provider_user_id
            or (existing.provider_user_id if not provider or provider == existing.provider else None)
        ),
        last_sign_in_at=now,
        created_at=existing.created_at,
        updated_at=now,
    )
    db.add(new_user)
    await db.flush()

    # Preserve ownership, approvals, audit history, and integrations while the
    # profile adopts the current auth.users UUID. All modeled user FKs are moved
    # before the retired profile is removed, within the same transaction.
    for table in Base.metadata.tables.values():
        if table is User.__table__:
            continue
        for column in table.columns:
            if any(foreign_key.column.table is User.__table__ for foreign_key in column.foreign_keys):
                await db.execute(
                    update(table)
                    .where(column == old_id)
                    .values({column.name: user_id})
                )

    await db.flush()
    await db.execute(delete(User.__table__).where(User.__table__.c.id == old_id))
    db.expunge(existing)
    logger.info("Reconciled existing user profile to current Supabase identity: %s", user_id)
    return new_user


async def get_or_sync_user_profile(
    db: AsyncSession,
    token_payload: dict[str, Any],
    access_token: str | None = None,
) -> User:
    """Synchronize a verified Supabase auth identity with a public.users record.

    Ensures that public.users.id strictly matches Supabase auth.users.id (JWT sub).
    Guarantees idempotency and safe profile provisioning without allowing arbitrary
    user impersonation.

    Args:
        db: Active async database session.
        token_payload: Verified JWT claims dictionary.
        access_token: Original verified bearer token, used to query Supabase Auth
            for authoritative email confirmation when profile reconciliation is needed.

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

    # Extract claims safely from the verified Supabase JWT structure.
    user_metadata = token_payload.get("user_metadata")
    if not isinstance(user_metadata, dict):
        user_metadata = {}
    app_metadata = token_payload.get("app_metadata")
    if not isinstance(app_metadata, dict):
        app_metadata = {}

    email_claim = token_payload.get("email") or user_metadata.get("email")
    email = str(email_claim).strip().lower() if email_claim else f"{user_id}@auth.local"
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
    external_provider_id = user_metadata.get("provider_id") or user_metadata.get("sub")
    provider_user_id = str(external_provider_id) if external_provider_id else None

    if user is not None:
        # Existing profile: update activity and only fill missing profile fields.
        user.last_sign_in_at = now
        if full_name and not user.full_name:
            user.full_name = full_name
        if avatar_url and not user.avatar_url:
            user.avatar_url = avatar_url
        if provider and not user.provider:
            user.provider = provider
        if provider_user_id and not user.provider_user_id:
            user.provider_user_id = provider_user_id
        await db.flush()
        logger.info("Synchronized existing user profile: %s", user_id)
        return user

    # A previous auth identity can leave a public.users profile behind after an
    # account is recreated or linked in Supabase. Reconcile by email only when
    # Supabase marks that email as verified; never create a duplicate email row.
    if email_claim:
        email_stmt = (
            select(User)
            .where(func.lower(User.email) == email)
            .with_for_update()
        )
        email_result = await db.execute(email_stmt)
        email_user = email_result.scalar_one_or_none()
        if email_user is not None:
            if email_user.id == user_id:
                email_user.last_sign_in_at = now
                if full_name and not email_user.full_name:
                    email_user.full_name = full_name
                if avatar_url and not email_user.avatar_url:
                    email_user.avatar_url = avatar_url
                if provider and not email_user.provider:
                    email_user.provider = provider
                if provider_user_id and not email_user.provider_user_id:
                    email_user.provider_user_id = provider_user_id
                await db.flush()
                return email_user

            if not await _email_is_verified(access_token, email):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="A profile already exists for this email. Confirm the email on the Supabase account before linking it to this profile.",
                )

            return await _reconcile_email_profile(
                db,
                email_user,
                user_id,
                email,
                full_name,
                avatar_url,
                provider,
                provider_user_id,
                now,
            )

    # First-time sign-in: provision new public.users record
    new_user = User(
        id=user_id,
        email=email,
        full_name=full_name,
        avatar_url=avatar_url,
        is_active=True,
        is_superuser=False,
        provider=provider,
        provider_user_id=provider_user_id,
        last_sign_in_at=now,
    )
    db.add(new_user)
    await db.flush()
    logger.info("Provisioned new user profile: %s", user_id)
    return new_user
