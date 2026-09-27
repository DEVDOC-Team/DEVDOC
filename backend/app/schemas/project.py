"""Project schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProjectBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Project human-readable name")
    description: str | None = Field(None, max_length=2000, description="Project description")
    settings_json: str | None = Field(None, description="Opaque settings JSON string")


class ProjectCreate(ProjectBase):
    slug: str | None = Field(
        None,
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
        description="URL-friendly slug (auto-generated from name if omitted)",
    )

    model_config = ConfigDict(extra="forbid")


class ProjectUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=2000)
    settings_json: str | None = None
    is_active: bool | None = None

    model_config = ConfigDict(extra="forbid")


class ProjectResponse(ProjectBase):
    id: uuid.UUID
    slug: str
    owner_id: uuid.UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProjectListResponse(BaseModel):
    items: list[ProjectResponse]
    total: int
    limit: int
    offset: int


class ProjectDeleteResponse(BaseModel):
    success: bool
    message: str
    project_id: uuid.UUID
