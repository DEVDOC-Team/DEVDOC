"""Typed, evidence-referenced root-cause analysis contracts."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from orchestrator.llm.contracts import LLMObservability


class RCAStatus(str, enum.Enum):
    ROOT_CAUSE_IDENTIFIED = "root_cause_identified"
    MULTIPLE_PLAUSIBLE_CAUSES = "multiple_plausible_causes"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class RCAConfidence(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RCACategory(str, enum.Enum):
    CODE_DEFECT = "code_defect"
    CONFIGURATION = "configuration"
    DEPENDENCY = "dependency"
    INFRASTRUCTURE = "infrastructure"
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    NETWORK = "network"
    DATABASE = "database"
    DEPLOYMENT = "deployment"
    AUTHENTICATION = "authentication"
    EXTERNAL_SERVICE = "external_service"
    HUMAN_CHANGE = "human_change"
    UNKNOWN = "unknown"


class EvidenceClassification(str, enum.Enum):
    FACT = "fact"
    EXTERNAL_KNOWLEDGE = "external_knowledge"


class RCAEvidenceReference(BaseModel):
    """Evidence reference whose identity and classification come from Phase 12."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: uuid.UUID
    classification: EvidenceClassification
    source: str = Field(min_length=1, max_length=256)
    evidence_type: str = Field(min_length=1, max_length=128)
    timestamp: datetime
    source_url: str | None = Field(default=None, max_length=2_048)
    title: str = Field(min_length=1, max_length=2_048)
    summary: str = Field(max_length=4_096)


class RCAClaim(BaseModel):
    """A hypothesis-chain claim with explicit links to actual evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    statement: str = Field(min_length=1, max_length=1_000)
    evidence_references: list[RCAEvidenceReference] = Field(min_length=1, max_length=20)


class CandidateRootCause(BaseModel):
    """A ranked candidate; its confidence is assigned by deterministic rules."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_id: uuid.UUID
    classification: Literal["hypothesis"] = "hypothesis"
    statement: str = Field(min_length=1, max_length=2_000)
    category: RCACategory
    confidence: RCAConfidence
    rank: int = Field(ge=1, le=8)
    supporting_evidence: list[RCAEvidenceReference] = Field(min_length=1, max_length=20)
    contradicting_evidence: list[RCAEvidenceReference] = Field(max_length=20)
    contributing_factors: list[RCAClaim] = Field(max_length=10)
    triggering_events: list[RCAClaim] = Field(max_length=10)
    observed_symptoms: list[RCAClaim] = Field(max_length=10)
    temporal_relationship_ids: list[str] = Field(max_length=20)
    uncertainty: str = Field(min_length=1, max_length=2_000)
    rationale: str = Field(min_length=1, max_length=4_000)
    ranking_basis: str = Field(min_length=1, max_length=1_000)


class RootCauseAnalysis(BaseModel):
    """One immutable result value; later analyses do not mutate evidence or prior results."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    analysis_id: uuid.UUID
    investigation_id: uuid.UUID
    execution_id: uuid.UUID
    status: RCAStatus
    candidates: list[CandidateRootCause] = Field(max_length=8)
    selected_root_cause: CandidateRootCause | None = None
    confidence: RCAConfidence
    observed_facts: list[RCAEvidenceReference] = Field(max_length=100)
    reasoning_summary_evidence: list[RCAEvidenceReference] = Field(max_length=20)
    evidence_references: list[RCAEvidenceReference] = Field(max_length=100)
    contradictions: list[RCAEvidenceReference] = Field(max_length=100)
    uncertainties: list[str] = Field(max_length=20)
    missing_information: list[str] = Field(max_length=20)
    reasoning_summary: str = Field(min_length=1, max_length=4_000)
    analyzed_at: datetime
    model_metadata: LLMObservability | None = None


class RCAClaimOutput(BaseModel):
    """Untrusted model claim; references are checked before making a public RCA claim."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    statement: str = Field(min_length=1, max_length=1_000)
    evidence_ids: list[uuid.UUID] = Field(min_length=1, max_length=20)


class RCACandidateOutput(BaseModel):
    """Untrusted candidate data returned by the existing LLM provider."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    statement: str = Field(min_length=1, max_length=2_000)
    category: RCACategory
    supporting_evidence_ids: list[uuid.UUID] = Field(min_length=1, max_length=20)
    contradicting_evidence_ids: list[uuid.UUID] = Field(max_length=20)
    contributing_factors: list[RCAClaimOutput] = Field(max_length=10)
    triggering_events: list[RCAClaimOutput] = Field(max_length=10)
    observed_symptoms: list[RCAClaimOutput] = Field(max_length=10)
    temporal_relationship_ids: list[str] = Field(max_length=20)
    uncertainty: str = Field(min_length=1, max_length=2_000)
    rationale: str = Field(min_length=1, max_length=4_000)


class RCACompletion(BaseModel):
    """Strict output schema expected from the model; root cause selection is local."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidates: list[RCACandidateOutput] = Field(max_length=8)
    reasoning_summary: str = Field(min_length=1, max_length=4_000)
    reasoning_summary_evidence_ids: list[uuid.UUID] = Field(min_length=1, max_length=20)
    uncertainties: list[str] = Field(max_length=20)
    missing_information: list[str] = Field(max_length=20)
