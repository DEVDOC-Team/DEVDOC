"""Evidence-validated, explainable root-cause analysis using the Phase 13 LLM service."""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from collections import OrderedDict
from collections.abc import Iterable
from datetime import UTC, datetime

from pydantic import ValidationError

from orchestrator.core.context import InvestigationContext
from orchestrator.core.sanitizer import sanitize_string
from orchestrator.evidence.models import Evidence, EvidenceSource, EvidenceType
from orchestrator.llm.service import LLMService, LLMServiceError
from orchestrator.rca.models import (
    CandidateRootCause,
    EvidenceClassification,
    RCACandidateOutput,
    RCAClaim,
    RCACompletion,
    RCAConfidence,
    RCAEvidenceReference,
    RCAStatus,
    RootCauseAnalysis,
)
from orchestrator.rca.prompt_builder import RCA_SYSTEM_MESSAGE, RCAPromptBuilder

logger = logging.getLogger("devdoc.orchestrator.rca")
_URL_PATTERN = re.compile(r"https?://", re.IGNORECASE)
_UUID_PATTERN = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)
_TIMESTAMP_PATTERN = re.compile(
    r"\b\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?\b"
)
_CANDIDATE_NAMESPACE = uuid.UUID("31d6cba1-b507-4e69-9cbe-7fed2460ba5a")
_NO_EVIDENCE = "No validated evidence is available to establish an incident-specific cause."
_DEFAULT_MISSING_INFORMATION = [
    "Collect a time-bounded application log or stack trace for the affected service.",
    "Collect relevant resource and health metrics around the incident window.",
    "Collect deployment and configuration changes preceding the first observed symptom.",
]


class RCAServiceError(Exception):
    """Safe root-cause analysis failure suitable for stage reporting."""


