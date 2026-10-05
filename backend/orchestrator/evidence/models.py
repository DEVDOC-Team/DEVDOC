"""Evidence data models and taxonomy.

Defines strongly typed, timezone-aware UTC evidence representation for investigation runs.
Includes provenance tracking, quality indicators (completeness and timestamp certainty),
deduplication keys, correlation relationships, timeline events, and summaries.
Strictly excludes root-cause confidence or diagnostic conclusions.
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


class EvidenceSource(str, enum.Enum):
    """Originating operational provider or agent source."""

    GITHUB = "github"
    DOCKER = "docker"
    MONITORING = "monitoring"
    EXTERNAL_KNOWLEDGE = "external_knowledge"
    GENERIC = "generic"
    UNKNOWN = "unknown"


class EvidenceType(str, enum.Enum):
    """Taxonomy of evidence types collected across operational domains."""

    # GitHub operational evidence
    REPOSITORY = "repository"
    COMMIT = "commit"
    PULL_REQUEST = "pull_request"
    ISSUE = "issue"
    WORKFLOW_RUN = "workflow_run"
    FILE_CONTENT = "file_content"

    # Docker operational evidence
    CONTAINER = "container"
    CONTAINER_STATE = "container_state"
    CONTAINER_LOG = "container_log"
    IMAGE = "image"

    # Monitoring operational evidence
    SERVICE_HEALTH = "service_health"
    METRIC = "metric"
    ALERT = "alert"

    # External technical references. This is not observed incident fact.
    EXTERNAL_KNOWLEDGE = "external_knowledge"

    # Generic fallback
    GENERIC = "generic"
    UNKNOWN = "unknown"


class TimestampType(str, enum.Enum):
    """Categorization of evidence timestamp origin."""

    EVENT = "event"  # Original timestamp when the event occurred in the provider
    COLLECTION = "collection"  # Timestamp when the agent collected the operational record
    FALLBACK = "fallback"  # Deterministic fallback when the source provided no timestamp


class ValidationStatus(str, enum.Enum):
    """Integrity and structural validation status of an evidence item."""

    VALID = "valid"
    WARNING = "warning"
    INVALID = "invalid"


class SourceReliability(str, enum.Enum):
    """Reliability tier of the originating evidence source."""

    AUTHORITATIVE = "authoritative"  # e.g. Git commit SHAs, immutable VCS history
    HIGH = "high"  # e.g. direct Docker Engine inspect data, firing alerts
    MEDIUM = "medium"  # e.g. sampled telemetry, log streams
    LOW = "low"  # e.g. partial or fallback data


@dataclass
class EvidenceProvenance:
    """Provenance audit metadata identifying where, when, and how evidence was collected."""

    agent_id: str
    source: str
    collected_at: datetime
    source_reference: str | None = None
    original_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "source": self.source,
            "collected_at": self.collected_at.isoformat(),
            "source_reference": self.source_reference,
            "original_id": self.original_id,
            "metadata": dict(self.metadata),
        }


@dataclass
class EvidenceQuality:
    """Quality and completeness metadata for an evidence item.

    NOTE: This measures data completeness and timestamp fidelity only.
    It does NOT represent root-cause diagnosis confidence or fix certainty.
    """

    source_reliability: SourceReliability = SourceReliability.HIGH
    completeness: float = 1.0  # Ratio from 0.0 to 1.0 of required fields present
    timestamp_quality: TimestampType = TimestampType.EVENT
    validation_status: ValidationStatus = ValidationStatus.VALID
    quality_score: float = 1.0  # Deterministic composite score (0.0 - 1.0) of completeness & timestamp quality

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_reliability": self.source_reliability.value,
            "completeness": self.completeness,
            "timestamp_quality": self.timestamp_quality.value,
            "validation_status": self.validation_status.value,
            "quality_score": self.quality_score,
        }


@dataclass
class Evidence:
    """Strongly typed normalized investigation evidence item.

    Captures an atomic piece of operational telemetry, configuration, or source state
    with immutable identifiers, UTC timestamp, provenance, and correlation coordinates.
    """

    investigation_id: uuid.UUID
    execution_id: uuid.UUID
    source: str
    source_type: EvidenceSource
    evidence_type: EvidenceType
    timestamp: datetime  # Timezone-aware UTC timestamp
    title: str
    provenance: EvidenceProvenance
    evidence_id: uuid.UUID = field(default_factory=uuid.uuid4)
    timestamp_type: TimestampType = TimestampType.EVENT
    summary: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    quality: EvidenceQuality = field(default_factory=EvidenceQuality)
    correlation_identifiers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    collection_metadata: dict[str, Any] = field(default_factory=dict)
    dedup_key: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": str(self.evidence_id),
            "investigation_id": str(self.investigation_id),
            "execution_id": str(self.execution_id),
            "source": self.source,
            "source_type": self.source_type.value,
            "evidence_type": self.evidence_type.value,
            "timestamp": self.timestamp.isoformat(),
            "timestamp_type": self.timestamp_type.value,
            "title": self.title,
            "summary": self.summary,
            "data": dict(self.data),
            "provenance": self.provenance.to_dict(),
            "quality": self.quality.to_dict(),
            "correlation_identifiers": list(self.correlation_identifiers),
            "warnings": list(self.warnings),
            "collection_metadata": dict(self.collection_metadata),
            "dedup_key": self.dedup_key,
        }


@dataclass
class TimelineEvent:
    """Chronologically sorted event entry on the investigation timeline."""

    timestamp: datetime
    evidence_id: uuid.UUID
    source: str
    evidence_type: str
    title: str
    summary: str
    correlation_identifiers: list[str] = field(default_factory=list)
    timestamp_type: str = "event"

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "evidence_id": str(self.evidence_id),
            "source": self.source,
            "evidence_type": self.evidence_type,
            "title": self.title,
            "summary": self.summary,
            "correlation_identifiers": list(self.correlation_identifiers),
            "timestamp_type": self.timestamp_type,
        }


@dataclass
class CorrelationRelationship:
    """Explicit correlation link between two evidence items.

    CRITICAL BOUNDARY: Correlation is NOT causality.
    This links items that share explicit identifiers (e.g. repo, container, service)
    or occurred within a configured temporal proximity window.
    """

    relationship_id: str
    source_evidence_id: uuid.UUID
    target_evidence_id: uuid.UUID
    relationship_type: str  # e.g. "shares_identifier:repo", "shares_identifier:service", "temporal_proximity"
    shared_identifier: str | None = None
    time_delta_seconds: float | None = None
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "relationship_id": self.relationship_id,
            "source_evidence_id": str(self.source_evidence_id),
            "target_evidence_id": str(self.target_evidence_id),
            "relationship_type": self.relationship_type,
            "shared_identifier": self.shared_identifier,
            "time_delta_seconds": self.time_delta_seconds,
            "description": self.description,
        }


@dataclass
class EvidenceSummary:
    """Descriptive statistics and summary of the normalized evidence set."""

    total_evidence_count: int = 0
    counts_by_source: dict[str, int] = field(default_factory=dict)
    counts_by_type: dict[str, int] = field(default_factory=dict)
    earliest_timestamp: datetime | None = None
    latest_timestamp: datetime | None = None
    validation_failure_count: int = 0
    duplicate_count: int = 0
    correlation_count: int = 0
    warning_count: int = 0
    sources_present: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_evidence_count": self.total_evidence_count,
            "counts_by_source": dict(self.counts_by_source),
            "counts_by_type": dict(self.counts_by_type),
            "earliest_timestamp": self.earliest_timestamp.isoformat() if self.earliest_timestamp else None,
            "latest_timestamp": self.latest_timestamp.isoformat() if self.latest_timestamp else None,
            "validation_failure_count": self.validation_failure_count,
            "duplicate_count": self.duplicate_count,
            "correlation_count": self.correlation_count,
            "warning_count": self.warning_count,
            "sources_present": list(self.sources_present),
        }


@dataclass
class EvidenceCollection:
    """Full container for all processed, validated, deduplicated, and correlated evidence."""

    investigation_id: uuid.UUID
    execution_id: uuid.UUID
    items: list[Evidence] = field(default_factory=list)
    timeline: list[TimelineEvent] = field(default_factory=list)
    correlations: list[CorrelationRelationship] = field(default_factory=list)
    summary: EvidenceSummary = field(default_factory=EvidenceSummary)
    groups_by_source: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    groups_by_type: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "investigation_id": str(self.investigation_id),
            "execution_id": str(self.execution_id),
            "evidence_count": len(self.items),
            "items": [item.to_dict() for item in self.items],
            "timeline": [t.to_dict() for t in self.timeline],
            "correlations": [c.to_dict() for c in self.correlations],
            "summary": self.summary.to_dict(),
            "groups_by_source": self.groups_by_source,
            "groups_by_type": self.groups_by_type,
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
        }
