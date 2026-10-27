"""Incident management API endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_authenticated_db, require_active_user, require_project_access
from app.models.incident import IncidentSeverity, IncidentSource, IncidentStatus
from app.models.project import Project
from app.models.user import User
from app.schemas.incident import (
    IncidentCreate,
    IncidentDeleteResponse,
    IncidentListResponse,
    IncidentResponse,
    IncidentStatusUpdate,
    IncidentUpdate,
)
from app.services.incident import IncidentService

router = APIRouter(prefix="/projects/{project_id}/incidents", tags=["incidents"])


@router.post("", response_model=IncidentResponse, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=IncidentResponse, status_code=status.HTTP_201_CREATED, include_in_schema=False)
async def create_incident(
    project_id: uuid.UUID,
    incident_in: IncidentCreate,
    project: Project = Depends(require_project_access),
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_authenticated_db),
) -> IncidentResponse:
    """Create a new incident within an authorized project.

    Project ownership and authorization is strictly enforced via require_project_access.
    project_id is sourced directly from the verified URL path, never from the client payload.
    """
    incident = await IncidentService.create_incident(
        db=db,
        project=project,
        current_user=current_user,
        data=incident_in,
    )
    return IncidentResponse.model_validate(incident)


@router.get("", response_model=IncidentListResponse)
@router.get("/", response_model=IncidentListResponse, include_in_schema=False)
async def list_incidents(
    project_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=100, description="Page size limit (max 100)"),
    offset: int = Query(0, ge=0, description="Page offset"),
    status: IncidentStatus | None = Query(None, description="Filter by incident status"),
    severity: IncidentSeverity | None = Query(None, description="Filter by incident severity"),
    source: IncidentSource | None = Query(None, description="Filter by incident source"),
    project: Project = Depends(require_project_access),
    db: AsyncSession = Depends(get_authenticated_db),
) -> IncidentListResponse:
    """List incidents belonging to the authorized project with bounded pagination and filtering."""
    items, total = await IncidentService.list_incidents(
        db=db,
        project=project,
        limit=limit,
        offset=offset,
        status_filter=status,
        severity_filter=severity,
        source_filter=source,
    )
    return IncidentListResponse(
        items=[IncidentResponse.model_validate(i) for i in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{incident_id}", response_model=IncidentResponse)
async def get_incident(
    project_id: uuid.UUID,
    incident_id: uuid.UUID,
    project: Project = Depends(require_project_access),
    db: AsyncSession = Depends(get_authenticated_db),
) -> IncidentResponse:
    """Retrieve details for a specific incident in the authorized project."""
    incident = await IncidentService.get_incident(
        db=db,
        project=project,
        incident_id=incident_id,
    )
    return IncidentResponse.model_validate(incident)


@router.patch("/{incident_id}", response_model=IncidentResponse)
async def update_incident(
    project_id: uuid.UUID,
    incident_id: uuid.UUID,
    update_in: IncidentUpdate,
    project: Project = Depends(require_project_access),
    db: AsyncSession = Depends(get_authenticated_db),
) -> IncidentResponse:
    """Update mutable fields on an incident.

    Validates lifecycle rules if a status change is included.
    """
    incident = await IncidentService.get_incident(db, project, incident_id)
    updated = await IncidentService.update_incident(
        db=db,
        project=project,
        incident=incident,
        data=update_in,
    )
    return IncidentResponse.model_validate(updated)


@router.patch("/{incident_id}/status", response_model=IncidentResponse)
async def transition_incident_status(
    project_id: uuid.UUID,
    incident_id: uuid.UUID,
    status_in: IncidentStatusUpdate,
    project: Project = Depends(require_project_access),
    db: AsyncSession = Depends(get_authenticated_db),
) -> IncidentResponse:
    """Dedicated endpoint to advance or roll back incident lifecycle status.

    Enforces strict transition state machine (OPEN -> INVESTIGATING -> MITIGATED -> RESOLVED -> CLOSED).
    """
    incident = await IncidentService.get_incident(db, project, incident_id)
    updated = await IncidentService.transition_incident_status(
        db=db,
        project=project,
        incident=incident,
        new_status=status_in.status,
    )
    return IncidentResponse.model_validate(updated)


@router.delete("/{incident_id}", response_model=IncidentDeleteResponse)
async def delete_incident(
    project_id: uuid.UUID,
    incident_id: uuid.UUID,
    project: Project = Depends(require_project_access),
    db: AsyncSession = Depends(get_authenticated_db),
) -> IncidentDeleteResponse:
    """Delete an incident within the authorized project."""
    incident = await IncidentService.get_incident(db, project, incident_id)
    deleted_id = await IncidentService.delete_incident(db, project, incident)
    return IncidentDeleteResponse(
        success=True,
        message="Incident deleted successfully",
        incident_id=deleted_id,
    )
