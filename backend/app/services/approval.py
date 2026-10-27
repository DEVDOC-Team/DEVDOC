"""Phase 18 eligibility, human decision, and audit persistence."""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.base import _utcnow
from app.models.approval import Approval, ApprovalDecision, ApprovalStatus
from app.models.approval_artifact import ApprovalArtifact
from app.models.audit_log import AuditLog, AuditOutcome
from app.models.fix_proposal import FixProposal as StoredFixProposal
from app.models.fix_proposal import FixStatus
from app.models.investigation import Investigation
from app.models.project import Project
from app.models.user import User
from app.schemas.approval import (
    ApprovalAuditEvent,
    ApprovalResponse,
    ApprovalReview,
    VerificationReview,
)
from orchestrator.core.context import InvestigationContext
from orchestrator.fixes.models import FixProposal
from orchestrator.rca.models import RCAConfidence, RCAStatus, RootCauseAnalysis
from orchestrator.sandbox.models import SandboxVerificationResult, VerificationStatus

logger = logging.getLogger("devdoc.approvals")
APPROVAL_REQUEST_TTL = timedelta(hours=24)
MAX_PROPOSAL_AGE = timedelta(days=7)
MAX_CLOCK_SKEW = timedelta(minutes=5)


def create_approval_artifact_recorder(
    session_factory: async_sessionmaker[AsyncSession],
) -> Callable[[InvestigationContext], Awaitable[uuid.UUID]]:
    """Create an orchestrator callback that persists outputs using a private DB session."""

    async def record(context: InvestigationContext) -> uuid.UUID:
        async with session_factory() as db:
            artifact_id = await ApprovalService.record_verified_artifact(db, context)
            await db.commit()
            return artifact_id

    return record


