"""Evidence deduplication.

Enforces deterministic evidence deduplication using stable business identifiers
(commit SHA, PR number, container ID, metric/alert ID) or canonical SHA-256 content hashes.
Preserves provenance audit metadata when duplicate occurrences are consolidated.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from orchestrator.evidence.models import Evidence


class EvidenceDeduplicator:
    """Consolidates identical or duplicate operational evidence records deterministically."""

    @staticmethod
    def compute_content_hash(data: dict[str, Any], source: str, evidence_type: str) -> str:
        """Compute a deterministic SHA-256 hash for payload content."""
        canonical_str = json.dumps(data, sort_keys=True, default=str)
        raw = f"{source}:{evidence_type}:{canonical_str}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def deduplicate(self, items: list[Evidence]) -> tuple[list[Evidence], int]:
        """Deduplicate a list of evidence items.

        Returns:
            tuple of (deduplicated_items, duplicate_count)
        """
        seen_keys: dict[str, Evidence] = {}
        deduped: list[Evidence] = []
        duplicate_count = 0

        for item in items:
            key = item.dedup_key
            if not key:
                # Compute content-based key fallback
                content_hash = self.compute_content_hash(
                    item.data, item.source, item.evidence_type.value
                )
                key = f"{item.source}:{item.evidence_type.value}:{content_hash}"
                item.dedup_key = key

            if key in seen_keys:
                duplicate_count += 1
                existing = seen_keys[key]

                # Update provenance duplicate count
                current_dups = existing.provenance.metadata.get("duplicate_occurrences", 1)
                existing.provenance.metadata["duplicate_occurrences"] = current_dups + 1

                # Merge correlation identifiers and warnings
                for corr in item.correlation_identifiers:
                    if corr not in existing.correlation_identifiers:
                        existing.correlation_identifiers.append(corr)

                for w in item.warnings:
                    if w not in existing.warnings:
                        existing.warnings.append(w)
            else:
                seen_keys[key] = item
                deduped.append(item)

        return deduped, duplicate_count
