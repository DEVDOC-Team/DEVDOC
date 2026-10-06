"""Phase 16 service: validate an RCA-grounded proposal without performing actions."""

from __future__ import annotations

import asyncio
import uuid
from collections import OrderedDict
from datetime import UTC, datetime

from pydantic import ValidationError

from orchestrator.core.context import InvestigationContext
from orchestrator.evidence.models import (
    Evidence,
    EvidenceCollection,
    EvidenceSource,
    EvidenceType,
)
from orchestrator.fixes.models import (
    FixCompletion,
    FixGenerationResult,
    FixGenerationStatus,
    FixProposal,
    FixProposalStatus,
)
from orchestrator.fixes.prompt_builder import FIX_SYSTEM_MESSAGE, FixPromptBuilder
from orchestrator.fixes.safety import (
    FixSafetyError,
    normalize_repository_path,
    risk_requires_human_review,
    validate_fix_completion,
)
from orchestrator.llm.service import LLMService, LLMServiceError
from orchestrator.rca.models import (
    CandidateRootCause,
    EvidenceClassification,
    RCAEvidenceReference,
    RCAStatus,
    RootCauseAnalysis,
)


class FixGenerationError(Exception):
    """Safe Phase 16 failure suitable for orchestrator stage reporting."""


class FixGeneratorService:
    """Create validated, evidence-bound proposals using the shared Phase 13 LLM controls."""

    def __init__(
        self,
        llm_service: LLMService,
        *,
        prompt_builder: FixPromptBuilder | None = None,
        max_generations_per_investigation: int = 3,
    ) -> None:
        if not 1 <= max_generations_per_investigation <= 10:
            raise ValueError("max_generations_per_investigation must be between 1 and 10")
        self._llm = llm_service
        self._prompt_builder = prompt_builder or FixPromptBuilder()
        self._max_generations_per_investigation = max_generations_per_investigation
        self._generation_usage: OrderedDict[tuple[uuid.UUID, uuid.UUID], int] = OrderedDict()
        self._usage_lock = asyncio.Lock()

    async def generate(
        self,
        context: InvestigationContext,
        analysis: RootCauseAnalysis,
        evidence: EvidenceCollection | None = None,
    ) -> FixGenerationResult:
        """Return a safe proposal or a controlled no-proposal outcome."""
        if context.is_cancelled():
            return FixGenerationResult(
                status=FixGenerationStatus.CANCELLED,
                reason="Fix generation was cancelled",
            )
        if analysis.investigation_id != context.investigation_id:
            raise FixGenerationError("Root-cause analysis belongs to another investigation")
        if analysis.execution_id != context.execution_id:
            raise FixGenerationError("Root-cause analysis belongs to another execution")
        collection = evidence if evidence is not None else context.evidence_collection
        if collection is None:
            return _insufficient("Validated evidence is unavailable")
        if (
            collection.investigation_id != context.investigation_id
            or collection.execution_id != context.execution_id
        ):
            raise FixGenerationError("Evidence does not belong to the active investigation")
        if context.evidence_collection is not None and collection != context.evidence_collection:
            raise FixGenerationError("Evidence differs from the active investigation snapshot")
        if (
            analysis.status != RCAStatus.ROOT_CAUSE_IDENTIFIED
            or analysis.selected_root_cause is None
        ):
            return _insufficient("The RCA did not uniquely identify an eligible root cause")
        if not collection.items:
            return _insufficient("Validated evidence is unavailable")

        evidence_by_id = {item.evidence_id: item for item in collection.items}
        if len(evidence_by_id) != len(collection.items):
            raise FixGenerationError("Evidence set contains duplicate evidence IDs")
        root_cause = analysis.selected_root_cause
        candidate_matches = [
            candidate
            for candidate in analysis.candidates
            if candidate.candidate_id == root_cause.candidate_id
        ]
        if len(candidate_matches) != 1 or candidate_matches[0] != root_cause:
            raise FixGenerationError("Selected root cause is not part of the active RCA")
        production_context = _is_production_context(context.execution_metadata)
        try:
            _validate_root_cause_references(root_cause, evidence_by_id)
            known_paths = _known_repository_paths(collection)
            system_message = FIX_SYSTEM_MESSAGE
            user_message = self._prompt_builder.build(context, analysis, collection)
            await self._reserve_investigation_generation(context)

            def validate_result(output: FixCompletion) -> None:
                validate_fix_completion(
                    output,
                    root_cause=root_cause,
                    evidence_by_id=evidence_by_id,
                    known_repository_paths=known_paths,
                    production_context=production_context,
                )

            completion, metadata = await self._llm.complete_structured(
                system_message=system_message,
                user_message=user_message,
                response_model=FixCompletion,
                cache_scope=(
                    f"phase16-fix:{context.project_id}:{context.investigation_id}:"
                    f"{context.execution_id}:{context.initiated_by_id or 'system'}"
                ),
                validation_error_message="Nemotron response failed fix proposal schema validation",
                validate_result=validate_result,
                cancellation_check=context.is_cancelled,
            )
            if context.is_cancelled():
                return FixGenerationResult(
                    status=FixGenerationStatus.CANCELLED,
                    reason="Fix generation was cancelled",
                )
            completion = validate_fix_completion(
                completion,
                root_cause=root_cause,
                evidence_by_id=evidence_by_id,
                known_repository_paths=known_paths,
                production_context=production_context,
            )
        except FixSafetyError as exc:
            return FixGenerationResult(
                status=FixGenerationStatus.UNSAFE,
                reason=str(exc),
            )
        except LLMServiceError as exc:
            if context.is_cancelled():
                return FixGenerationResult(
                    status=FixGenerationStatus.CANCELLED,
                    reason="Fix generation was cancelled",
                )
            raise FixGenerationError(str(exc)) from exc
        except (ValidationError, TypeError, ValueError) as exc:
            raise FixGenerationError("Fix generation input failed contract validation") from exc

        proposal_status = (
            FixProposalStatus.REQUIRES_HUMAN_REVIEW
            if risk_requires_human_review(completion.risks)
            else FixProposalStatus.PROPOSED
        )
        proposal = FixProposal(
            proposal_id=uuid.uuid4(),
            investigation_id=context.investigation_id,
            execution_id=context.execution_id,
            root_cause_reference=root_cause.candidate_id,
            status=proposal_status,
            summary=completion.summary,
            rationale=completion.rationale,
            affected_components=completion.affected_components,
            change_type=completion.change_type,
            changes=completion.changes,
            prerequisites=completion.prerequisites,
            risks=completion.risks,
            verification_plan=completion.verification_plan,
            rollback_plan=completion.rollback_plan,
            evidence_references=completion.evidence_references,
            external_knowledge_references=completion.external_knowledge_references,
            confidence=completion.confidence,
            change_scope=completion.change_scope,
            human_approval_required=True,
            generated_at=datetime.now(UTC),
            model_metadata=metadata,
        )
        return FixGenerationResult(
            status=FixGenerationStatus(proposal.status.value),
            proposal=proposal,
        )

    async def _reserve_investigation_generation(
        self,
        context: InvestigationContext,
    ) -> None:
        key = (context.project_id, context.investigation_id)
        async with self._usage_lock:
            count = self._generation_usage.get(key, 0)
            if count >= self._max_generations_per_investigation:
                raise FixGenerationError(
                    "Investigation exceeded the configured fix generation limit"
                )
            self._generation_usage[key] = count + 1
            self._generation_usage.move_to_end(key)
            while len(self._generation_usage) > 10_000:
                self._generation_usage.popitem(last=False)