class ApprovalService:
    """Server-side approval rules; API bodies never select an actor or status."""

    @staticmethod
    async def record_verified_artifact(db: AsyncSession, context: InvestigationContext) -> uuid.UUID:
        """Persist Phase 15-17 values only from a server-held orchestration context."""
        root_cause = context.root_cause_analysis
        proposal = context.fix_proposal
        verification = context.sandbox_verification_result
        if root_cause is None or proposal is None or verification is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A complete RCA, fix proposal, and sandbox result are required",
            )
        if (
            root_cause.investigation_id != context.investigation_id
            or proposal.investigation_id != context.investigation_id
            or verification.investigation_id != context.investigation_id
            or verification.proposal_id != proposal.proposal_id
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Phase 15-17 artifacts do not share the same investigation and proposal",
            )

        investigation = await db.scalar(
            select(Investigation).where(
                Investigation.id == context.investigation_id,
                Investigation.project_id == context.project_id,
                Investigation.incident_id == context.incident_id,
            )
        )
        if investigation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Investigation not found for the supplied project and incident",
            )

        proposal_payload = _canonical_model(proposal)
        root_cause_payload = _canonical_model(root_cause)
        verification_payload = _canonical_model(verification)
        proposal_record_payload = _proposal_record_payload(proposal)
        record = await db.scalar(
            select(StoredFixProposal)
            .where(StoredFixProposal.id == proposal.proposal_id)
            .with_for_update()
        )
        if record is None:
            record = StoredFixProposal(
                id=proposal.proposal_id,
                investigation_id=proposal.investigation_id,
                created_by_id=None,
                title=proposal.summary,
                description=proposal.rationale,
                patch_content=proposal_payload,
                affected_files=_canonical_value(
                    sorted(
                        {
                            change.target_path
                            for change in proposal.changes
                            if change.target_path is not None
                        }
                    )
                ),
                status=FixStatus.AWAITING_APPROVAL,
                confidence_score=round(proposal.confidence * 100),
            )
            db.add(record)
            await db.flush()
        elif (
            record.investigation_id != proposal.investigation_id
            or _stored_proposal_payload(record) != proposal_record_payload
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Proposal ID already refers to different stored proposal content",
            )

        artifact = ApprovalArtifact(
            id=verification.verification_id,
            project_id=context.project_id,
            investigation_id=context.investigation_id,
            fix_proposal_id=proposal.proposal_id,
            verification_status=verification.status.value,
            root_cause_fingerprint=_fingerprint(root_cause_payload),
            proposal_fingerprint=_fingerprint(proposal_payload),
            proposal_record_fingerprint=_fingerprint(proposal_record_payload),
            verification_fingerprint=_fingerprint(verification_payload),
            root_cause_snapshot=root_cause_payload,
            proposal_snapshot=proposal_payload,
            verification_snapshot=verification_payload,
        )
        db.add(artifact)
        await db.flush()
        logger.info(
            "Recorded verified approval artifact",
            extra={
                "investigation_id": str(context.investigation_id),
                "proposal_id": str(proposal.proposal_id),
                "verification_id": str(verification.verification_id),
                "verification_status": verification.status.value,
            },
        )
        return artifact.id

    @staticmethod
    async def create_request(
        db: AsyncSession,
        project: Project,
        investigation_id: uuid.UUID,
        proposal_id: uuid.UUID,
        actor: User,
        request_id: str | None,
    ) -> ApprovalResponse:
        _require_project_authority(project, actor)
        await _set_request_context(db, request_id)
        investigation = await _get_investigation(db, project.id, investigation_id)
        stored_proposal = await db.scalar(
            select(StoredFixProposal)
            .where(
                StoredFixProposal.id == proposal_id,
                StoredFixProposal.investigation_id == investigation.id,
            )
            .with_for_update()
        )
        if stored_proposal is None:
            raise HTTPException(status_code=404, detail="Fix proposal not found")

        prior = list(
            (
                await db.scalars(
                    select(Approval)
                    .where(Approval.fix_proposal_id == proposal_id)
                    .order_by(Approval.created_at.desc(), Approval.id.desc())
                )
            ).all()
        )
        if any(
            request.status
            in {
                ApprovalStatus.PENDING,
                ApprovalStatus.APPROVED,
                ApprovalStatus.REJECTED,
                ApprovalStatus.SUPERSEDED,
            }
            for request in prior
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This proposal already has a pending or terminal approval request",
            )

        artifact = await db.scalar(
            select(ApprovalArtifact)
            .where(
                ApprovalArtifact.project_id == project.id,
                ApprovalArtifact.investigation_id == investigation.id,
                ApprovalArtifact.fix_proposal_id == proposal_id,
            )
            .order_by(ApprovalArtifact.created_at.desc(), ApprovalArtifact.id.desc())
            .limit(1)
        )
        if artifact is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A server-recorded Phase 15–17 review artifact is required",
            )
        root_cause, proposal, verification = _load_and_validate_artifact(
            artifact, stored_proposal, investigation_id
        )
        _require_approval_eligibility(root_cause, proposal, verification)

        now = _utcnow()
        generated_at = _as_utc(proposal.generated_at)
        if generated_at > now + MAX_CLOCK_SKEW or now - generated_at > MAX_PROPOSAL_AGE:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The proposal is outside the allowed review age",
            )
        if stored_proposal.status not in {
            FixStatus.AWAITING_APPROVAL,
            FixStatus.SANDBOX_PASSED,
        }:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The stored proposal is not eligible for human review",
            )

        approval = Approval(
            id=uuid.uuid4(),
            fix_proposal_id=proposal_id,
            requested_by_id=actor.id,
            verification_id=artifact.id,
            status=ApprovalStatus.PENDING,
            proposal_fingerprint=artifact.proposal_fingerprint,
            verification_fingerprint=artifact.verification_fingerprint,
            expires_at=now + APPROVAL_REQUEST_TTL,
        )
        db.add(approval)
        await db.flush()
        await _audit(
            db,
            actor.id,
            project.id,
            approval.id,
            "approval.requested",
            "Human approval requested for a verified proposal.",
            AuditOutcome.SUCCESS,
            request_id,
            {
                "proposal_id": str(proposal_id),
                "verification_id": str(artifact.id),
                "proposal_fingerprint": artifact.proposal_fingerprint,
                "verification_fingerprint": artifact.verification_fingerprint,
                "status": ApprovalStatus.PENDING.value,
            },
        )
        logger.info(
            "Created approval request",
            extra={
                "approval_id": str(approval.id),
                "investigation_id": str(investigation_id),
                "proposal_id": str(proposal_id),
                "actor_id": str(actor.id),
                "status": approval.status.value,
                "request_id": request_id,
            },
        )
        return await _response(db, approval)

    @staticmethod
    async def get_request(
        db: AsyncSession,
        project: Project,
        investigation_id: uuid.UUID,
        approval_id: uuid.UUID,
        actor: User,
        request_id: str | None,
    ) -> ApprovalResponse:
        _require_project_authority(project, actor)
        await _set_request_context(db, request_id)
        await _get_investigation(db, project.id, investigation_id)
        approval = await _get_approval(
            db, project.id, investigation_id, approval_id, for_update=True
        )
        await _expire_if_due(db, approval, actor.id, project.id, request_id)
        return await _response(db, approval)

    @staticmethod
    async def list_requests(
        db: AsyncSession,
        project: Project,
        investigation_id: uuid.UUID,
        actor: User,
        limit: int,
        offset: int,
        request_id: str | None,
    ) -> tuple[list[ApprovalResponse], int]:
        _require_project_authority(project, actor)
        await _set_request_context(db, request_id)
        await _get_investigation(db, project.id, investigation_id)
        filters = (
            StoredFixProposal.investigation_id == investigation_id,
            Approval.fix_proposal_id == StoredFixProposal.id,
        )
        approvals = list(
            (
                await db.scalars(
                    select(Approval)
                    .join(StoredFixProposal, Approval.fix_proposal_id == StoredFixProposal.id)
                    .where(*filters)
                    .order_by(Approval.created_at.desc(), Approval.id.desc())
                    .limit(limit)
                    .offset(offset)
                )
            ).all()
        )
        for approval in approvals:
            await _expire_if_due(db, approval, actor.id, project.id, request_id)
        total = int(
            await db.scalar(
                select(func.count())
                .select_from(Approval)
                .join(StoredFixProposal, Approval.fix_proposal_id == StoredFixProposal.id)
                .where(*filters)
            )
            or 0
        )
        return [await _response(db, item) for item in approvals], total

    @staticmethod
    async def list_audit_events(
        db: AsyncSession,
        project: Project,
        investigation_id: uuid.UUID,
        actor: User,
        limit: int,
        offset: int,
    ) -> tuple[list[ApprovalAuditEvent], int]:
        _require_project_authority(project, actor)
        await _get_investigation(db, project.id, investigation_id)
        filters = (
            AuditLog.project_id == project.id,
            AuditLog.entity_type == "approval",
            AuditLog.action.like("approval.%"),
            StoredFixProposal.investigation_id == investigation_id,
            Approval.id == AuditLog.entity_id,
        )
        query = (
            select(AuditLog)
            .join(Approval, Approval.id == AuditLog.entity_id)
            .join(StoredFixProposal, StoredFixProposal.id == Approval.fix_proposal_id)
            .where(*filters)
        )
        events = list(
            (
                await db.scalars(
                    query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
                    .limit(limit)
                    .offset(offset)
                )
            ).all()
        )
        total = int(
            await db.scalar(
                select(func.count())
                .select_from(AuditLog)
                .join(Approval, Approval.id == AuditLog.entity_id)
                .join(StoredFixProposal, StoredFixProposal.id == Approval.fix_proposal_id)
                .where(*filters)
            )
            or 0
        )
        return [
            ApprovalAuditEvent(
                id=event.id,
                actor_id=event.actor_id,
                action=event.action,
                description=event.description,
                outcome=event.outcome.value if event.outcome else None,
                request_id=event.session_id,
                created_at=event.created_at,
            )
            for event in events
        ], total

    @staticmethod
    async def approve(
        db: AsyncSession,
        project: Project,
        investigation_id: uuid.UUID,
        approval_id: uuid.UUID,
        actor: User,
        reason: str,
        request_id: str | None,
    ) -> ApprovalResponse:
        return await ApprovalService._decide(
            db,
            project,
            investigation_id,
            approval_id,
            actor,
            ApprovalDecision.APPROVED,
            reason,
            request_id,
        )

    @staticmethod
    async def reject(
        db: AsyncSession,
        project: Project,
        investigation_id: uuid.UUID,
        approval_id: uuid.UUID,
        actor: User,
        reason: str,
        request_id: str | None,
    ) -> ApprovalResponse:
        return await ApprovalService._decide(
            db,
            project,
            investigation_id,
            approval_id,
            actor,
            ApprovalDecision.REJECTED,
            reason,
            request_id,
        )

    @staticmethod
    async def cancel(
        db: AsyncSession,
        project: Project,
        investigation_id: uuid.UUID,
        approval_id: uuid.UUID,
        actor: User,
        reason: str,
        request_id: str | None,
    ) -> ApprovalResponse:
        _require_project_authority(project, actor)
        await _set_request_context(db, request_id)
        await _get_investigation(db, project.id, investigation_id)
        approval = await _get_approval(
            db, project.id, investigation_id, approval_id, for_update=True
        )
        if approval.status != ApprovalStatus.PENDING:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Only a pending approval request can be cancelled",
            )
        if approval.requested_by_id != actor.id and not actor.is_superuser:
            raise HTTPException(status_code=403, detail="Only the requester can cancel this request")
        if _is_expired(approval.expires_at, _utcnow()):
            await _mark_terminal(
                db, approval, ApprovalStatus.EXPIRED, actor.id, project.id, request_id,
                "approval.expired", "Approval request expired before cancellation.",
            )
            return await _response(db, approval)
        approval.status = ApprovalStatus.CANCELLED
        approval.decided_at = _utcnow()
        approval.rationale = reason
        await db.flush()
        await _audit(
            db, actor.id, project.id, approval.id, "approval.cancelled",
            "Pending approval request cancelled by an authorized human.",
            AuditOutcome.SUCCESS, request_id,
            {"status": ApprovalStatus.CANCELLED.value},
        )
        return await _response(db, approval)

    @staticmethod
    async def _decide(
        db: AsyncSession,
        project: Project,
        investigation_id: uuid.UUID,
        approval_id: uuid.UUID,
        actor: User,
        decision: ApprovalDecision,
        reason: str,
        request_id: str | None,
    ) -> ApprovalResponse:
        _require_project_authority(project, actor)
        await _set_request_context(db, request_id)
        await _get_investigation(db, project.id, investigation_id)
        approval = await _get_approval(
            db, project.id, investigation_id, approval_id, for_update=True
        )
        if approval.status != ApprovalStatus.PENDING:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Approval request is not pending; terminal decisions cannot be replayed",
            )
        if _is_expired(approval.expires_at, _utcnow()):
            await _mark_terminal(
                db, approval, ApprovalStatus.EXPIRED, actor.id, project.id, request_id,
                "approval.expired", "Approval request expired before a decision was recorded.",
            )
            return await _response(db, approval)

        artifact = await db.scalar(
            select(ApprovalArtifact)
            .where(
                ApprovalArtifact.id == approval.verification_id,
                ApprovalArtifact.project_id == project.id,
                ApprovalArtifact.investigation_id == investigation_id,
                ApprovalArtifact.fix_proposal_id == approval.fix_proposal_id,
            )
        )
        stored_proposal = await db.scalar(
            select(StoredFixProposal)
            .where(
                StoredFixProposal.id == approval.fix_proposal_id,
                StoredFixProposal.investigation_id == investigation_id,
            )
            .with_for_update()
        )
        if artifact is None or stored_proposal is None:
            raise HTTPException(status_code=409, detail="The approved review artifact is unavailable")
        try:
            _load_and_validate_artifact(artifact, stored_proposal, investigation_id)
        except HTTPException:
            await _mark_terminal(
                db, approval, ApprovalStatus.SUPERSEDED, actor.id, project.id, request_id,
                "approval.stale", "Approval request failed current fingerprint validation.",
            )
            return await _response(db, approval)
        if (
            approval.proposal_fingerprint != artifact.proposal_fingerprint
            or approval.verification_fingerprint != artifact.verification_fingerprint
        ):
            await _mark_terminal(
                db, approval, ApprovalStatus.SUPERSEDED, actor.id, project.id, request_id,
                "approval.stale", "Approval request no longer matches its verified artifact.",
            )
            return await _response(db, approval)

        target_status = (
            ApprovalStatus.APPROVED
            if decision == ApprovalDecision.APPROVED
            else ApprovalStatus.REJECTED
        )
        updated = await db.execute(
            update(Approval)
            .where(
                Approval.id == approval.id,
                Approval.status == ApprovalStatus.PENDING,
            )
            .values(
                status=target_status,
                decision=decision,
                approver_id=actor.id,
                rationale=reason,
                decided_at=_utcnow(),
            )
            .returning(Approval.id)
        )
        if updated.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Another reviewer already completed this approval request",
            )
        await db.refresh(approval)
        action = (
            "approval.approved"
            if decision == ApprovalDecision.APPROVED
            else "approval.rejected"
        )
        await _audit(
            db, actor.id, project.id, approval.id, action,
            "Authorized human recorded an approval decision.",
            AuditOutcome.SUCCESS, request_id,
            {
                "status": approval.status.value,
                "proposal_fingerprint": approval.proposal_fingerprint,
                "verification_fingerprint": approval.verification_fingerprint,
            },
        )
        logger.info(
            "Recorded human approval decision",
            extra={
                "approval_id": str(approval.id),
                "investigation_id": str(investigation_id),
                "proposal_id": str(approval.fix_proposal_id),
                "actor_id": str(actor.id),
                "action": action,
                "status": approval.status.value,
                "request_id": request_id,
            },
        )
        return await _response(db, approval)


