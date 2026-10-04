"""Timestamp normalization utilities for investigation evidence.

Guarantees that all evidence items have timezone-aware UTC timestamps.
Tracks timestamp provenance (event, collection, or fallback).
Prevents silent fabrication of historical event timestamps.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from orchestrator.evidence.models import TimestampType

# Common date string regex format patterns for parsing
_ISO_FORMATS = (
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%S.%f%z",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S.%fZ",
    "%Y-%m-%d %H:%M:%S%z",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
)


def normalize_timestamp(
    raw_val: Any,
    fallback: datetime | None = None,
) -> tuple[datetime, TimestampType, list[str]]:
    """Normalize a raw timestamp into a timezone-aware UTC datetime.

    Args:
        raw_val: Raw timestamp (datetime, str, int, float, or None)
        fallback: Optional deterministic fallback timestamp to use if raw_val is missing or invalid.

    Returns:
        tuple of (normalized_datetime_utc, timestamp_type, list_of_warnings)

    Raises:
        ValueError: If raw_val cannot be parsed and no fallback is supplied.
    """
    warnings: list[str] = []

    # 1. Handle datetime instance
    if isinstance(raw_val, datetime):
        if raw_val.tzinfo is None:
            # Naive datetime: attach UTC
            return raw_val.replace(tzinfo=UTC), TimestampType.EVENT, []
        return raw_val.astimezone(UTC), TimestampType.EVENT, []

    # 2. Handle numeric unix timestamps
    if isinstance(raw_val, (int, float)) and not isinstance(raw_val, bool):
        try:
            dt = datetime.fromtimestamp(float(raw_val), tz=UTC)
            return dt, TimestampType.EVENT, []
        except (ValueError, OverflowError, OSError) as exc:
            if fallback is not None:
                fb_dt = fallback.astimezone(UTC) if fallback.tzinfo else fallback.replace(tzinfo=UTC)
                warnings.append(
                    f"Numeric timestamp {raw_val} out of range ({exc}); using fallback {fb_dt.isoformat()}"
                )
                return fb_dt, TimestampType.FALLBACK, warnings
            raise ValueError(f"Numeric timestamp {raw_val} out of range: {exc}") from exc

    # 3. Handle string representation
    if isinstance(raw_val, str) and raw_val.strip():
        s = raw_val.strip()

        # Try standard fromisoformat first (handles standard ISO-8601 including +00:00 and Z in Python 3.11+)
        try:
            # Normalize trailing Z to +00:00 for robust compatibility
            normalized_s = re.sub(r"Z$", "+00:00", s, flags=re.IGNORECASE)
            dt = datetime.fromisoformat(normalized_s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            else:
                dt = dt.astimezone(UTC)
            return dt, TimestampType.EVENT, []
        except (ValueError, TypeError):
            pass

        # Try alternative explicit strptime formats
        for fmt in _ISO_FORMATS:
            try:
                dt = datetime.strptime(s, fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=UTC)
                else:
                    dt = dt.astimezone(UTC)
                return dt, TimestampType.EVENT, []
            except (ValueError, TypeError):
                continue

    # 4. If invalid or empty, use fallback if available
    if fallback is not None:
        fb_dt = fallback.astimezone(UTC) if fallback.tzinfo else fallback.replace(tzinfo=UTC)
        warning_text = (
            f"Missing or unparseable timestamp '{raw_val}'; using fallback timestamp {fb_dt.isoformat()}"
        )
        warnings.append(warning_text)
        return fb_dt, TimestampType.FALLBACK, warnings

    raise ValueError(f"Unable to parse timestamp '{raw_val}' and no fallback was provided")
