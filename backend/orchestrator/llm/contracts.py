"""Strict request and response contracts for evidence-grounded LLM reasoning."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from orchestrator.core.sanitizer import sanitize_data, sanitize_string
from orchestrator.evidence.models import EvidenceCollection


class LLMEvidence(BaseModel):
    """Bounded, sanitized subset of an evidence item sent to an LLM provider."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: uuid.UUID
    source: str = Field(max_length=256)
    evidence_type: str = Field(max_length=128)
    timestamp: datetime
    title: str = Field(max_length=2_048)
    summary: str = Field(max_length=4_096)
    data: dict[str, Any]
    correlation_identifiers: list[str] = Field(max_length=100)


class EvidenceSet(BaseModel):
    """Structured Phase 12 evidence payload supplied to Phase 13 reasoning."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    investigation_id: uuid.UUID
    execution_id: uuid.UUID
    evidence: list[LLMEvidence] = Field(max_length=500)

    @classmethod
    def from_collection(cls, collection: EvidenceCollection, *, max_items: int) -> EvidenceSet:
        if max_items <= 0:
            raise ValueError("max_items must be positive")
        return cls(
            investigation_id=collection.investigation_id,
            execution_id=collection.execution_id,
            evidence=[
                LLMEvidence(
                    evidence_id=item.evidence_id,
                    source=item.source,
                    evidence_type=item.evidence_type.value,
                    timestamp=item.timestamp,
                    title=sanitize_string(item.title),
                    summary=sanitize_string(item.summary),
                    data=sanitize_data(item.data),
                    correlation_identifiers=[
                        sanitize_string(value) for value in item.correlation_identifiers
                    ],
                )
                for item in collection.items[:max_items]
            ],
        )


class ReasoningObservation(BaseModel):
    """Evidence-grounded observation; it is not a causal diagnosis."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str = Field(min_length=1, max_length=2_000)
    evidence_ids: list[uuid.UUID] = Field(min_length=1, max_length=20)


class StructuredReasoning(BaseModel):
    """Nemotron's structured reasoning output, intentionally short of root cause."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    summary: str = Field(min_length=1, max_length=4_000)
    observations: list[ReasoningObservation] = Field(max_length=30)
    uncertainties: list[str] = Field(max_length=30)
    follow_up_questions: list[str] = Field(max_length=20)


class LLMObservability(BaseModel):
    """Safe operational metadata; never contains prompts, evidence, or credentials."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str = "nebius"
    model: str
    request_id: str | None = None
    duration_ms: float = Field(ge=0)
    attempts: int = Field(ge=0, le=3)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    estimated_cost_usd: float = Field(ge=0)
    budget_remaining_usd: float = Field(ge=0)
    cache_hit: bool = False


class ReasoningResponse(BaseModel):
    """Validated reasoning result and its token/cost observability metadata."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    reasoning: StructuredReasoning
    metadata: LLMObservability


class ProviderCompletion(BaseModel):
    """Normalized completion returned by an LLM provider adapter."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    content: str
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    request_id: str | None = None
    model: str | None = None
