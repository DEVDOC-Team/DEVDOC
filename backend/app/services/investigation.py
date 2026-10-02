"""Investigation Service.

Encapsulates all business logic, lifecycle state transitions, and database operations
for DEVDOC investigations. Keeps route handlers thin and guarantees consistent
multi-level authorization (project + incident boundary) and data validation.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.db.base import _utcnow
from app.models.incident import Incident
from app.models.investigation import Investigation, InvestigationStatus
from app.models.project import Project
from app.models.user import User
from app.schemas.investigation import (
    InvestigationCreate,
    InvestigationStatusUpdate,
    InvestigationUpdate,
)
from orchestrator.core.context import InvestigationContext
from orchestrator.core.orchestrator import DEVDOCOrchestrator
from orchestrator.core.result import ExecutionStatus, OrchestrationResult

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
        )

    @staticmethod
    async def run_investigation_orchestration(
        db: AsyncSession,
        project: Project,
        incident: Incident,
        investigation: Investigation,
        orchestrator: DEVDOCOrchestrator | None = None,
    ) -> OrchestrationResult:
        """Execute the investigation orchestrator and persist final lifecycle state.

        Guarantees:
        - Must be in PENDING or RUNNING status prior to execution.
        - Automatically transitions PENDING -> RUNNING upon execution start.
        - Transitions to COMPLETED, FAILED, or CANCELLED based on OrchestrationResult.
        - Updates error_message and completed_at upon completion.
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

        engine = orchestrator if orchestrator is not None else DEVDOCOrchestrator()
        context = InvestigationService.build_orchestration_context(investigation)

        result = await engine.execute(context)

        # Map execution result to Investigation lifecycle status
        if result.status == ExecutionStatus.SUCCESS:
            investigation.status = InvestigationStatus.COMPLETED
            investigation.completed_at = _utcnow()
        elif result.status == ExecutionStatus.CANCELLED:
            investigation.status = InvestigationStatus.CANCELLED
            investigation.completed_at = _utcnow()
        else:
            investigation.status = InvestigationStatus.FAILED
            investigation.completed_at = _utcnow()
            if result.error_message:
                investigation.error_message = result.error_message

        await db.flush()
        await db.refresh(investigation)

        logger.info(
            "Investigation orchestration completed",
            extra={
                "investigation_id": str(investigation.id),
                "incident_id": str(incident.id),
                "project_id": str(project.id),
                "orchestration_status": result.status.value,
                "investigation_status": investigation.status.value,
            },
        )
        return result