async def _get_investigation(
    db: AsyncSession,
    project_id: uuid.UUID,
    investigation_id: uuid.UUID,
) -> Investigation:
    investigation = await db.scalar(
        select(Investigation).where(
            Investigation.id == investigation_id,
            Investigation.project_id == project_id,
        )
    )
    if investigation is None:
        raise HTTPException(status_code=404, detail="Investigation not found in this project")
    return investigation


async def _get_approval(
    db: AsyncSession,
    project_id: uuid.UUID,
    investigation_id: uuid.UUID,
    approval_id: uuid.UUID,
    *,
    for_update: bool,
) -> Approval:
    statement = (
        select(Approval)
        .join(StoredFixProposal, Approval.fix_proposal_id == StoredFixProposal.id)
        .join(Investigation, StoredFixProposal.investigation_id == Investigation.id)
        .where(
            Approval.id == approval_id,
            Investigation.id == investigation_id,
            Investigation.project_id == project_id,
        )
    )
    if for_update:
        statement = statement.with_for_update()
    approval = await db.scalar(statement)
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval request not found")
    return approval


def _require_project_authority(project: Project, actor: User) -> None:
    if not actor.is_active:
        raise HTTPException(status_code=403, detail="User account is inactive")
    if project.owner_id != actor.id and not actor.is_superuser:
        raise HTTPException(status_code=403, detail="Project owner or platform administrator required")