class RootCauseAnalysisService:
    """Build a typed RCA and only select a candidate that meets evidence thresholds."""

    def __init__(
        self,
        llm_service: LLMService,
        *,
        prompt_builder: RCAPromptBuilder | None = None,
        max_analyses_per_investigation: int = 3,
    ) -> None:
        if not 1 <= max_analyses_per_investigation <= 10:
            raise ValueError("max_analyses_per_investigation must be between 1 and 10")
        self._llm = llm_service
        self._prompt_builder = prompt_builder or RCAPromptBuilder()
        self._max_analyses_per_investigation = max_analyses_per_investigation
        self._analysis_usage: OrderedDict[tuple[uuid.UUID, uuid.UUID], int] = OrderedDict()
        self._usage_lock = asyncio.Lock()

    async def analyze(self, context: InvestigationContext) -> RootCauseAnalysis:
        """Analyze the current evidence snapshot without mutating it."""
        if context.is_cancelled():
            raise RCAServiceError("Root-cause analysis cancelled")
        collection = context.evidence_collection
        if collection is None:
            return self._insufficient_evidence(context, [])
        if (
            collection.investigation_id != context.investigation_id
            or collection.execution_id != context.execution_id
        ):
            raise RCAServiceError("Evidence does not belong to the active investigation execution")
        if not collection.items:
            return self._insufficient_evidence(context, [])

        evidence_by_id = {item.evidence_id: item for item in collection.items}
        if len(evidence_by_id) != len(collection.items):
            raise RCAServiceError("Evidence set contains duplicate evidence IDs")
        await self._reserve_investigation_analysis(context)
        try:
            user_message = self._prompt_builder.build(context, collection)
            completion, metadata = await self._llm.complete_structured(
                system_message=RCA_SYSTEM_MESSAGE,
                user_message=user_message,
                response_model=RCACompletion,
                cache_scope=(
                    f"phase15-rca:{context.project_id}:"
                    f"{context.investigation_id}:{context.execution_id}:"
                    f"{context.initiated_by_id or 'system'}"
                ),
                validation_error_message="Nemotron response failed RCA schema validation",
                validate_result=lambda output: self._validate_references(
                    output,
                    evidence_by_id,
                    {relation.relationship_id for relation in collection.correlations},
                ),
                cancellation_check=context.is_cancelled,
            )
        except LLMServiceError as exc:
            if context.is_cancelled():
                raise RCAServiceError("Root-cause analysis cancelled") from exc
            raise RCAServiceError(str(exc)) from exc
        except (ValidationError, ValueError, TypeError) as exc:
            raise RCAServiceError("RCA input failed prompt contract validation") from exc
        if context.is_cancelled():
            raise RCAServiceError("Root-cause analysis cancelled")

        analysis_id = uuid.uuid4()
        candidates = [
            self._build_candidate(
                candidate,
                index=index,
                analysis_id=analysis_id,
                evidence_by_id=evidence_by_id,
                relationship_ids={relation.relationship_id for relation in collection.correlations},
            )
            for index, candidate in enumerate(completion.candidates)
        ]
        candidates.sort(key=self._ranking_key, reverse=True)
        candidates = [
            candidate.model_copy(update={"rank": rank})
            for rank, candidate in enumerate(candidates, start=1)
        ]
        status, selected, confidence = self._select_root_cause(candidates)
        summary_references = self._references(
            completion.reasoning_summary_evidence_ids,
            evidence_by_id,
        )
        all_references = self._aggregate_references(candidates)
        all_references = self._unique_references([*all_references, *summary_references])
        contradictions = self._unique_references(
            reference for candidate in candidates for reference in candidate.contradicting_evidence
        )
        result = RootCauseAnalysis(
            analysis_id=analysis_id,
            investigation_id=context.investigation_id,
            execution_id=context.execution_id,
            status=status,
            candidates=candidates,
            selected_root_cause=selected,
            confidence=confidence,
            observed_facts=self._observed_facts(evidence_by_id),
            reasoning_summary_evidence=summary_references,
            evidence_references=all_references,
            contradictions=contradictions,
            uncertainties=[self._safe_text(value, 2_000) for value in completion.uncertainties],
            missing_information=[
                self._safe_text(value, 2_000) for value in completion.missing_information
            ]
            or (_DEFAULT_MISSING_INFORMATION if status != RCAStatus.ROOT_CAUSE_IDENTIFIED else []),
            reasoning_summary=self._safe_text(completion.reasoning_summary, 4_000),
            analyzed_at=datetime.now(UTC),
            model_metadata=metadata,
        )
        logger.info(
            "Root-cause analysis completed",
            extra={
                "investigation_id": str(context.investigation_id),
                "execution_id": str(context.execution_id),
                "analysis_id": str(analysis_id),
                "model": metadata.model,
                "duration_ms": round(metadata.duration_ms, 2),
                "input_tokens": metadata.input_tokens,
                "output_tokens": metadata.output_tokens,
                "estimated_cost_usd": metadata.estimated_cost_usd,
                "status": result.status.value,
                "candidate_count": len(result.candidates),
                "cache_hit": metadata.cache_hit,
            },
        )
        return result

    @staticmethod
    def _validate_references(
        completion: RCACompletion,
        evidence_by_id: dict[uuid.UUID, Evidence],
        relationship_ids: set[str],
    ) -> None:
        known_evidence_ids = set(evidence_by_id)
        if any(
            evidence_id not in known_evidence_ids
            for evidence_id in completion.reasoning_summary_evidence_ids
        ):
            raise LLMServiceError(
                "Nemotron summary referenced evidence outside the active evidence set"
            )
        if not any(
            RootCauseAnalysisService._is_observed(evidence_by_id[evidence_id])
            for evidence_id in completion.reasoning_summary_evidence_ids
        ):
            raise LLMServiceError("RCA summary lacks supporting observed incident evidence")
        for candidate in completion.candidates:
            referenced_ids: Iterable[uuid.UUID] = (
                *candidate.supporting_evidence_ids,
                *candidate.contradicting_evidence_ids,
                *(
                    evidence_id
                    for claim in (
                        *candidate.contributing_factors,
                        *candidate.triggering_events,
                        *candidate.observed_symptoms,
                    )
                    for evidence_id in claim.evidence_ids
                ),
            )
            if any(evidence_id not in known_evidence_ids for evidence_id in referenced_ids):
                raise LLMServiceError(
                    "Nemotron response referenced evidence outside the active evidence set"
                )
            if not any(
                RootCauseAnalysisService._is_observed(evidence_by_id[evidence_id])
                for evidence_id in candidate.supporting_evidence_ids
            ):
                raise LLMServiceError("RCA candidate lacks supporting observed incident evidence")
            if any(
                relationship_id not in relationship_ids
                for relationship_id in candidate.temporal_relationship_ids
            ):
                raise LLMServiceError(
                    "Nemotron response referenced a correlation outside the evidence set"
                )
        RootCauseAnalysisService._validate_generated_text(completion, evidence_by_id)

    @staticmethod
    def _validate_generated_text(
        completion: RCACompletion,
        evidence_by_id: dict[uuid.UUID, Evidence],
    ) -> None:
        texts = [
            completion.reasoning_summary,
            *completion.uncertainties,
            *completion.missing_information,
        ]
        for candidate in completion.candidates:
            texts.extend((candidate.statement, candidate.uncertainty, candidate.rationale))
            texts.extend(
                claim.statement
                for claim in (
                    *candidate.contributing_factors,
                    *candidate.triggering_events,
                    *candidate.observed_symptoms,
                )
            )
        if any(_URL_PATTERN.search(text) for text in texts):
            raise LLMServiceError("Nemotron response contained an unverified URL")
        evidence_ids = {str(evidence_id) for evidence_id in evidence_by_id}
        if any(
            referenced_id.lower() not in evidence_ids
            for text in texts
            for referenced_id in _UUID_PATTERN.findall(text)
        ):
            raise LLMServiceError("Nemotron prose referenced an unknown evidence ID")
        allowed_timestamps = {
            timestamp_match
            for item in evidence_by_id.values()
            for timestamp_match in (
                *_TIMESTAMP_PATTERN.findall(item.timestamp.isoformat()),
                item.timestamp.date().isoformat(),
            )
        }
        if any(
            timestamp not in allowed_timestamps
            for text in texts
            for timestamp in _TIMESTAMP_PATTERN.findall(text)
        ):
            raise LLMServiceError("Nemotron response contained an unverified timestamp")

    def _build_candidate(
        self,
        output: RCACandidateOutput,
        *,
        index: int,
        analysis_id: uuid.UUID,
        evidence_by_id: dict[uuid.UUID, Evidence],
        relationship_ids: set[str],
    ) -> CandidateRootCause:
        supporting = self._references(output.supporting_evidence_ids, evidence_by_id)
        contradicting = self._references(output.contradicting_evidence_ids, evidence_by_id)
        observed_support = [
            ref for ref in supporting if ref.classification == EvidenceClassification.FACT
        ]
        observed_contradiction = [
            ref for ref in contradicting if ref.classification == EvidenceClassification.FACT
        ]
        independent_sources = {
            evidence_by_id[reference.evidence_id].source for reference in observed_support
        }
        confidence = self._classify_confidence(
            observed_count=len({ref.evidence_id for ref in observed_support}),
            independent_source_count=len(independent_sources),
            contradiction_count=len({ref.evidence_id for ref in observed_contradiction}),
        )
        factors = [
            RCAClaim(
                statement=self._safe_text(claim.statement, 1_000),
                evidence_references=self._references(claim.evidence_ids, evidence_by_id),
            )
            for claim in output.contributing_factors
        ]
        triggers = [
            RCAClaim(
                statement=self._safe_text(claim.statement, 1_000),
                evidence_references=self._references(claim.evidence_ids, evidence_by_id),
            )
            for claim in output.triggering_events
        ]
        symptoms = [
            RCAClaim(
                statement=self._safe_text(claim.statement, 1_000),
                evidence_references=self._references(claim.evidence_ids, evidence_by_id),
            )
            for claim in output.observed_symptoms
        ]
        return CandidateRootCause(
            candidate_id=uuid.uuid5(_CANDIDATE_NAMESPACE, f"{analysis_id}:{index}"),
            statement=self._safe_text(output.statement, 2_000),
            category=output.category,
            confidence=confidence,
            rank=1,
            supporting_evidence=supporting,
            contradicting_evidence=contradicting,
            contributing_factors=factors,
            triggering_events=triggers,
            observed_symptoms=symptoms,
            temporal_relationship_ids=[
                relationship_id
                for relationship_id in output.temporal_relationship_ids
                if relationship_id in relationship_ids
            ],
            uncertainty=self._safe_text(output.uncertainty, 2_000),
            rationale=self._safe_text(output.rationale, 4_000),
            ranking_basis=(
                f"{len({ref.evidence_id for ref in observed_support})} distinct observed "
                f"supporting evidence item(s) across {len(independent_sources)} source(s); "
                f"{len({ref.evidence_id for ref in observed_contradiction})} distinct "
                "observed contradiction(s). External references do not increase confidence."
            ),
        )

    @staticmethod
    def _classify_confidence(
        *,
        observed_count: int,
        independent_source_count: int,
        contradiction_count: int,
    ) -> RCAConfidence:
        if observed_count >= 3 and independent_source_count >= 2 and contradiction_count == 0:
            return RCAConfidence.HIGH
        if (
            observed_count >= 2
            and independent_source_count >= 2
            and contradiction_count < observed_count
        ):
            return RCAConfidence.MEDIUM
        return RCAConfidence.LOW

    @staticmethod
    def _ranking_key(candidate: CandidateRootCause) -> tuple[int, int, int, int]:
        confidence = {
            RCAConfidence.LOW: 0,
            RCAConfidence.MEDIUM: 1,
            RCAConfidence.HIGH: 2,
        }[candidate.confidence]
        observed_support = {
            ref.evidence_id
            for ref in candidate.supporting_evidence
            if ref.classification == EvidenceClassification.FACT
        }
        sources = {
            ref.source
            for ref in candidate.supporting_evidence
            if ref.evidence_id in observed_support
        }
        observed_contradictions = {
            ref.evidence_id
            for ref in candidate.contradicting_evidence
            if ref.classification == EvidenceClassification.FACT
        }
        return (
            confidence,
            len(sources),
            len(observed_support),
            -len(observed_contradictions),
        )

    @staticmethod
    def _select_root_cause(
        candidates: list[CandidateRootCause],
    ) -> tuple[RCAStatus, CandidateRootCause | None, RCAConfidence]:
        if not candidates:
            return RCAStatus.INSUFFICIENT_EVIDENCE, None, RCAConfidence.LOW
        top = candidates[0]
        if top.confidence == RCAConfidence.LOW:
            return RCAStatus.INSUFFICIENT_EVIDENCE, None, top.confidence
        if len(candidates) > 1 and RootCauseAnalysisService._ranking_key(
            candidates[1]
        ) == RootCauseAnalysisService._ranking_key(top):
            return RCAStatus.MULTIPLE_PLAUSIBLE_CAUSES, None, top.confidence
        if top.confidence != RCAConfidence.HIGH:
            return RCAStatus.INSUFFICIENT_EVIDENCE, None, top.confidence
        return RCAStatus.ROOT_CAUSE_IDENTIFIED, top, top.confidence

    @staticmethod
    def _is_observed(item: Evidence) -> bool:
        return not (
            item.source_type == EvidenceSource.EXTERNAL_KNOWLEDGE
            or item.evidence_type == EvidenceType.EXTERNAL_KNOWLEDGE
        )

    @staticmethod
    def _references(
        evidence_ids: list[uuid.UUID],
        evidence_by_id: dict[uuid.UUID, Evidence],
    ) -> list[RCAEvidenceReference]:
        references: list[RCAEvidenceReference] = []
        seen: set[uuid.UUID] = set()
        for evidence_id in evidence_ids:
            if evidence_id in seen:
                continue
            seen.add(evidence_id)
            item = evidence_by_id[evidence_id]
            external = not RootCauseAnalysisService._is_observed(item)
            references.append(
                RCAEvidenceReference(
                    evidence_id=item.evidence_id,
                    classification=(
                        EvidenceClassification.EXTERNAL_KNOWLEDGE
                        if external
                        else EvidenceClassification.FACT
                    ),
                    source=sanitize_string(item.source)[:256],
                    evidence_type=item.evidence_type.value,
                    timestamp=item.timestamp,
                    source_url=(
                        sanitize_string(item.provenance.source_reference)[:2_048]
                        if external and item.provenance.source_reference
                        else None
                    ),
                    title=sanitize_string(item.title)[:2_048],
                    summary=sanitize_string(item.summary)[:4_096],
                )
            )
        return references

    @staticmethod
    def _aggregate_references(
        candidates: list[CandidateRootCause],
    ) -> list[RCAEvidenceReference]:
        return RootCauseAnalysisService._unique_references(
            reference
            for candidate in candidates
            for reference in (*candidate.supporting_evidence, *candidate.contradicting_evidence)
        )

    @staticmethod
    def _observed_facts(
        evidence_by_id: dict[uuid.UUID, Evidence],
    ) -> list[RCAEvidenceReference]:
        observed_ids = [
            evidence_id
            for evidence_id, item in evidence_by_id.items()
            if RootCauseAnalysisService._is_observed(item)
        ]
        return RootCauseAnalysisService._references(
            observed_ids[:100],
            evidence_by_id,
        )

    @staticmethod
    def _unique_references(
        references: Iterable[RCAEvidenceReference],
    ) -> list[RCAEvidenceReference]:
        unique: dict[uuid.UUID, RCAEvidenceReference] = {}
        for reference in references:
            unique.setdefault(reference.evidence_id, reference)
        return list(unique.values())

    @staticmethod
    def _safe_text(value: str, limit: int) -> str:
        return sanitize_string(value).strip()[:limit]

    async def _reserve_investigation_analysis(
        self,
        context: InvestigationContext,
    ) -> None:
        key = (context.project_id, context.investigation_id)
        async with self._usage_lock:
            count = self._analysis_usage.get(key, 0)
            if count >= self._max_analyses_per_investigation:
                raise RCAServiceError("Investigation exceeded the configured RCA analysis limit")
            self._analysis_usage[key] = count + 1
            self._analysis_usage.move_to_end(key)
            while len(self._analysis_usage) > 10_000:
                self._analysis_usage.popitem(last=False)

    @staticmethod
    def _insufficient_evidence(
        context: InvestigationContext,
        missing_information: list[str],
    ) -> RootCauseAnalysis:
        return RootCauseAnalysis(
            analysis_id=uuid.uuid4(),
            investigation_id=context.investigation_id,
            execution_id=context.execution_id,
            status=RCAStatus.INSUFFICIENT_EVIDENCE,
            candidates=[],
            selected_root_cause=None,
            confidence=RCAConfidence.LOW,
            observed_facts=[],
            reasoning_summary_evidence=[],
            evidence_references=[],
            contradictions=[],
            uncertainties=[_NO_EVIDENCE],
            missing_information=[
                *missing_information,
                *(_DEFAULT_MISSING_INFORMATION if not missing_information else []),
            ][:20],
            reasoning_summary=(
                "No incident-specific root cause was selected because validated evidence "
                "was unavailable. Unknown is an expected result."
            ),
            analyzed_at=datetime.now(UTC),
            model_metadata=None,
        )
