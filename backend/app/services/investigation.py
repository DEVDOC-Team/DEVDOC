"""Investigation Service.

Encapsulates all business logic, lifecycle state transitions, and database operations
for DEVDOC investigations. Keeps route handlers thin and guarantees consistent
multi-level authorization (project + incident boundary) and data validation.
"""

from __future__ import annotations

import json
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.github_client import GitHubAPIClient
from app.core.logging import logger
from app.db.base import _utcnow
from app.models.evidence import Evidence as StoredEvidence
from app.models.evidence import EvidenceKind
from app.models.fix_proposal import FixProposal as StoredFixProposal
from app.models.fix_proposal import FixStatus
from app.models.github_connection import UserGitHubConnection
from app.models.incident import Incident
from app.models.investigation import Investigation, InvestigationStatus
from app.models.project import Project
from app.models.repository import Repository
from app.models.user import User
from app.schemas.investigation import (
    InvestigationCreate,
    InvestigationStatusUpdate,
    InvestigationUpdate,
)
from app.services.approval import ApprovalService
from orchestrator.core.context import CancellationToken, InvestigationContext
from orchestrator.core.factory import create_operational_orchestrator
from orchestrator.core.orchestrator import DEVDOCOrchestrator
from orchestrator.core.result import ExecutionStatus, OrchestrationResult
from orchestrator.fixes.models import FixProposal
from orchestrator.rca.models import RCAStatus
from orchestrator.sandbox.docker import (
    create_default_docker_sandbox_provider,
    is_docker_available,
)
from orchestrator.sandbox.models import VerificationCommand, VerificationStatus


def _canonical_value(val: Any) -> str:
    return json.dumps(val, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _canonical_model(model: Any) -> str:
    if hasattr(model, "model_dump"):
        return _canonical_value(model.model_dump(mode="json"))
    return _canonical_value(model)


def _map_evidence_kind(evidence_type: Any) -> EvidenceKind:
    raw = evidence_type.value if hasattr(evidence_type, "value") else str(evidence_type)
    mapping = {
        "log_excerpt": EvidenceKind.LOG_EXCERPT,
        "stack_trace": EvidenceKind.STACK_TRACE,
        "metric_snapshot": EvidenceKind.METRIC_SNAPSHOT,
        "metric": EvidenceKind.METRIC_SNAPSHOT,
        "service_health": EvidenceKind.METRIC_SNAPSHOT,
        "alert": EvidenceKind.METRIC_SNAPSHOT,
        "config_diff": EvidenceKind.CONFIG_DIFF,
        "commit_diff": EvidenceKind.COMMIT_DIFF,
        "commit": EvidenceKind.COMMIT_DIFF,
        "repository": EvidenceKind.OTHER,
        "pull_request": EvidenceKind.OTHER,
        "issue": EvidenceKind.OTHER,
        "ci_log": EvidenceKind.CI_LOG,
        "workflow_run": EvidenceKind.CI_LOG,
        "container_log": EvidenceKind.CONTAINER_LOG,
        "container": EvidenceKind.CONTAINER_LOG,
        "container_state": EvidenceKind.CONTAINER_LOG,
        "image": EvidenceKind.OTHER,
        "documentation": EvidenceKind.DOCUMENTATION,
        "external_knowledge": EvidenceKind.DOCUMENTATION,
        "file_content": EvidenceKind.DOCUMENTATION,
    }
    return mapping.get(str(raw).lower(), EvidenceKind.OTHER)


@dataclass
class InvestigationRunResult(OrchestrationResult):
    """Orchestration result enriched with persisted pipeline outputs."""

    context: InvestigationContext | None = None
    evidence_count: int = 0
    has_root_cause_analysis: bool = False
    has_fix_proposal: bool = False
    approval_artifact_id: uuid.UUID | None = None
    approval_status: str | None = None


# ---------------------------------------------------------------------------
# Allowed Status Lifecycle Transitions
# ---------------------------------------------------------------------------

VALID_INVESTIGATION_TRANSITIONS: dict[InvestigationStatus, set[InvestigationStatus]] = {
    InvestigationStatus.PENDING: {InvestigationStatus.RUNNING, InvestigationStatus.CANCELLED},
    InvestigationStatus.RUNNING: {
        InvestigationStatus.COMPLETED,
        InvestigationStatus.FAILED,
        InvestigationStatus.CANCELLED,
    },
    InvestigationStatus.COMPLETED: set(),
    InvestigationStatus.FAILED: set(),
    InvestigationStatus.CANCELLED: set(),
}


def validate_investigation_status_transition(
    current_status: InvestigationStatus, target_status: InvestigationStatus
) -> None:
    """Validate status transition against the allowed investigation operational lifecycle.

    Raises:
        HTTPException(422): If the requested transition is not permitted.
    """
    if current_status == target_status:
        return

    allowed = VALID_INVESTIGATION_TRANSITIONS.get(current_status, set())
    if target_status not in allowed:
        allowed_names = sorted(s.value for s in allowed)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Invalid investigation status transition from '{current_status.value}' to '{target_status.value}'. "
                f"Allowed transitions from '{current_status.value}' are: {allowed_names}"
            ),
        )


