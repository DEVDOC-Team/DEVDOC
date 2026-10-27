"""User schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class UserBase(BaseModel):
    email: str
    full_name: str | None = None
    avatar_url: str | None = None


class UserResponse(UserBase):
    id: uuid.UUID
    is_active: bool
    is_superuser: bool
    provider: str | None = None
    provider_user_id: str | None = None
    last_sign_in_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserUpdate(BaseModel):
    full_name: str | None = None
    avatar_url: str | None = None

    model_config = ConfigDict(extra="forbid")


class UserDeactivateResponse(BaseModel):
    success: bool
    message: str
    user_id: uuid.UUID

