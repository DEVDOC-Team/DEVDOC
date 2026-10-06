"""Strict Phase 18 approval request and review contracts."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.approval import ApprovalDecision, ApprovalStatus
from orchestrator.fixes.models import FixProposal
from orchestrator.rca.models import RootCauseAnalysis
from orchestrator.sandbox.models import VerificationStatus


class ApprovalRequestCreate(BaseModel):
    proposal_id: uuid.UUID

    model_config = ConfigDict(extra="forbid")


class ApprovalDecisionInput(BaseModel):
    reason: str = Field(min_length=8, max_length=2_000)

    @field_validator("reason")
    @classmethod
    def reason_must_be_meaningful(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 8:
            raise ValueError("Decision reason must contain at least 8 non-whitespace characters")
        return normalized

    model_config = ConfigDict(extra="forbid")


class VerificationStepReview(BaseModel):
    step_id: str
    description: str
    status: str
    exit_code: int | None
    duration_ms: float
    expected_result: str
    observed_result: str

    model_config = ConfigDict(extra="forbid")


class VerificationReview(BaseModel):
    verification_id: uuid.UUID
    investigation_id: uuid.UUID
    proposal_id: uuid.UUID
    status: VerificationStatus
    started_at: datetime
    completed_at: datetime
    verification_steps: list[VerificationStepReview]
    passed_steps: int
    failed_steps: int
    risk_findings: list[str]
    cleanup_status: str
    summary: str

    model_config = ConfigDict(extra="forbid")


class ApprovalReview(BaseModel):
    root_cause: RootCauseAnalysis
    proposal: FixProposal
    verification: VerificationReview

    model_config = ConfigDict(extra="forbid")


class ApprovalResponse(BaseModel):
    id: uuid.UUID
    fix_proposal_id: uuid.UUID
    verification_id: uuid.UUID | None
    status: ApprovalStatus
    requested_by_id: uuid.UUID
    approver_id: uuid.UUID | None
    decision: ApprovalDecision | None
    rationale: str | None
    requested_at: datetime
    decided_at: datetime | None
    expires_at: datetime | None
    proposal_fingerprint: str | None
    verification_fingerprint: str | None
    review: ApprovalReview | None

    model_config = ConfigDict(from_attributes=True)


class ApprovalListResponse(BaseModel):
    items: list[ApprovalResponse]
    total: int


class ApprovalAuditEvent(BaseModel):
    id: uuid.UUID
    actor_id: uuid.UUID | None
    action: str
    description: str | None
    outcome: str | None
    request_id: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ApprovalAuditListResponse(BaseModel):
    items: list[ApprovalAuditEvent]
    total: int
    limit: int
    offset: int