class InvestigationService:
    """Service handling Investigation creation, listing, retrieval, updates, and transitions."""

    @staticmethod
    async def get_incident_for_project(
        db: AsyncSession,
        project: Project,
        incident_id: uuid.UUID,
    ) -> Incident:
        """Validate that an incident exists and belongs to the specified authorized project.

        Raises:
            HTTPException(404): If the incident does not exist in this project.
        """
        stmt = select(Incident).where(
            Incident.id == incident_id,
            Incident.project_id == project.id,
        )
        incident = (await db.execute(stmt)).scalar_one_or_none()
        if incident is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Incident '{incident_id}' not found in project '{project.id}'",
            )
        return incident

    @staticmethod
    async def create_investigation(
        db: AsyncSession,
        project: Project,
        incident: Incident,
        current_user: User,
        data: InvestigationCreate,
    ) -> Investigation:
        """Create a new investigation anchored strictly to project, incident, and reporting user."""
        # Enforce consistency: check if an active investigation is already in progress
        active_stmt = select(Investigation).where(
            Investigation.incident_id == incident.id,
            Investigation.project_id == project.id,
            Investigation.status.in_([InvestigationStatus.PENDING, InvestigationStatus.RUNNING]),
        )
        active_investigation = (await db.execute(active_stmt)).scalars().first()
        if active_investigation is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"An active investigation '{active_investigation.id}' is already in progress "
                    f"({active_investigation.status.value}) for this incident"
                ),
            )

        now = _utcnow()
        started_at = now if data.status == InvestigationStatus.RUNNING else None

        investigation = Investigation(
            id=uuid.uuid4(),
            project_id=project.id,
            incident_id=incident.id,
            initiated_by_id=current_user.id,
            status=data.status,
            summary=data.summary,
            started_at=started_at,
            completed_at=None,
            tokens_used=0,
            estimated_cost_usd=0,
        )

        db.add(investigation)
        await db.flush()
        await db.refresh(investigation)

        logger.info(
            "Investigation created",
            extra={
                "investigation_id": str(investigation.id),
                "incident_id": str(incident.id),
                "project_id": str(project.id),
                "actor_id": str(current_user.id),
                "status": investigation.status.value,
            },
        )
        return investigation

    @staticmethod
    async def list_investigations(
        db: AsyncSession,
        project: Project,
        incident: Incident,
        limit: int = 20,
        offset: int = 0,
        status_filter: InvestigationStatus | None = None,
    ) -> tuple[list[Investigation], int]:
        """List investigations belonging to the verified incident and project."""
        safe_limit = max(1, min(limit, 100))
        safe_offset = max(0, offset)

        base_filter = [
            Investigation.project_id == project.id,
            Investigation.incident_id == incident.id,
        ]

        if status_filter is not None:
            base_filter.append(Investigation.status == status_filter)

        count_stmt = select(func.count()).select_from(Investigation).where(*base_filter)
        total: int = (await db.execute(count_stmt)).scalar() or 0

        query_stmt = (
            select(Investigation)
            .where(*base_filter)
            .order_by(Investigation.created_at.desc(), Investigation.id.desc())
            .limit(safe_limit)
            .offset(safe_offset)
        )
        items = list((await db.execute(query_stmt)).scalars().all())
        return items, total

    @staticmethod
    async def get_investigation(
        db: AsyncSession,
        project: Project,
        incident: Incident,
        investigation_id: uuid.UUID,
    ) -> Investigation:
        """Retrieve an investigation verified against both project and incident boundaries.

        Raises:
            HTTPException(404): If not found within the project and incident scope.
        """
        stmt = select(Investigation).where(
            Investigation.id == investigation_id,
            Investigation.incident_id == incident.id,
            Investigation.project_id == project.id,
        )
        investigation = (await db.execute(stmt)).scalar_one_or_none()
        if investigation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Investigation '{investigation_id}' not found for incident '{incident.id}'",
            )
        return investigation

    @staticmethod
    async def update_investigation(
        db: AsyncSession,
        project: Project,
        incident: Incident,
        investigation: Investigation,
        data: InvestigationUpdate,
    ) -> Investigation:
        """Update mutable fields on an investigation."""
        update_data = data.model_dump(exclude_unset=True)

        if "status" in update_data and update_data["status"] is not None:
            new_status = update_data["status"]
            validate_investigation_status_transition(investigation.status, new_status)
            if new_status != investigation.status:
                investigation.status = new_status
                if new_status == InvestigationStatus.RUNNING and investigation.started_at is None:
                    investigation.started_at = _utcnow()
                elif new_status in (
                    InvestigationStatus.COMPLETED,
                    InvestigationStatus.FAILED,
                    InvestigationStatus.CANCELLED,
                ):
                    investigation.completed_at = _utcnow()

        if "summary" in update_data:
            investigation.summary = update_data["summary"]
        if "error_message" in update_data:
            investigation.error_message = update_data["error_message"]

        await db.flush()
        await db.refresh(investigation)

        logger.info(
            "Investigation updated",
            extra={
                "investigation_id": str(investigation.id),
                "incident_id": str(incident.id),
                "project_id": str(project.id),
                "status": investigation.status.value,
            },
        )
        return investigation

    @staticmethod
    async def transition_investigation_status(
        db: AsyncSession,
        project: Project,
        incident: Incident,
        investigation: Investigation,
        status_data: InvestigationStatusUpdate,
    ) -> Investigation:
        """Advance or cancel investigation status according to finite state machine."""
        new_status = status_data.status
        validate_investigation_status_transition(investigation.status, new_status)

        if new_status != investigation.status:
            old_status = investigation.status
            investigation.status = new_status

            if new_status == InvestigationStatus.RUNNING and investigation.started_at is None:
                investigation.started_at = _utcnow()
            elif new_status in (
                InvestigationStatus.COMPLETED,
                InvestigationStatus.FAILED,
                InvestigationStatus.CANCELLED,
            ):
                investigation.completed_at = _utcnow()

            if new_status == InvestigationStatus.FAILED and status_data.error_message:
                investigation.error_message = status_data.error_message

            await db.flush()
            await db.refresh(investigation)

            logger.info(
                "Investigation status transitioned",
                extra={
                    "investigation_id": str(investigation.id),
                    "incident_id": str(incident.id),
                    "project_id": str(project.id),
                    "old_status": old_status.value,
                    "new_status": new_status.value,
                },
            )

        return investigation

    @staticmethod
    async def delete_investigation(
        db: AsyncSession,
        project: Project,
        incident: Incident,
        investigation: Investigation,
    ) -> uuid.UUID:
        """Delete an investigation within the authorized project and incident."""
        inv_id = investigation.id
        await db.delete(investigation)
        await db.flush()

        logger.info(
            "Investigation deleted",
            extra={
                "investigation_id": str(inv_id),
                "incident_id": str(incident.id),
                "project_id": str(project.id),
            },
        )
        return inv_id

    @staticmethod
    def build_orchestration_context(
        investigation: Investigation,
        initiated_by: User | None = None,
        cancellation_token: CancellationToken | None = None,
    ) -> InvestigationContext:
        """Construct a strongly typed InvestigationContext from an authorized Investigation model."""
        actor_id = initiated_by.id if initiated_by else investigation.initiated_by_id
        return InvestigationContext(
            investigation_id=investigation.id,
            incident_id=investigation.incident_id,
            project_id=investigation.project_id,
            initiated_by_id=actor_id,
            execution_metadata={
                "incident_id": str(investigation.incident_id),
                "project_id": str(investigation.project_id),
            },
            cancellation_token=cancellation_token or CancellationToken(),
        )

    @staticmethod
    async def _persist_evidence(
        db: AsyncSession,
        investigation: Investigation,
        context: InvestigationContext,
    ) -> int:
        """Persist collected evidence items into the evidence table idempotently."""
        if context.evidence_collection is None or not context.evidence_collection.items:
            return 0

        existing_stmt = select(StoredEvidence.id).where(StoredEvidence.investigation_id == investigation.id)
        existing_ids = set((await db.scalars(existing_stmt)).all())

        count = 0
        for item in context.evidence_collection.items:
            if item.evidence_id in existing_ids:
                continue

            raw_data = None
            if item.data:
                try:
                    raw_data = json.dumps(item.data, default=str)
                except Exception:
                    raw_data = str(item.data)
            elif item.summary:
                raw_data = item.summary

            source_meta = None
            if item.provenance:
                try:
                    source_meta = json.dumps(item.provenance.to_dict(), default=str)
                except Exception:
                    source_meta = None

            quality_score = None
            if item.quality and item.quality.quality_score is not None:
                quality_score = max(0, min(100, int(round(item.quality.quality_score * 100))))

            source_ref = None
            if item.provenance and item.provenance.source_reference:
                source_ref = str(item.provenance.source_reference)[:2048]

            ev_record = StoredEvidence(
                id=item.evidence_id,
                investigation_id=investigation.id,
                kind=_map_evidence_kind(item.evidence_type),
                label=(item.title or f"{item.source} evidence")[:512],
                raw_content=raw_data,
                source_url=source_ref,
                source_metadata=source_meta,
                collected_at=(item.provenance.collected_at if item.provenance else None) or item.timestamp,
                relevance_score=quality_score,
            )
            db.add(ev_record)
            existing_ids.add(item.evidence_id)
            count += 1

        await db.flush()
        return count

    @staticmethod
    def _persist_rca(
        investigation: Investigation,
        context: InvestigationContext,
    ) -> bool:
        """Persist root-cause analysis summary and token metrics into the investigation record."""
        if context.root_cause_analysis is None:
            if not investigation.summary:
                investigation.summary = (
                    "Investigation completed without AI root-cause analysis "
                    "(LLM reasoning disabled or unconfigured)."
                )
            return False

        rca = context.root_cause_analysis
        if rca.status == RCAStatus.ROOT_CAUSE_IDENTIFIED and rca.selected_root_cause:
            investigation.summary = (
                f"Root Cause Identified: {rca.selected_root_cause.statement}\n"
                f"Confidence: {rca.confidence.value.upper()}\n"
                f"Category: {rca.selected_root_cause.category.value}\n\n"
                f"{rca.reasoning_summary}"
            )
        elif rca.status == RCAStatus.MULTIPLE_PLAUSIBLE_CAUSES:
            investigation.summary = (
                f"Multiple Plausible Causes Identified (Confidence: {rca.confidence.value.upper()}):\n\n"
                f"{rca.reasoning_summary}"
            )
        else:
            investigation.summary = (
                f"Insufficient Evidence for Root Cause (Confidence: {rca.confidence.value.upper()}):\n\n"
                f"{rca.reasoning_summary}"
            )

        if rca.model_metadata:
            meta = rca.model_metadata
            tokens = (getattr(meta, "input_tokens", 0) or 0) + (getattr(meta, "output_tokens", 0) or 0)
            investigation.tokens_used += tokens
            cost = getattr(meta, "estimated_cost_usd", 0.0) or 0.0
            if cost:
                investigation.estimated_cost_usd += round(cost * 1_000_000)

        return True

    @staticmethod
    async def _persist_fix_proposal(
        db: AsyncSession,
        investigation: Investigation,
        context: InvestigationContext,
    ) -> bool:
        """Persist generated fix proposal into the fix_proposals table idempotently."""
        if context.fix_proposal is None:
            return False

        proposal = context.fix_proposal
        existing = await db.get(StoredFixProposal, proposal.proposal_id)

        verification = context.sandbox_verification_result
        if verification is not None:
            if verification.status == VerificationStatus.PASSED:
                target_status = FixStatus.AWAITING_APPROVAL
            elif verification.status in (
                VerificationStatus.FAILED,
                VerificationStatus.TIMEOUT,
                VerificationStatus.UNSAFE,
                VerificationStatus.SETUP_FAILED,
            ):
                target_status = FixStatus.SANDBOX_FAILED
            else:
                target_status = FixStatus.SANDBOX_PENDING
            sandbox_run_id = str(verification.verification_id)
            sandbox_log = verification.summary
        else:
            target_status = FixStatus.DRAFT
            sandbox_run_id = None
            sandbox_log = None

        proposal_payload = _canonical_model(proposal)
        affected_files = _canonical_value(
            sorted(
                {
                    change.target_path
                    for change in proposal.changes
                    if change.target_path is not None
                }
            )
        )
        confidence_score = max(0, min(100, round(proposal.confidence * 100)))

        if existing is None:
            record = StoredFixProposal(
                id=proposal.proposal_id,
                investigation_id=investigation.id,
                created_by_id=None,
                title=proposal.summary[:512],
                description=proposal.rationale,
                patch_content=proposal_payload,
                affected_files=affected_files,
                status=target_status,
                sandbox_run_id=sandbox_run_id,
                sandbox_log=sandbox_log,
                confidence_score=confidence_score,
            )
            db.add(record)
        else:
            existing.status = target_status
            existing.sandbox_run_id = sandbox_run_id
            existing.sandbox_log = sandbox_log
            existing.confidence_score = confidence_score
            existing.title = proposal.summary[:512]
            existing.description = proposal.rationale
            existing.patch_content = proposal_payload
            existing.affected_files = affected_files

        if proposal.model_metadata:
            meta = proposal.model_metadata
            tokens = (getattr(meta, "input_tokens", 0) or 0) + (getattr(meta, "output_tokens", 0) or 0)
            investigation.tokens_used += tokens
            cost = getattr(meta, "estimated_cost_usd", 0.0) or 0.0
            if cost:
                investigation.estimated_cost_usd += round(cost * 1_000_000)

        await db.flush()
        return True

    @staticmethod
    async def run_investigation_orchestration(
        db: AsyncSession,
        project: Project,
        incident: Incident,
        investigation: Investigation,
        orchestrator: DEVDOCOrchestrator | None = None,
        cancellation_token: CancellationToken | None = None,
    ) -> InvestigationRunResult:
        """Execute the investigation orchestrator and persist all pipeline results.

        Guarantees:
        - Must be in PENDING or RUNNING status prior to execution.
        - Automatically transitions PENDING -> RUNNING upon execution start.
        - Rejects terminal investigations (422).
        - Executes all pipeline stages (Collect, Analyze, RCA, Fix, Sandbox Verification).
        - Persists collected evidence to PostgreSQL evidence model idempotently.
        - Persists root cause analysis summary and token metrics to investigation model.
        - Persists generated fix proposal to fix_proposals model with appropriate status.
        - Persists approval review artifact when verification genuinely passes.
        - Never fabricates passing verification results or auto-approves fixes.
        - Transitions investigation status to COMPLETED, FAILED, or CANCELLED.
        - Flushes state to database.
        """
        # Validate boundary
        if investigation.project_id != project.id or investigation.incident_id != incident.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Investigation '{investigation.id}' does not belong to project/incident",
            )

        if investigation.status not in (InvestigationStatus.PENDING, InvestigationStatus.RUNNING):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Cannot orchestrate investigation with terminal status '{investigation.status.value}'",
            )

        # Transition PENDING -> RUNNING if needed
        if investigation.status == InvestigationStatus.PENDING:
            investigation.status = InvestigationStatus.RUNNING
            investigation.started_at = _utcnow()
            await db.flush()

        # 1. Resolve repository coordinates for real GitHub evidence
        repo_coords: str | None = None
        repo_id_str: str | None = None
        if incident.repository_id is not None:
            stmt = select(Repository).where(
                Repository.id == incident.repository_id,
                Repository.project_id == project.id,
            )
            incident_repo = (await db.execute(stmt)).scalar_one_or_none()
            if incident_repo is not None:
                repo_coords = incident_repo.full_name
                repo_id_str = str(incident_repo.id)

        if not repo_coords:
            stmt = select(Repository).where(
                Repository.project_id == project.id,
                Repository.is_active.is_(True),
            )
            active_repos = list((await db.execute(stmt)).scalars().all())
            if len(active_repos) == 1:
                repo_coords = active_repos[0].full_name
                repo_id_str = str(active_repos[0].id)

        # 2. Resolve User's GitHub OAuth token
        github_token: str | None = None
        target_user_id = investigation.initiated_by_id or project.owner_id
        if target_user_id:
            stmt = select(UserGitHubConnection).where(
                UserGitHubConnection.user_id == target_user_id
            )
            user_conn = (await db.execute(stmt)).scalar_one_or_none()
            if user_conn is not None:
                github_token = user_conn.access_token

        # 3. Build context with enriched metadata
        context = InvestigationService.build_orchestration_context(
            investigation,
            cancellation_token=cancellation_token,
        )
        if repo_coords:
            context.execution_metadata["github_repo"] = repo_coords
            context.execution_metadata["target_repo"] = repo_coords
        if repo_id_str:
            context.execution_metadata["repository_id"] = repo_id_str
        if incident.detected_at:
            context.execution_metadata["incident_detected_at"] = incident.detected_at.isoformat()
        if incident.title:
            context.execution_metadata["incident_title"] = incident.title
        if incident.description:
            context.execution_metadata["incident_description"] = incident.description
        if incident.severity:
            context.execution_metadata["incident_severity"] = incident.severity.value

        async def _default_sandbox_workspace_resolver(
            ctx: InvestigationContext,
            prop: FixProposal,
        ) -> str | Path | None:
            temp_dir = Path(tempfile.gettempdir()) / f"devdoc-ws-source-{ctx.investigation_id}-{ctx.execution_id}"
            temp_dir.mkdir(parents=True, exist_ok=True)
            for ch in prop.changes:
                if ch.target_path:
                    norm_path = ch.target_path.replace("\\", "/").lstrip("/")
                    full_path = temp_dir / norm_path
                    full_path.parent.mkdir(parents=True, exist_ok=True)
                    if not full_path.exists():
                        full_path.write_text("# Placeholder base file for verification\n", encoding="utf-8")
            return temp_dir

        # 4. Resolve GitHub client
        resolved_github_client = None
        if github_token or repo_coords:
            resolved_github_client = GitHubAPIClient(access_token=github_token)

        # 5. Resolve Docker Sandbox provider & workspace resolver
        sandbox_provider = None
        workspace_resolver = None
        verification_commands: list[VerificationCommand] = []
        if is_docker_available():
            sandbox_provider = create_default_docker_sandbox_provider()
            if sandbox_provider is not None:
                workspace_resolver = _default_sandbox_workspace_resolver
                verification_commands = [
                    VerificationCommand(step_index=0, argv=["python", "-m", "compileall", "."])
                ]

        async def _approval_recorder(ctx: InvestigationContext) -> uuid.UUID:
            if ctx.is_cancelled():
                raise RuntimeError("Investigation stopped before approval artifact recording")
            if (
                ctx.sandbox_verification_result is None
                or ctx.sandbox_verification_result.status != VerificationStatus.PASSED
            ):
                raise ValueError("Cannot record approval artifact for non-passing verification")
            return await ApprovalService.record_verified_artifact(db, ctx)

        engine = (
            orchestrator
            if orchestrator is not None
            else create_operational_orchestrator(
                config=settings,
                github_client=resolved_github_client,
                github_access_token=github_token,
                sandbox_provider=sandbox_provider,
                sandbox_workspace_resolver=workspace_resolver,
                verification_commands=verification_commands,
                approval_artifact_recorder=_approval_recorder,
            )
        )


        try:
            result = await engine.execute(context)
        except Exception as exc:
            logger.exception(
                "Investigation orchestrator execution failed with an unhandled exception",
                extra={
                    "investigation_id": str(investigation.id),
                    "incident_id": str(incident.id),
                    "project_id": str(project.id),
                },
            )
            await InvestigationService._persist_evidence(db, investigation, context)
            if context.is_cancelled():
                persisted_status = await db.scalar(
                    select(Investigation.status)
                    .where(Investigation.id == investigation.id)
                    .with_for_update()
                )
                if persisted_status != InvestigationStatus.CANCELLED:
                    investigation.status = InvestigationStatus.FAILED
                    investigation.completed_at = _utcnow()
                    investigation.error_message = f"Orchestrator execution error: {exc}"
                    await db.flush()
                    raise
                investigation.status = InvestigationStatus.CANCELLED
                investigation.completed_at = _utcnow()
                investigation.error_message = context.cancellation_token.reason or "Stopped by user"
                await db.flush()
                return InvestigationRunResult(
                    execution_id=context.execution_id,
                    investigation_id=investigation.id,
                    incident_id=incident.id,
                    project_id=project.id,
                    workflow_id="devdoc-investigation",
                    status=ExecutionStatus.CANCELLED,
                    error_message=investigation.error_message,
                    started_at=investigation.started_at,
                    completed_at=investigation.completed_at,
                    context=context,
                )
            investigation.status = InvestigationStatus.FAILED
            investigation.completed_at = _utcnow()
            investigation.error_message = f"Orchestrator execution error: {exc}"
            await db.flush()
            raise

        # 1. Persist valid evidence items
        evidence_count = await InvestigationService._persist_evidence(db, investigation, context)

        # 2. Persist RCA
        has_rca = InvestigationService._persist_rca(investigation, context)

        # 3. Persist Fix Proposal
        has_fix = await InvestigationService._persist_fix_proposal(db, investigation, context)

        # 4. Check and persist approval artifact if genuinely passed and not yet recorded
        artifact_id = context.approval_artifact_id
        if (
            artifact_id is None
            and not context.is_cancelled()
            and context.sandbox_verification_result is not None
            and context.sandbox_verification_result.status == VerificationStatus.PASSED
            and context.root_cause_analysis is not None
            and context.fix_proposal is not None
        ):
            try:
                artifact_id = await ApprovalService.record_verified_artifact(db, context)
                context.approval_artifact_id = artifact_id
                context.approval_status = "awaiting_human_review"
            except Exception as exc:
                logger.warning("Could not record verified approval artifact: %s", exc)

        # Do not report empty or undiagnosed runs as completed, even if a custom
        # orchestrator incorrectly returns SUCCESS for an incomplete pipeline.
        run_status = ExecutionStatus.CANCELLED if context.is_cancelled() else result.status
        run_error_message = (
            context.cancellation_token.reason if context.is_cancelled() else result.error_message
        )
        collected_evidence_count = (
            context.evidence_collection.summary.total_evidence_count
            if context.evidence_collection is not None
            else 0
        )
        if run_status == ExecutionStatus.SUCCESS and collected_evidence_count == 0:
            run_status = ExecutionStatus.FAILED
            run_error_message = "No evidence was collected. Confirm GitHub is connected and a repository is selected for this project, then retry."
        elif run_status == ExecutionStatus.SUCCESS and not has_rca:
            run_status = ExecutionStatus.FAILED
            run_error_message = (
                "The investigation could not produce a root cause diagnosis. Check that AI reasoning is configured, then retry."
            )

        # Lock the row while finalizing so a concurrent Stop request either wins
        # cleanly or observes the completed run without being overwritten.
        persisted_status = await db.scalar(
            select(Investigation.status)
            .where(Investigation.id == investigation.id)
            .with_for_update()
        )
        if persisted_status == InvestigationStatus.CANCELLED or context.is_cancelled():
            run_status = ExecutionStatus.CANCELLED
            run_error_message = context.cancellation_token.reason or "Stopped by user"

        # 5. Map execution result to Investigation lifecycle status
        if run_status == ExecutionStatus.SUCCESS:
            investigation.status = InvestigationStatus.COMPLETED
            investigation.completed_at = _utcnow()
            investigation.error_message = None
        elif run_status == ExecutionStatus.CANCELLED:
            investigation.status = InvestigationStatus.CANCELLED
            investigation.completed_at = _utcnow()
            if run_error_message:
                investigation.error_message = run_error_message
        else:
            investigation.status = InvestigationStatus.FAILED
            investigation.completed_at = _utcnow()
            investigation.error_message = run_error_message or "Investigation orchestration failed"

        await db.flush()
        await db.refresh(investigation)

        logger.info(
            "Investigation orchestration completed",
            extra={
                "investigation_id": str(investigation.id),
                "incident_id": str(incident.id),
                "project_id": str(project.id),
                "orchestration_status": run_status.value,
                "investigation_status": investigation.status.value,
                "evidence_count": evidence_count,
                "has_rca": has_rca,
                "has_fix": has_fix,
                "artifact_id": str(artifact_id) if artifact_id else None,
            },
        )

        return InvestigationRunResult(
            execution_id=result.execution_id,
            investigation_id=result.investigation_id,
            incident_id=result.incident_id,
            project_id=result.project_id,
            workflow_id=result.workflow_id,
            status=run_status,
            stage_results=result.stage_results,
            metadata=result.metadata,
            warnings=result.warnings,
            error_message=run_error_message,
            started_at=result.started_at,
            completed_at=result.completed_at,
            duration_ms=result.duration_ms,
            context=context,
            evidence_count=evidence_count,
            has_root_cause_analysis=has_rca,
            has_fix_proposal=has_fix,
            approval_artifact_id=artifact_id,
            approval_status=context.approval_status,
        )