def _require_approval_eligibility(
    root_cause: RootCauseAnalysis,
    proposal: FixProposal,
    verification: SandboxVerificationResult,
) -> None:
    selected = root_cause.selected_root_cause
    if (
        root_cause.status != RCAStatus.ROOT_CAUSE_IDENTIFIED
        or selected is None
        or root_cause.confidence == RCAConfidence.LOW
        or selected.confidence == RCAConfidence.LOW
        or not selected.supporting_evidence
        or proposal.root_cause_reference != selected.candidate_id
    ):
        raise HTTPException(
            status_code=409,
            detail="A supported, selected root cause matching the proposal is required",
        )
    if not proposal.human_approval_required:
        raise HTTPException(status_code=409, detail="Proposal does not require human approval")
    if verification.status != VerificationStatus.PASSED:
        raise HTTPException(
            status_code=409,
            detail="Sandbox verification must pass; no override is available",
        )
    if (
        verification.cleanup_status != "complete"
        or verification.passed_steps < 1
        or verification.failed_steps != 0
        or not verification.verification_steps
        or any(step.status.value != "passed" for step in verification.verification_steps)
    ):
        raise HTTPException(
            status_code=409,
            detail="Verification must contain completed, passing steps and successful cleanup",
        )


def _load_and_validate_artifact(
    artifact: ApprovalArtifact,
    stored_proposal: StoredFixProposal,
    investigation_id: uuid.UUID,
) -> tuple[RootCauseAnalysis, FixProposal, SandboxVerificationResult]:
    try:
        root_payload = json.loads(artifact.root_cause_snapshot)
        proposal_payload = json.loads(artifact.proposal_snapshot)
        verification_payload = json.loads(artifact.verification_snapshot)
        root_cause = RootCauseAnalysis.model_validate(root_payload)
        proposal = FixProposal.model_validate(proposal_payload)
        verification = SandboxVerificationResult.model_validate(verification_payload)
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=409, detail="Stored review artifact is invalid") from exc

    if (
        artifact.investigation_id != investigation_id
        or artifact.fix_proposal_id != proposal.proposal_id
        or artifact.id != verification.verification_id
        or root_cause.investigation_id != investigation_id
        or proposal.investigation_id != investigation_id
        or verification.investigation_id != investigation_id
        or verification.proposal_id != proposal.proposal_id
        or proposal.root_cause_reference
        != (root_cause.selected_root_cause.candidate_id if root_cause.selected_root_cause else None)
    ):
        raise HTTPException(status_code=409, detail="Review artifact identifiers do not match")
    if (
        _fingerprint(_canonical_model(root_cause)) != artifact.root_cause_fingerprint
        or _fingerprint(_canonical_model(proposal)) != artifact.proposal_fingerprint
        or _fingerprint(_canonical_model(verification)) != artifact.verification_fingerprint
        or _fingerprint(_stored_proposal_payload(stored_proposal))
        != artifact.proposal_record_fingerprint
    ):
        raise HTTPException(status_code=409, detail="Review artifact fingerprint validation failed")
    return root_cause, proposal, verification


