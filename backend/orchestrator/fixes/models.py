"""Typed Phase 16 proposal and model-completion contracts."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from orchestrator.llm.contracts import LLMObservability


class FixChangeType(str, enum.Enum):
    CODE_CHANGE = "code_change"
    CONFIGURATION_CHANGE = "configuration_change"
    DEPENDENCY_CHANGE = "dependency_change"
    INFRASTRUCTURE_CHANGE = "infrastructure_change"
    DEPLOYMENT_CHANGE = "deployment_change"
    DATABASE_CHANGE = "database_change"
    MONITORING_CHANGE = "monitoring_change"
    ROLLBACK = "rollback"
    DOCUMENTATION_CHANGE = "documentation_change"
    UNKNOWN = "unknown"


class FixRiskCategory(str, enum.Enum):
    DATA_LOSS = "data_loss"
    DOWNTIME = "downtime"
    SECURITY = "security"
    COMPATIBILITY = "compatibility"
    PERFORMANCE = "performance"
    REGRESSION = "regression"
    MIGRATION = "migration"
    DEPENDENCY = "dependency"
    INFRASTRUCTURE = "infrastructure"
    UNKNOWN = "unknown"


class FixRiskSeverity(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class FixProposalStatus(str, enum.Enum):
    PROPOSED = "proposed"
    REQUIRES_HUMAN_REVIEW = "requires_human_review"


class FixGenerationStatus(str, enum.Enum):
    PROPOSED = "proposed"
    REQUIRES_HUMAN_REVIEW = "requires_human_review"
    UNSAFE = "unsafe"
    INSUFFICIENT_INFORMATION = "insufficient_information"
    CANCELLED = "cancelled"


class FixChange(BaseModel):
    """An inert, reviewable change description; patches are data, never applied here."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    target: str = Field(min_length=1, max_length=512)
    target_path: str | None = Field(default=None, max_length=512)
    operation: str = Field(min_length=1, max_length=256)
    current_state: str | None = Field(default=None, max_length=4_000)
    proposed_state: str | None = Field(default=None, max_length=4_000)
    proposed_diff: str | None = Field(default=None, max_length=20_000)
    patch_status: Literal["PROPOSED / UNVERIFIED"] | None = "PROPOSED / UNVERIFIED"
    reason: str = Field(min_length=1, max_length=2_000)
    evidence_references: list[uuid.UUID] = Field(min_length=1, max_length=20)
    tests_required: list[str] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def require_proposed_state(self) -> FixChange:
        if self.proposed_state is None and self.proposed_diff is None:
            raise ValueError("A change must include a proposed state or proposed diff")
        return self


class FixRisk(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    category: FixRiskCategory
    severity: FixRiskSeverity
    description: str = Field(min_length=1, max_length=2_000)
    mitigation: str = Field(min_length=1, max_length=2_000)


class FixVerificationStep(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    description: str = Field(min_length=1, max_length=2_000)
    expected_result: str = Field(min_length=1, max_length=2_000)
    evidence_required: list[str] = Field(min_length=1, max_length=10)


class FixRollbackStep(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    description: str = Field(min_length=1, max_length=2_000)
    trigger: str = Field(min_length=1, max_length=1_000)
    expected_result: str = Field(min_length=1, max_length=2_000)


class FixCompletion(BaseModel):
    """Untrusted structured content returned by the existing Phase 13 LLM service."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    root_cause_reference: uuid.UUID
    summary: str = Field(min_length=1, max_length=2_000)
    rationale: str = Field(min_length=1, max_length=4_000)
    affected_components: list[str] = Field(min_length=1, max_length=5)
    change_type: FixChangeType
    changes: list[FixChange] = Field(min_length=1, max_length=3)
    prerequisites: list[str] = Field(max_length=20)
    risks: list[FixRisk] = Field(min_length=1, max_length=10)
    verification_plan: list[FixVerificationStep] = Field(min_length=1, max_length=20)
    rollback_plan: list[FixRollbackStep] = Field(min_length=1, max_length=20)
    evidence_references: list[uuid.UUID] = Field(min_length=1, max_length=100)
    external_knowledge_references: list[uuid.UUID] = Field(max_length=20)
    confidence: float = Field(ge=0, le=1)
    change_scope: str = Field(min_length=1, max_length=1_000)


class FixProposal(BaseModel):
    """Validated proposal for later sandbox evaluation and explicit human review."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    proposal_id: uuid.UUID
    investigation_id: uuid.UUID
    execution_id: uuid.UUID
    root_cause_reference: uuid.UUID
    status: FixProposalStatus
    summary: str = Field(min_length=1, max_length=2_000)
    rationale: str = Field(min_length=1, max_length=4_000)
    affected_components: list[str] = Field(min_length=1, max_length=5)
    change_type: FixChangeType
    changes: list[FixChange] = Field(min_length=1, max_length=3)
    prerequisites: list[str] = Field(max_length=20)
    risks: list[FixRisk] = Field(min_length=1, max_length=10)
    verification_plan: list[FixVerificationStep] = Field(min_length=1, max_length=20)
    rollback_plan: list[FixRollbackStep] = Field(min_length=1, max_length=20)
    evidence_references: list[uuid.UUID] = Field(min_length=1, max_length=100)
    external_knowledge_references: list[uuid.UUID] = Field(max_length=20)
    confidence: float = Field(ge=0, le=1)
    change_scope: str = Field(min_length=1, max_length=1_000)
    human_approval_required: Literal[True] = True
    generated_at: datetime
    model_metadata: LLMObservability


class FixGenerationResult(BaseModel):
    """Controlled Phase 16 outcome; non-proposal statuses never carry proposal content."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: FixGenerationStatus
    proposal: FixProposal | None = None
    reason: str | None = Field(default=None, max_length=512)

    @model_validator(mode="after")
    def validate_result_status(self) -> FixGenerationResult:
        has_proposal_status = self.status in {
            FixGenerationStatus.PROPOSED,
            FixGenerationStatus.REQUIRES_HUMAN_REVIEW,
        }
        if has_proposal_status != (self.proposal is not None):
            raise ValueError("Only proposal statuses may contain a proposal")
        if self.proposal is not None and self.proposal.status.value != self.status.value:
            raise ValueError("Generation and proposal statuses must match")
        if not has_proposal_status and self.reason is None:
            raise ValueError("A no-proposal result must include a reason")
        return self
