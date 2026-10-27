"""Typed request, result, document, and provenance contracts for knowledge search."""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SearchIntent(str, enum.Enum):
    DOCUMENTATION = "documentation"
    ERROR_REFERENCE = "error_reference"
    KNOWN_ISSUE = "known_issue"
    CONFIGURATION = "configuration"
    COMPATIBILITY = "compatibility"
    TROUBLESHOOTING = "troubleshooting"
    GENERAL_TECHNICAL = "general_technical"


class KnowledgeSearchRequest(BaseModel):
    """A single bounded search, scoped to one project and investigation execution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: uuid.UUID
    investigation_id: uuid.UUID
    execution_id: uuid.UUID
    intent: SearchIntent
    query: str = Field(min_length=1, max_length=1_000)


class KnowledgeProvenance(BaseModel):
    """Source attribution for content returned by an external provider."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    original_url: str = Field(min_length=8, max_length=4_096)
    source_domain: str = Field(min_length=1, max_length=253)
    provider: str = Field(min_length=1, max_length=64)
    search_query: str = Field(min_length=1, max_length=1_000)
    retrieved_at: datetime


class KnowledgeDocument(BaseModel):
    """A normalized web result, explicitly classified as untrusted external data."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str = Field(min_length=1, max_length=2_048)
    url: str = Field(min_length=8, max_length=4_096)
    snippet: str = Field(min_length=1, max_length=8_000)
    source_domain: str = Field(min_length=1, max_length=253)
    published_at: str | None = Field(default=None, max_length=128)
    relevance_score: float | None = Field(default=None, ge=0, le=1)
    provenance: KnowledgeProvenance
    trust_classification: Literal["untrusted_external"] = "untrusted_external"


class KnowledgeSearchMetadata(BaseModel):
    """Provider-safe usage metadata; does not estimate or fabricate monetary cost."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    duration_ms: float = Field(ge=0)
    attempts: int = Field(ge=1, le=3)
    cache_hit: bool = False
    provider_response_time_seconds: float | None = Field(default=None, ge=0)


class KnowledgeSearchResult(BaseModel):
    """Normalized result of a single external knowledge search."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    query: str = Field(min_length=1, max_length=1_000)
    provider: str = Field(min_length=1, max_length=64)
    results: list[KnowledgeDocument] = Field(max_length=10)
    searched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    total_results: int = Field(ge=0, le=10)
    metadata: KnowledgeSearchMetadata


class ProviderSearchItem(BaseModel):
    """Small allow-listed subset of a provider's search-result schema."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    title: str
    url: str
    content: str
    published_date: str | None = None
    score: float | None = None


class ProviderSearchResponse(BaseModel):
    """Normalized Tavily API response fields before content normalization."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    results: list[ProviderSearchItem] = Field(max_length=20)
    response_time: float | None = Field(default=None, ge=0)
    response_size_bytes: int = Field(default=0, ge=0)
