"""Incident Pydantic schemas.

Provides strict request and response validation for Incident Management.
Enforces extra="forbid" on all write models to eliminate spoofing and unintended fields.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.incident import IncidentSeverity, IncidentSource, IncidentStatus


class IncidentBase(BaseModel):
    """Base fields for incident models."""

    title: str = Field(..., min_length=1, max_length=512, description="Short incident summary")
    description: str | None = Field(None, max_length=10000, description="Detailed incident description")
    severity: IncidentSeverity = Field(IncidentSeverity.MEDIUM, description="Incident severity level")
    source: IncidentSource = Field(IncidentSource.MANUAL, description="Incident reporting origin")
    external_reference: str | None = Field(None, max_length=256, description="External ticket or alert ID")
    repository_id: uuid.UUID | None = Field(None, description="Optional associated repository ID")
    affected_users: int = Field(0, ge=0, description="Estimated number of affected users")

    @field_validator("severity", mode="before")
    @classmethod
    def parse_severity(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.lower()
        return v

    @field_validator("source", mode="before")
    @classmethod
    def parse_source(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.lower()
        return v


class IncidentCreate(IncidentBase):
    """Schema for creating a new incident within a project."""

    status: IncidentStatus = Field(IncidentStatus.OPEN, description="Initial incident status")
    detected_at: datetime | None = Field(None, description="Optional historical detection timestamp")

    @field_validator("status", mode="before")
    @classmethod
    def parse_status(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.lower()
        return v

    @field_validator("status")
    @classmethod
    def validate_initial_status(cls, v: IncidentStatus) -> IncidentStatus:
        if v not in (IncidentStatus.OPEN, IncidentStatus.INVESTIGATING):
            raise ValueError("New incidents must start in OPEN or INVESTIGATING status")
        return v

    model_config = ConfigDict(extra="forbid")


class IncidentUpdate(BaseModel):
    """Schema for updating mutable incident fields."""

    title: str | None = Field(None, min_length=1, max_length=512)
    description: str | None = Field(None, max_length=10000)
    severity: IncidentSeverity | None = None
    status: IncidentStatus | None = None
    source: IncidentSource | None = None
    external_reference: str | None = Field(None, max_length=256)
    repository_id: uuid.UUID | None = None
    affected_users: int | None = Field(None, ge=0)

    @field_validator("severity", mode="before")
    @classmethod
    def parse_severity(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.lower()
        return v

    @field_validator("status", mode="before")
    @classmethod
    def parse_status(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.lower()
        return v

    @field_validator("source", mode="before")
    @classmethod
    def parse_source(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.lower()
        return v

    model_config = ConfigDict(extra="forbid")


class IncidentStatusUpdate(BaseModel):
    """Schema for dedicated status transition endpoint."""

    status: IncidentStatus = Field(..., description="Target lifecycle status")

    @field_validator("status", mode="before")
    @classmethod
    def parse_status(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.lower()
        return v

    model_config = ConfigDict(extra="forbid")


class IncidentResponse(BaseModel):
    """Normalized incident API representation."""

    id: uuid.UUID
    project_id: uuid.UUID
    repository_id: uuid.UUID | None = None
    reported_by_id: uuid.UUID | None = None
    title: str
    description: str | None = None
    severity: IncidentSeverity
    status: IncidentStatus
    source: IncidentSource
    external_reference: str | None = None
    affected_users: int = 0
    detected_at: datetime
    resolved_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class IncidentListResponse(BaseModel):
    """Paginated list of incidents."""

    items: list[IncidentResponse]
    total: int
    limit: int
    offset: int


class IncidentDeleteResponse(BaseModel):
    """Response returned upon successful incident deletion."""

    success: bool = True
    message: str = "Incident deleted successfully"
    incident_id: uuid.UUID