async def _response(db: AsyncSession, approval: Approval) -> ApprovalResponse:
    review: ApprovalReview | None = None
    if approval.verification_id is not None:
        artifact = await db.get(ApprovalArtifact, approval.verification_id)
        if artifact is not None:
            try:
                root_cause = RootCauseAnalysis.model_validate(
                    json.loads(artifact.root_cause_snapshot)
                )
                proposal = FixProposal.model_validate(json.loads(artifact.proposal_snapshot))
                raw_verification = json.loads(artifact.verification_snapshot)
                verification = VerificationReview.model_validate(
                    _verification_review_payload(raw_verification)
                )
                review = ApprovalReview(
                    root_cause=root_cause,
                    proposal=proposal,
                    verification=verification,
                )
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                raise HTTPException(
                    status_code=409, detail="Stored approval review cannot be decoded"
                ) from exc
    return ApprovalResponse(
        id=approval.id,
        fix_proposal_id=approval.fix_proposal_id,
        verification_id=approval.verification_id,
        status=approval.status,
        requested_by_id=approval.requested_by_id,
        approver_id=approval.approver_id,
        decision=approval.decision,
        rationale=approval.rationale,
        requested_at=approval.created_at,
        decided_at=approval.decided_at,
        expires_at=approval.expires_at,
        proposal_fingerprint=approval.proposal_fingerprint,
        verification_fingerprint=approval.verification_fingerprint,
        review=review,
    )


