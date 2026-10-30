"""Investigation Pydantic schemas.

Provides strict request and response validation for Investigation API.
Enforces extra="forbid" on all write models to eliminate spoofing and unintended fields.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.investigation import InvestigationStatus


class InvestigationBase(BaseModel):
    """Base fields for investigation models."""

    summary: str | None = Field(None, max_length=10000, description="Investigation objective or hypothesis summary")


class InvestigationCreate(InvestigationBase):
    """Schema for initiating an investigation within an incident."""

    status: InvestigationStatus = Field(InvestigationStatus.PENDING, description="Initial investigation status")

    @field_validator("status", mode="before")
    @classmethod
    def parse_status(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.lower()
        return v

    @field_validator("status")
    @classmethod
    def validate_initial_status(cls, v: InvestigationStatus) -> InvestigationStatus:
        if v not in (InvestigationStatus.PENDING, InvestigationStatus.RUNNING):
            raise ValueError("New investigations must start in PENDING or RUNNING status")
        return v

    model_config = ConfigDict(extra="forbid")


class InvestigationUpdate(BaseModel):
    """Schema for updating mutable investigation fields."""

    summary: str | None = Field(None, max_length=10000)
    error_message: str | None = Field(None, max_length=5000)
    status: InvestigationStatus | None = None

    @field_validator("status", mode="before")
    @classmethod
    def parse_status(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.lower()
        return v

    model_config = ConfigDict(extra="forbid")


class InvestigationStatusUpdate(BaseModel):
    """Schema for dedicated lifecycle status transition endpoint."""

    status: InvestigationStatus = Field(..., description="Target lifecycle status")
    error_message: str | None = Field(None, max_length=5000, description="Failure reason if status is FAILED")

    @field_validator("status", mode="before")
    @classmethod
    def parse_status(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.lower()
        return v

    model_config = ConfigDict(extra="forbid")


class InvestigationResponse(BaseModel):
    """Normalized investigation API representation."""

    id: uuid.UUID
    project_id: uuid.UUID
    incident_id: uuid.UUID
    initiated_by_id: uuid.UUID | None = None
    status: InvestigationStatus
    summary: str | None = None
    tokens_used: int = 0
    estimated_cost_usd: int = 0
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class InvestigationListResponse(BaseModel):
    """Paginated list of investigations."""

    items: list[InvestigationResponse]
    total: int
    limit: int
    offset: int


class InvestigationDeleteResponse(BaseModel):
    """Response returned upon successful investigation deletion."""

    success: bool = True
    message: str = "Investigation deleted successfully"
    investigation_id: uuid.UUID


class InvestigationRunResponse(InvestigationResponse):
    """Response returned upon running an investigation orchestration."""

    evidence_count: int = 0
    has_root_cause_analysis: bool = False
    has_fix_proposal: bool = False
    approval_artifact_id: uuid.UUID | None = None
    approval_status: str | None = None


class InvestigationCancelResponse(BaseModel):
    """Result of requesting cancellation for an active investigation."""

    success: bool = True
    status: InvestigationStatus = InvestigationStatus.CANCELLED
    cancellation_requested: bool = True
    message: str = "Investigation stop requested."

