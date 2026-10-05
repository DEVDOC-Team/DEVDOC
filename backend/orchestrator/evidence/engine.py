"""Evidence processing pipeline for operational investigation results."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Sequence
from typing import Any

from orchestrator.core.context import InvestigationContext
from orchestrator.core.result import AgentResult
from orchestrator.evidence.config import EvidenceEngineConfig
from orchestrator.evidence.deduplicator import EvidenceDeduplicator
from orchestrator.evidence.models import (
    CorrelationRelationship,
    Evidence,
    EvidenceCollection,
    EvidenceSummary,
    TimelineEvent,
)
from orchestrator.evidence.normalizer import EvidenceNormalizer
from orchestrator.evidence.validator import EvidenceValidator


class EvidenceEngine:
    """Normalize, validate, deduplicate, correlate, and order agent evidence."""

    def __init__(self, config: EvidenceEngineConfig | None = None) -> None:
        self.config = config if config is not None else EvidenceEngineConfig()
        self.normalizer = EvidenceNormalizer(self.config.limits)
        self.validator = EvidenceValidator(self.config.limits)
        self.deduplicator = EvidenceDeduplicator()

    def process(
        self,
        agent_results: Sequence[AgentResult],
        context: InvestigationContext,
        *,
        correlation_window_seconds: int | None = None,
    ) -> EvidenceCollection:
        """Build a bounded evidence collection from agent results for one execution."""
        context.validate()
        window_seconds = self._resolve_window(correlation_window_seconds)
        collection = EvidenceCollection(
            investigation_id=context.investigation_id,
            execution_id=context.execution_id,
        )
        normalized: list[Evidence] = []
        rejected_count = 0

        results_to_process = agent_results[: self.config.limits.max_evidence_items]
        if len(agent_results) > len(results_to_process):
            collection.warnings.append(
                f"Evidence item limit ({self.config.limits.max_evidence_items}) reached; remaining agent results were omitted"
            )
            rejected_count += len(agent_results) - len(results_to_process)

        for result in results_to_process:
            if (
                result.investigation_id is not None
                and result.investigation_id != context.investigation_id
            ) or (result.execution_id is not None and result.execution_id != context.execution_id):
                collection.warnings.append(
                    f"Skipped evidence from agent '{result.agent_id}' with mismatched execution identifiers"
                )
                rejected_count += 1
                continue

            try:
                agent_items = self.normalizer.normalize_agent_result(result, context)
            except (AttributeError, TypeError, ValueError, OverflowError, RecursionError) as exc:
                collection.warnings.append(
                    f"Could not normalize evidence from agent '{result.agent_id}' "
                    f"({type(exc).__name__})"
                )
                rejected_count += 1
                continue

            remaining = self.config.limits.max_evidence_items - len(normalized)
            if remaining <= 0:
                collection.warnings.append(
                    f"Evidence item limit ({self.config.limits.max_evidence_items}) reached; remaining items were omitted"
                )
                break
            if len(agent_items) > remaining:
                agent_items = agent_items[:remaining]
                collection.warnings.append(
                    f"Evidence item limit ({self.config.limits.max_evidence_items}) reached; some items were omitted"
                )
            normalized.extend(agent_items)

        valid_items: list[Evidence] = []
        collection_bytes = 0
        for item in normalized:
            self._sanitize_evidence(item)
            is_valid, warnings = self.validator.validate(item)
            collection.warnings.extend(warnings)
            if is_valid:
                item_bytes = len(
                    json.dumps(item.to_dict(), default=str, ensure_ascii=False).encode("utf-8")
                )
                if collection_bytes + item_bytes > self.config.limits.max_collection_bytes:
                    collection.warnings.append(
                        f"Evidence collection size limit "
                        f"({self.config.limits.max_collection_bytes} bytes) reached; additional items were omitted"
                    )
                    rejected_count += 1
                    continue
                collection_bytes += item_bytes
                valid_items.append(item)
            else:
                rejected_count += 1

        deduplicated, duplicate_count = self.deduplicator.deduplicate(valid_items)
        collection.items = deduplicated
        collection.warnings.extend(warning for item in deduplicated for warning in item.warnings)

        if self.config.enable_timeline:
            collection.timeline = self._build_timeline(deduplicated, collection)
        if self.config.enable_correlation:
            collection.correlations = self._correlate(
                deduplicated,
                window_seconds=window_seconds,
                collection=collection,
            )

        collection.summary = self._summarize(
            deduplicated,
            duplicate_count=duplicate_count,
            validation_failure_count=rejected_count,
            correlation_count=len(collection.correlations),
            warning_count=len(collection.warnings),
        )
        collection.groups_by_source = self._group_ids(deduplicated, lambda item: item.source)
        collection.groups_by_type = self._group_ids(
            deduplicated, lambda item: item.evidence_type.value
        )
        collection.metadata = {
            "correlation_window_seconds": window_seconds,
            "timestamp_tolerance_seconds": self.config.correlation.timestamp_tolerance_seconds,
            "duplicates_removed": duplicate_count,
            "rejected_item_count": rejected_count,
            "collection_payload_bytes": collection_bytes,
            "max_collection_bytes": self.config.limits.max_collection_bytes,
            "timeline_enabled": self.config.enable_timeline,
            "correlation_enabled": self.config.enable_correlation,
        }
        collection.warnings = self._unique_strings(collection.warnings)
        collection.summary.warning_count = len(collection.warnings)
        return collection

    def _resolve_window(self, window_seconds: int | None) -> int:
        if window_seconds is None:
            return self.config.correlation.default_window_seconds
        if window_seconds <= 0:
            raise ValueError("correlation_window_seconds must be positive")
        if window_seconds > self.config.correlation.max_window_seconds:
            raise ValueError(
                "correlation_window_seconds cannot exceed "
                f"{self.config.correlation.max_window_seconds}"
            )
        return window_seconds

    def _sanitize_evidence(self, item: Evidence) -> None:
        """Sanitize free-text presentation fields that are not covered by payload sanitization."""
        from orchestrator.core.sanitizer import sanitize_data, sanitize_string

        max_length = self.config.limits.max_string_length

        def bound_text(value: str) -> str:
            sanitized = sanitize_string(value)
            if len(sanitized) <= max_length:
                return sanitized
            marker = "[TRUNCATED]"
            if max_length <= len(marker):
                return marker[:max_length]
            return sanitized[: max_length - len(marker)] + marker

        item.title = bound_text(item.title)
        item.summary = bound_text(item.summary)
        item.source = bound_text(item.source)
        item.warnings = [bound_text(warning) for warning in item.warnings]
        item.correlation_identifiers = [
            bound_text(identifier) for identifier in item.correlation_identifiers
        ]
        item.provenance.source = bound_text(item.provenance.source)
        if item.provenance.source_reference:
            item.provenance.source_reference = bound_text(item.provenance.source_reference)
        item.provenance.metadata = sanitize_data(item.provenance.metadata)
        item.data = sanitize_data(item.data)
        if self._contains_truncation_marker(item.data) and not any(
            "truncated" in warning.lower() for warning in item.warnings
        ):
            item.warnings.append("Evidence payload was truncated to configured limits")

    @staticmethod
    def _contains_truncation_marker(value: Any) -> bool:
        if isinstance(value, str):
            return "[TRUNCATED]" in value
        if isinstance(value, dict):
            return any(EvidenceEngine._contains_truncation_marker(item) for item in value.values())
        if isinstance(value, list):
            return any(EvidenceEngine._contains_truncation_marker(item) for item in value)
        return False

    def _build_timeline(
        self,
        items: list[Evidence],
        collection: EvidenceCollection,
    ) -> list[TimelineEvent]:
        ordered = sorted(items, key=lambda item: (item.timestamp, str(item.evidence_id)))
        max_entries = self.config.limits.max_timeline_entries
        if len(ordered) > max_entries:
            collection.warnings.append(
                f"Timeline entry limit ({max_entries}) reached; later events were omitted"
            )
            ordered = ordered[:max_entries]
        return [
            TimelineEvent(
                timestamp=item.timestamp,
                evidence_id=item.evidence_id,
                source=item.source,
                evidence_type=item.evidence_type.value,
                title=item.title,
                summary=item.summary,
                correlation_identifiers=list(item.correlation_identifiers),
                timestamp_type=item.timestamp_type.value,
            )
            for item in ordered
        ]

    def _correlate(
        self,
        items: list[Evidence],
        *,
        window_seconds: int,
        collection: EvidenceCollection,
    ) -> list[CorrelationRelationship]:
        max_relationships = self.config.limits.max_correlation_relationships
        relationships: list[CorrelationRelationship] = []
        seen: set[tuple[str, str, str, str | None]] = set()

        def add_relationship(
            first: Evidence,
            second: Evidence,
            relationship_type: str,
            *,
            shared_identifier: str | None = None,
            time_delta: float | None = None,
        ) -> bool:
            pair = sorted((str(first.evidence_id), str(second.evidence_id)))
            key = (pair[0], pair[1], relationship_type, shared_identifier)
            if key in seen:
                return True
            if len(relationships) >= max_relationships:
                return False
            seen.add(key)
            relationship_hash = hashlib.sha256(
                json.dumps(key, separators=(",", ":")).encode("utf-8")
            ).hexdigest()[:24]
            relationships.append(
                CorrelationRelationship(
                    relationship_id=relationship_hash,
                    source_evidence_id=first.evidence_id,
                    target_evidence_id=second.evidence_id,
                    relationship_type=relationship_type,
                    shared_identifier=shared_identifier,
                    time_delta_seconds=time_delta,
                    description=(
                        f"Evidence items share identifier '{shared_identifier}'"
                        if shared_identifier is not None
                        else f"Evidence items occurred within {window_seconds} seconds"
                    ),
                )
            )
            return True

        items_by_identifier: dict[str, list[Evidence]] = defaultdict(list)
        for item in items:
            for identifier in set(item.correlation_identifiers):
                items_by_identifier[identifier].append(item)

        limit_reached = False
        for identifier in sorted(items_by_identifier):
            matching_items = sorted(
                items_by_identifier[identifier], key=lambda item: str(item.evidence_id)
            )
            for index, first in enumerate(matching_items):
                for second in matching_items[index + 1 :]:
                    if not add_relationship(
                        first,
                        second,
                        f"shares_identifier:{identifier.split(':', 1)[0]}",
                        shared_identifier=identifier,
                    ):
                        limit_reached = True
                        break
                if limit_reached:
                    break
            if limit_reached:
                break

        effective_window = min(
            self.config.correlation.max_window_seconds,
            window_seconds + self.config.correlation.timestamp_tolerance_seconds,
        )
        if not limit_reached:
            ordered = sorted(items, key=lambda item: (item.timestamp, str(item.evidence_id)))
            for index, first in enumerate(ordered):
                for second in ordered[index + 1 :]:
                    delta = (second.timestamp - first.timestamp).total_seconds()
                    if delta > effective_window:
                        break
                    if delta >= 0 and not add_relationship(
                        first,
                        second,
                        "temporal_proximity",
                        time_delta=delta,
                    ):
                        limit_reached = True
                        break
                if limit_reached:
                    break

        if limit_reached:
            collection.warnings.append(
                f"Correlation relationship limit ({max_relationships}) reached; additional links were omitted"
            )
        return relationships

    @staticmethod
    def _summarize(
        items: list[Evidence],
        *,
        duplicate_count: int,
        validation_failure_count: int,
        correlation_count: int,
        warning_count: int,
    ) -> EvidenceSummary:
        counts_by_source: dict[str, int] = {}
        counts_by_type: dict[str, int] = {}
        for item in items:
            counts_by_source[item.source] = counts_by_source.get(item.source, 0) + 1
            evidence_type = item.evidence_type.value
            counts_by_type[evidence_type] = counts_by_type.get(evidence_type, 0) + 1

        timestamps = [item.timestamp for item in items]
        return EvidenceSummary(
            total_evidence_count=len(items),
            counts_by_source=dict(sorted(counts_by_source.items())),
            counts_by_type=dict(sorted(counts_by_type.items())),
            earliest_timestamp=min(timestamps) if timestamps else None,
            latest_timestamp=max(timestamps) if timestamps else None,
            validation_failure_count=validation_failure_count,
            duplicate_count=duplicate_count,
            correlation_count=correlation_count,
            warning_count=warning_count,
            sources_present=sorted(counts_by_source),
        )

    @staticmethod
    def _group_ids(
        items: list[Evidence],
        key_getter: Any,
    ) -> dict[str, list[dict[str, str]]]:
        groups: dict[str, list[dict[str, str]]] = defaultdict(list)
        for item in items:
            groups[key_getter(item)].append(
                {"evidence_id": str(item.evidence_id), "title": item.title}
            )
        return {key: groups[key] for key in sorted(groups)}

    def _unique_strings(self, values: list[str]) -> list[str]:
        from orchestrator.core.sanitizer import sanitize_string

        maximum = self.config.limits.max_string_length
        sanitized: list[str] = []
        for value in values:
            safe_value = sanitize_string(value)
            if len(safe_value) > maximum:
                safe_value = safe_value[:maximum]
            if safe_value and safe_value not in sanitized:
                sanitized.append(safe_value)
            if len(sanitized) >= self.config.limits.max_evidence_items:
                break
        return sanitized
