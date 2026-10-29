"""Authentication and authorization FastAPI dependencies."""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import sqlalchemy as sa
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import extract_bearer_token, verify_and_decode_jwt
from app.db.session import get_db
from app.models.project import Project
from app.models.user import User
from app.services.auth import get_or_sync_user_profile


async def get_token_payload(
    authorization: str | None = Header(None, alias="Authorization"),
) -> dict[str, Any]:
    """FastAPI dependency to extract and cryptographically verify Bearer JWT."""
    token = extract_bearer_token(authorization)
    return verify_and_decode_jwt(token)


async def get_current_user(
    token_payload: dict[str, Any] = Depends(get_token_payload),
    authorization: str | None = Header(None, alias="Authorization"),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Resolve and return the authenticated User profile from the verified JWT sub."""
    access_token = extract_bearer_token(authorization)
    user = await get_or_sync_user_profile(db, token_payload, access_token)
    return user


async def require_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Ensure the authenticated user profile is active."""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )
    return current_user


async def require_superuser(
    current_user: User = Depends(require_active_user),
) -> User:
    """Ensure the authenticated user has platform administrative privileges."""
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator privileges required",
        )
    return current_user


async def get_authenticated_db(
    current_user: User = Depends(require_active_user),
    session: AsyncSession = Depends(get_db),
) -> AsyncGenerator[AsyncSession]:
    """Yield a database session configured with PostgreSQL authenticated session context.

    Propagates `current_user.id` into `request.jwt.claim.sub` so PostgreSQL RLS
    and `auth.uid()` resolve to the authenticated user.

    Security & Connection Pool Guarantees:
    - Scoped to transaction via `set_config(..., true)`.
    - Explicitly resets parameter on return to pool via `RESET request.jwt.claim.sub`.
    - Safe no-op on SQLite unit test databases.
    """
    bind = session.bind
    is_postgres = bind is not None and bind.dialect.name == "postgresql"

    if is_postgres:
        await session.execute(
            sa.text("SELECT set_config('request.jwt.claim.sub', :uid, true)"),
            {"uid": str(current_user.id)},
        )

    try:
        yield session
    finally:
        if is_postgres:
            with contextlib.suppress(Exception):
                # Defensive pool isolation: prevent session identity bleeding
                await session.execute(sa.text("RESET request.jwt.claim.sub"))


async def require_project_access(
    project_id: uuid.UUID,
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_authenticated_db),
) -> Project:
    """Application-level authorization check for project access.

    Verifies:
    1. Project exists.
    2. current_user is the project owner (or is a platform superuser).

    Raises:
        HTTPException(404): If project does not exist.
        HTTPException(403): If authenticated user is not authorized for this project.
    """
    stmt = sa.select(Project).where(Project.id == project_id)
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()

    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    # Authorization guard: owner or superuser
    if project.owner_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You do not have access to this project",
        )

    return project
