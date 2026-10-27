"""DEVDOC Evidence Engine package.

Transforms structured operational outputs from Phase 11 operational agents (GitHub, Docker, Monitoring)
into a normalized, validated, timestamped, deduplicated, and correlated investigation evidence set.
Strictly separated from root-cause reasoning (Phase 15) and LLM inference (Phase 13).
"""

from __future__ import annotations

from orchestrator.evidence.config import (
    EvidenceCorrelationConfig,
    EvidenceEngineConfig,
    EvidenceLimitsConfig,
)
from orchestrator.evidence.engine import EvidenceEngine
from orchestrator.evidence.models import (
    CorrelationRelationship,
    Evidence,
    EvidenceCollection,
    EvidenceProvenance,
    EvidenceQuality,
    EvidenceSource,
    EvidenceSummary,
    EvidenceType,
    SourceReliability,
    TimelineEvent,
    TimestampType,
    ValidationStatus,
)

__all__ = [
    "CorrelationRelationship",
    "Evidence",
    "EvidenceCollection",
    "EvidenceCorrelationConfig",
    "EvidenceEngine",
    "EvidenceEngineConfig",
    "EvidenceLimitsConfig",
    "EvidenceProvenance",
    "EvidenceQuality",
    "EvidenceSource",
    "EvidenceSummary",
    "EvidenceType",
    "SourceReliability",
    "TimelineEvent",
    "TimestampType",
    "ValidationStatus",
]