async def _expire_if_due(
    db: AsyncSession,
    approval: Approval,
    actor_id: uuid.UUID,
    project_id: uuid.UUID,
    request_id: str | None,
) -> None:
    if approval.status == ApprovalStatus.PENDING and _is_expired(approval.expires_at, _utcnow()):
        await _mark_terminal(
            db, approval, ApprovalStatus.EXPIRED, actor_id, project_id, request_id,
            "approval.expired", "Approval request expired before a human decision.",
        )


async def _mark_terminal(
    db: AsyncSession,
    approval: Approval,
    state: ApprovalStatus,
    actor_id: uuid.UUID,
    project_id: uuid.UUID,
    request_id: str | None,
    action: str,
    description: str,
) -> None:
    await _set_request_context(db, request_id)
    approval.status = state
    approval.decided_at = _utcnow()
    await db.flush()
    await _audit(
        db, actor_id, project_id, approval.id, action, description,
        AuditOutcome.SUCCESS, request_id, {"status": state.value},
    )


async def _audit(
    db: AsyncSession,
    actor_id: uuid.UUID,
    project_id: uuid.UUID,
    approval_id: uuid.UUID,
    action: str,
    description: str,
    outcome: AuditOutcome,
    request_id: str | None,
    details: dict[str, str],
) -> None:
    bind = db.bind
    if bind is not None and bind.dialect.name == "postgresql":
        return
    db.add(
        AuditLog(
            id=uuid.uuid4(),
            actor_id=actor_id,
            project_id=project_id,
            action=action,
            entity_type="approval",
            entity_id=approval_id,
            description=description,
            diff=_canonical_value(details),
            outcome=outcome,
            session_id=request_id,
            created_at=_utcnow(),
        )
    )
    await db.flush()


