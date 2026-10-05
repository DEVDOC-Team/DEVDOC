"""Evidence Engine configuration.

Provides validated settings for correlation windows, size limits, and processing flags.
Prevents unbounded memory growth and ensures predictable, bounded execution.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EvidenceCorrelationConfig:
    """Settings controlling temporal and identifier correlation."""

    default_window_seconds: int = 3600  # Default correlation window: 1 hour
    max_window_seconds: int = 86400  # Maximum correlation window: 24 hours
    timestamp_tolerance_seconds: int = 60  # Tolerance for timestamp jitter: 1 minute

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        """Validate correlation configuration invariants."""
        if self.default_window_seconds <= 0:
            raise ValueError(
                f"default_window_seconds must be positive, got {self.default_window_seconds}"
            )
        if self.max_window_seconds < self.default_window_seconds:
            raise ValueError(
                f"max_window_seconds ({self.max_window_seconds}) cannot be less than "
                f"default_window_seconds ({self.default_window_seconds})"
            )
        if self.timestamp_tolerance_seconds < 0:
            raise ValueError(
                f"timestamp_tolerance_seconds must be non-negative, got {self.timestamp_tolerance_seconds}"
            )


@dataclass
class EvidenceLimitsConfig:
    """Size and payload limits to guard against memory exhaustion and oversized payloads."""

    max_evidence_items: int = 500
    max_payload_bytes: int = 1_000_000  # 1 MB max serialized payload per evidence item
    max_collection_bytes: int = 10_000_000  # 10 MB max normalized evidence collection
    max_string_length: int = 4096  # Max length for string fields before explicit truncation
    max_timeline_entries: int = 500
    max_correlation_relationships: int = 1000
    max_source_records_per_agent: int = 100

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        """Validate limit configuration invariants."""
        if self.max_evidence_items <= 0:
            raise ValueError(f"max_evidence_items must be positive, got {self.max_evidence_items}")
        if self.max_payload_bytes <= 0:
            raise ValueError(f"max_payload_bytes must be positive, got {self.max_payload_bytes}")
        if self.max_collection_bytes <= 0:
            raise ValueError(
                f"max_collection_bytes must be positive, got {self.max_collection_bytes}"
            )
        if self.max_string_length <= 0:
            raise ValueError(f"max_string_length must be positive, got {self.max_string_length}")
        if self.max_timeline_entries <= 0:
            raise ValueError(f"max_timeline_entries must be positive, got {self.max_timeline_entries}")
        if self.max_correlation_relationships <= 0:
            raise ValueError(
                f"max_correlation_relationships must be positive, got {self.max_correlation_relationships}"
            )
        if self.max_source_records_per_agent <= 0:
            raise ValueError(
                f"max_source_records_per_agent must be positive, got {self.max_source_records_per_agent}"
            )


@dataclass
class EvidenceEngineConfig:
    """Master configuration for the DEVDOC Evidence Engine."""

    correlation: EvidenceCorrelationConfig = field(default_factory=EvidenceCorrelationConfig)
    limits: EvidenceLimitsConfig = field(default_factory=EvidenceLimitsConfig)
    enable_correlation: bool = True
    enable_timeline: bool = True
