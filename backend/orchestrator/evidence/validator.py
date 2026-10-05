"""Evidence validation logic.

Validates structural integrity, timezone invariants, required identifiers,
and payload bounds for normalized evidence items. Calculates completeness
and evidence data quality scores (strictly data quality, not root-cause confidence).
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from orchestrator.evidence.config import EvidenceLimitsConfig
from orchestrator.evidence.models import (
    Evidence,
    EvidenceQuality,
    SourceReliability,
    TimestampType,
    ValidationStatus,
)


class EvidenceValidator:
    """Validates normalized evidence items against structural and quality invariants."""

    def __init__(self, limits: EvidenceLimitsConfig | None = None) -> None:
        self.limits = limits if limits is not None else EvidenceLimitsConfig()

    def validate(self, evidence: Evidence) -> tuple[bool, list[str]]:
        """Validate an individual evidence item.

        Updates the evidence.quality metadata in place and returns (is_valid, validation_warnings).
        """
        warnings: list[str] = []
        is_invalid = False

        # 1. Validate UUIDs
        if not isinstance(evidence.evidence_id, uuid.UUID):
            warnings.append(f"Invalid evidence_id: expected UUID, got {type(evidence.evidence_id).__name__}")
            is_invalid = True
        if not isinstance(evidence.investigation_id, uuid.UUID):
            warnings.append(f"Invalid investigation_id: expected UUID, got {type(evidence.investigation_id).__name__}")
            is_invalid = True
        if not isinstance(evidence.execution_id, uuid.UUID):
            warnings.append(f"Invalid execution_id: expected UUID, got {type(evidence.execution_id).__name__}")
            is_invalid = True

        # 2. Validate source and type
        if not evidence.source or not isinstance(evidence.source, str):
            warnings.append("Missing or invalid evidence source")
            is_invalid = True

        # 3. Validate timestamp is timezone-aware UTC
        if not isinstance(evidence.timestamp, datetime):
            warnings.append(f"Invalid timestamp: expected datetime, got {type(evidence.timestamp).__name__}")
            is_invalid = True
        else:
            if evidence.timestamp.tzinfo is None:
                warnings.append("Timestamp must be timezone-aware UTC, received naive datetime")
                is_invalid = True
            elif evidence.timestamp.utcoffset() != (UTC.utcoffset(evidence.timestamp) or None):
                # Ensure offset is +00:00
                offset = evidence.timestamp.utcoffset()
                if offset is not None and offset.total_seconds() != 0:
                    warnings.append(f"Timestamp must be UTC (+00:00), received offset {offset}")
                    is_invalid = True

        # 4. Check payload size
        try:
            serialized_len = len(
                json.dumps(evidence.data, default=str, ensure_ascii=False).encode("utf-8")
            )
            if serialized_len > self.limits.max_payload_bytes:
                warnings.append(
                    f"Evidence payload size ({serialized_len} bytes) exceeds maximum "
                    f"limit ({self.limits.max_payload_bytes} bytes)"
                )
                is_invalid = True
        except (TypeError, ValueError, RecursionError) as json_err:
            warnings.append(f"Evidence data could not be serialized to JSON: {json_err}")
            is_invalid = True

        # 5. Compute completeness and quality score
        required_fields = [
            bool(evidence.title),
            bool(evidence.source),
            evidence.provenance is not None,
            bool(evidence.provenance.agent_id),
            evidence.timestamp is not None,
            bool(evidence.correlation_identifiers),
        ]
        present_count = sum(1 for f in required_fields if f)
        completeness = round(present_count / len(required_fields), 2)

        # Quality score based on timestamp certainty and completeness
        ts_factor = 1.0
        if evidence.timestamp_type == TimestampType.COLLECTION:
            ts_factor = 0.85
        elif evidence.timestamp_type == TimestampType.FALLBACK:
            ts_factor = 0.65

        quality_score = round(completeness * ts_factor, 2)

        # 6. Determine final validation status
        if is_invalid:
            status = ValidationStatus.INVALID
            quality_score = min(quality_score, 0.4)
        elif warnings or evidence.timestamp_type == TimestampType.FALLBACK:
            status = ValidationStatus.WARNING
        else:
            status = ValidationStatus.VALID

        # Update quality metadata on the evidence item
        evidence.quality = EvidenceQuality(
            source_reliability=evidence.quality.source_reliability or SourceReliability.HIGH,
            completeness=completeness,
            timestamp_quality=evidence.timestamp_type,
            validation_status=status,
            quality_score=quality_score,
        )

        for w in warnings:
            if w not in evidence.warnings:
                evidence.warnings.append(w)

        return (not is_invalid), warnings