async def _set_request_context(db: AsyncSession, request_id: str | None) -> None:
    if request_id is not None and (
        len(request_id) > 128
        or not all(character.isalnum() or character in "._:-" for character in request_id)
    ):
        raise HTTPException(status_code=400, detail="X-Request-ID contains unsupported characters")
    bind = db.bind
    if bind is not None and bind.dialect.name == "postgresql":
        await db.execute(
            text("SELECT set_config('devdoc.request_id', :request_id, true)"),
            {"request_id": request_id or ""},
        )


def _verification_review_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return review-relevant test results without raw logs or command output."""
    steps = payload.get("verification_steps", [])
    return {
        "verification_id": payload["verification_id"],
        "investigation_id": payload["investigation_id"],
        "proposal_id": payload["proposal_id"],
        "status": payload["status"],
        "started_at": payload["started_at"],
        "completed_at": payload["completed_at"],
        "verification_steps": [
            {
                "step_id": step["step_id"],
                "description": step["description"],
                "status": step["status"],
                "exit_code": step.get("exit_code"),
                "duration_ms": step["duration_ms"],
                "expected_result": step["expected_result"],
                "observed_result": step["observed_result"],
            }
            for step in steps
        ],
        "passed_steps": payload["passed_steps"],
        "failed_steps": payload["failed_steps"],
        "risk_findings": payload["risk_findings"],
        "cleanup_status": payload["cleanup_status"],
        "summary": payload["summary"],
    }


def _proposal_record_payload(proposal: FixProposal) -> str:
    return _canonical_value(
        {
            "id": str(proposal.proposal_id),
            "investigation_id": str(proposal.investigation_id),
            "title": proposal.summary,
            "description": proposal.rationale,
            "patch_content": _canonical_model(proposal),
            "affected_files": sorted(
                {
                    change.target_path
                    for change in proposal.changes
                    if change.target_path is not None
                }
            ),
            "status": FixStatus.AWAITING_APPROVAL.value,
            "confidence_score": round(proposal.confidence * 100),
        }
    )


def _stored_proposal_payload(proposal: StoredFixProposal) -> str:
    return _canonical_value(
        {
            "id": str(proposal.id),
            "investigation_id": str(proposal.investigation_id),
            "title": proposal.title,
            "description": proposal.description,
            "patch_content": proposal.patch_content,
            "affected_files": json.loads(proposal.affected_files or "[]"),
            "status": proposal.status.value,
            "confidence_score": proposal.confidence_score,
        }
    )


def _canonical_model(model: Any) -> str:
    return _canonical_value(model.model_dump(mode="json"))


def _canonical_value(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _fingerprint(canonical_payload: str) -> str:
    return hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _is_expired(expires_at: datetime | None, now: datetime) -> bool:
    return expires_at is not None and _as_utc(expires_at) <= now
