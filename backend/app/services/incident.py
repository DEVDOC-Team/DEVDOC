"""Incident Management Service.

Encapsulates all business logic, lifecycle transitions, and database operations
for DEVDOC incidents. Keeps route handlers thin and guarantees consistent
authorization and data validation.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.db.base import _utcnow
from app.models.incident import Incident, IncidentSeverity, IncidentSource, IncidentStatus
from app.models.project import Project
from app.models.repository import Repository
from app.models.user import User
from app.schemas.incident import IncidentCreate, IncidentUpdate

# ---------------------------------------------------------------------------
# Allowed Status Lifecycle Transitions
# ---------------------------------------------------------------------------

VALID_TRANSITIONS: dict[IncidentStatus, set[IncidentStatus]] = {
    IncidentStatus.OPEN: {IncidentStatus.INVESTIGATING, IncidentStatus.RESOLVED},
    IncidentStatus.INVESTIGATING: {IncidentStatus.MITIGATED, IncidentStatus.RESOLVED, IncidentStatus.OPEN},
    IncidentStatus.MITIGATED: {IncidentStatus.RESOLVED, IncidentStatus.INVESTIGATING},
    IncidentStatus.RESOLVED: {IncidentStatus.CLOSED, IncidentStatus.OPEN, IncidentStatus.INVESTIGATING},
    IncidentStatus.CLOSED: {IncidentStatus.OPEN},
}


def validate_status_transition(current_status: IncidentStatus, target_status: IncidentStatus) -> None:
    """Validate status transition against the allowed operational lifecycle.

    Raises:
        HTTPException(422): If the requested transition is not permitted.
    """
    if current_status == target_status:
        return

    allowed = VALID_TRANSITIONS.get(current_status, set())
    if target_status not in allowed:
        allowed_names = sorted(s.value for s in allowed)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Invalid status transition from '{current_status.value}' to '{target_status.value}'. "
                f"Allowed transitions from '{current_status.value}' are: {allowed_names}"
            ),
        )


class IncidentService:
    """Service handling Incident creation, listing, retrieval, updates, and transitions."""

    @staticmethod
    async def create_incident(
        db: AsyncSession,
        project: Project,
        current_user: User,
        data: IncidentCreate,
    ) -> Incident:
        """Create a new incident anchored strictly to the specified project and reporting user."""
        # Optional repository link validation
        if data.repository_id is not None:
            repo_stmt = select(Repository).where(
                Repository.id == data.repository_id,
                Repository.project_id == project.id,
            )
            repo = (await db.execute(repo_stmt)).scalar_one_or_none()
            if repo is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Repository '{data.repository_id}' does not belong to this project",
                )

        detected_at = data.detected_at or _utcnow()

        incident = Incident(
            id=uuid.uuid4(),
            project_id=project.id,
            repository_id=data.repository_id,
            reported_by_id=current_user.id,
            title=data.title.strip(),
            description=data.description,
            severity=data.severity,
            status=data.status,
            source=data.source,
            external_ref=data.external_reference,
            affected_users=data.affected_users,
            detected_at=detected_at,
            resolved_at=_utcnow() if data.status in (IncidentStatus.RESOLVED, IncidentStatus.CLOSED) else None,
        )

        db.add(incident)
        await db.commit()
        await db.refresh(incident)

        logger.info(
            "Created incident '%s' (%s) in project %s by user %s",
            incident.title,
            incident.id,
            project.id,
            current_user.id,
        )
        return incident

    @staticmethod
    async def list_incidents(
        db: AsyncSession,
        project: Project,
        limit: int = 50,
        offset: int = 0,
        status_filter: IncidentStatus | None = None,
        severity_filter: IncidentSeverity | None = None,
        source_filter: IncidentSource | None = None,
    ) -> tuple[list[Incident], int]:
        """List incidents for a project with bounded pagination and optional filtering."""
        # Enforce bounded limit
        bounded_limit = min(max(1, limit), 100)
        bounded_offset = max(0, offset)

        conditions: list[Any] = [Incident.project_id == project.id]
        if status_filter is not None:
            conditions.append(Incident.status == status_filter)
        if severity_filter is not None:
            conditions.append(Incident.severity == severity_filter)
        if source_filter is not None:
            conditions.append(Incident.source == source_filter)

        count_stmt = select(func.count()).select_from(Incident).where(*conditions)
        total = (await db.execute(count_stmt)).scalar() or 0

        query_stmt = (
            select(Incident)
            .where(*conditions)
            .order_by(Incident.created_at.desc())
            .limit(bounded_limit)
            .offset(bounded_offset)
        )
        items = list((await db.execute(query_stmt)).scalars().all())

        return items, total

    @staticmethod
    async def get_incident(
        db: AsyncSession,
        project: Project,
        incident_id: uuid.UUID,
    ) -> Incident:
        """Retrieve an authorized incident by its ID within the project scope."""
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
    async def update_incident(
        db: AsyncSession,
        project: Project,
        incident: Incident,
        data: IncidentUpdate,
    ) -> Incident:
        """Update mutable fields of an existing incident."""
        # Validate repository link if provided
        if data.repository_id is not None:
            repo_stmt = select(Repository).where(
                Repository.id == data.repository_id,
                Repository.project_id == project.id,
            )
            repo = (await db.execute(repo_stmt)).scalar_one_or_none()
            if repo is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Repository '{data.repository_id}' does not belong to this project",
                )
            incident.repository_id = data.repository_id

        # Lifecycle transition check if status is modified
        if data.status is not None and data.status != incident.status:
            validate_status_transition(incident.status, data.status)
            incident.status = data.status
            if data.status in (IncidentStatus.RESOLVED, IncidentStatus.CLOSED):
                if not incident.resolved_at:
                    incident.resolved_at = _utcnow()
            else:
                incident.resolved_at = None

        if data.title is not None:
            incident.title = data.title.strip()
        if data.description is not None:
            incident.description = data.description
        if data.severity is not None:
            incident.severity = data.severity
        if data.source is not None:
            incident.source = data.source
        if data.external_reference is not None:
            incident.external_ref = data.external_reference
        if data.affected_users is not None:
            incident.affected_users = data.affected_users

        await db.commit()
        await db.refresh(incident)

        logger.info("Updated incident %s in project %s", incident.id, project.id)
        return incident

    @staticmethod
    async def transition_incident_status(
        db: AsyncSession,
        project: Project,
        incident: Incident,
        new_status: IncidentStatus,
    ) -> Incident:
        """Execute a validated lifecycle status transition."""
        if new_status == incident.status:
            return incident

        validate_status_transition(incident.status, new_status)
        old_status = incident.status
        incident.status = new_status

        if new_status in (IncidentStatus.RESOLVED, IncidentStatus.CLOSED):
            if not incident.resolved_at:
                incident.resolved_at = _utcnow()
        else:
            incident.resolved_at = None

        await db.commit()
        await db.refresh(incident)

        logger.info(
            "Transitioned incident %s status from %s to %s in project %s",
            incident.id,
            old_status.value,
            new_status.value,
            project.id,
        )
        return incident

    @staticmethod
    async def delete_incident(
        db: AsyncSession,
        project: Project,
        incident: Incident,
    ) -> uuid.UUID:
        """Delete an incident from the project."""
        incident_id = incident.id
        await db.delete(incident)
        await db.commit()

        logger.info("Deleted incident %s from project %s", incident_id, project.id)
        return incident_id