def _insufficient(reason: str) -> FixGenerationResult:
    return FixGenerationResult(
        status=FixGenerationStatus.INSUFFICIENT_INFORMATION,
        reason=reason,
    )


def _validate_root_cause_references(
    root_cause: CandidateRootCause,
    evidence_by_id: dict[uuid.UUID, Evidence],
) -> None:
    references: list[RCAEvidenceReference] = [
        *root_cause.supporting_evidence,
        *root_cause.contradicting_evidence,
        *(
            reference
            for claim in (
                *root_cause.contributing_factors,
                *root_cause.triggering_events,
                *root_cause.observed_symptoms,
            )
            for reference in claim.evidence_references
        ),
    ]
    if not any(
        reference.classification == EvidenceClassification.FACT
        and reference.evidence_id in evidence_by_id
        and not _is_external(evidence_by_id[reference.evidence_id])
        for reference in root_cause.supporting_evidence
    ):
        raise FixSafetyError("Selected RCA lacks observed supporting evidence")
    for reference in references:
        item = evidence_by_id.get(reference.evidence_id)
        if item is None:
            raise FixSafetyError("Selected RCA referenced evidence outside the active set")
        is_external = _is_external(item)
        expected = (
            EvidenceClassification.EXTERNAL_KNOWLEDGE
            if is_external
            else EvidenceClassification.FACT
        )
        if reference.classification != expected:
            raise FixSafetyError("Selected RCA evidence classification did not match its source")


def _known_repository_paths(collection: EvidenceCollection) -> set[str]:
    paths: set[str] = set()
    for item in collection.items:
        if item.evidence_type != EvidenceType.FILE_CONTENT:
            continue
        candidates = [item.data.get("path")] if isinstance(item.data, dict) else []
        prefix = "File Content: "
        if item.title.startswith(prefix):
            candidates.append(item.title[len(prefix) :])
        for candidate in candidates:
            if not isinstance(candidate, str):
                continue
            try:
                paths.add(normalize_repository_path(candidate))
            except FixSafetyError:
                continue
    return paths


def _is_external(evidence: Evidence) -> bool:
    return (
        evidence.source_type == EvidenceSource.EXTERNAL_KNOWLEDGE
        or evidence.evidence_type == EvidenceType.EXTERNAL_KNOWLEDGE
    )


def _is_production_context(metadata: dict[str, object]) -> bool:
    return any(
        isinstance(value, str) and value.strip().lower() in {"prod", "production"}
        for key, value in metadata.items()
        if key in {"environment", "deployment_environment"}
    )
