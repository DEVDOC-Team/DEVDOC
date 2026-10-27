"""Investigation API endpoints.

Mounts under: /api/v1/projects/{project_id}/incidents/{incident_id}/investigations
Guarantees strict multi-level authorization: project-access boundary + incident validation.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_authenticated_db, require_active_user, require_project_access
from app.models.investigation import InvestigationStatus
from app.models.project import Project
from app.models.user import User
from app.schemas.investigation import (
    InvestigationCreate,
    InvestigationDeleteResponse,
    InvestigationListResponse,
    InvestigationResponse,
    InvestigationRunResponse,
    InvestigationStatusUpdate,
    InvestigationUpdate,
)
from app.services.investigation import InvestigationService

router = APIRouter(
    prefix="/projects/{project_id}/incidents/{incident_id}/investigations",
    tags=["investigations"],
)


@router.post("", response_model=InvestigationResponse, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=InvestigationResponse, status_code=status.HTTP_201_CREATED, include_in_schema=False)
async def create_investigation(
    project_id: uuid.UUID,
    incident_id: uuid.UUID,
    investigation_in: InvestigationCreate,
    project: Project = Depends(require_project_access),
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_authenticated_db),
) -> InvestigationResponse:
    """Create a new investigation for an incident within an authorized project.

    Enforces dual-boundary checks:
    1. Authenticated user has access to project_id.
    2. incident_id exists and strictly belongs to project_id.
    3. project_id and incident_id cannot be spoofed in request bodies.
    """
    incident = await InvestigationService.get_incident_for_project(
        db=db,
        project=project,
        incident_id=incident_id,
    )
    investigation = await InvestigationService.create_investigation(
        db=db,
        project=project,
        incident=incident,
        current_user=current_user,
        data=investigation_in,
    )
    return InvestigationResponse.model_validate(investigation)


@router.get("", response_model=InvestigationListResponse)
@router.get("/", response_model=InvestigationListResponse, include_in_schema=False)
async def list_investigations(
    project_id: uuid.UUID,
    incident_id: uuid.UUID,
    limit: int = Query(20, ge=1, le=100, description="Page size limit (max 100)"),
    offset: int = Query(0, ge=0, description="Page offset"),
    status: InvestigationStatus | None = Query(None, description="Filter by status"),
    project: Project = Depends(require_project_access),
    db: AsyncSession = Depends(get_authenticated_db),
) -> InvestigationListResponse:
    """List investigations for the specified incident with bounded pagination and optional filtering."""
    incident = await InvestigationService.get_incident_for_project(
        db=db,
        project=project,
        incident_id=incident_id,
    )
    items, total = await InvestigationService.list_investigations(
        db=db,
        project=project,
        incident=incident,
        limit=limit,
        offset=offset,
        status_filter=status,
    )
    return InvestigationListResponse(
        items=[InvestigationResponse.model_validate(i) for i in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{investigation_id}", response_model=InvestigationResponse)
async def get_investigation(
    project_id: uuid.UUID,
    incident_id: uuid.UUID,
    investigation_id: uuid.UUID,
    project: Project = Depends(require_project_access),
    db: AsyncSession = Depends(get_authenticated_db),
) -> InvestigationResponse:
    """Retrieve details for a specific investigation belonging to the verified incident."""
    incident = await InvestigationService.get_incident_for_project(
        db=db,
        project=project,
        incident_id=incident_id,
    )
    investigation = await InvestigationService.get_investigation(
        db=db,
        project=project,
        incident=incident,
        investigation_id=investigation_id,
    )
    return InvestigationResponse.model_validate(investigation)


@router.patch("/{investigation_id}", response_model=InvestigationResponse)
async def update_investigation(
    project_id: uuid.UUID,
    incident_id: uuid.UUID,
    investigation_id: uuid.UUID,
    update_in: InvestigationUpdate,
    project: Project = Depends(require_project_access),
    db: AsyncSession = Depends(get_authenticated_db),
) -> InvestigationResponse:
    """Update mutable fields on an investigation.

    Validates lifecycle rules if a status change is included in the payload.
    """
    incident = await InvestigationService.get_incident_for_project(
        db=db,
        project=project,
        incident_id=incident_id,
    )
    investigation = await InvestigationService.get_investigation(
        db=db,
        project=project,
        incident=incident,
        investigation_id=investigation_id,
    )
    updated = await InvestigationService.update_investigation(
        db=db,
        project=project,
        incident=incident,
        investigation=investigation,
        data=update_in,
    )
    return InvestigationResponse.model_validate(updated)


@router.patch("/{investigation_id}/status", response_model=InvestigationResponse)
async def transition_investigation_status(
    project_id: uuid.UUID,
    incident_id: uuid.UUID,
    investigation_id: uuid.UUID,
    status_in: InvestigationStatusUpdate,
    project: Project = Depends(require_project_access),
    db: AsyncSession = Depends(get_authenticated_db),
) -> InvestigationResponse:
    """Dedicated endpoint to advance or cancel investigation status.

    Enforces finite state machine transitions (PENDING -> RUNNING -> COMPLETED/FAILED/CANCELLED).
    """
    incident = await InvestigationService.get_incident_for_project(
        db=db,
        project=project,
        incident_id=incident_id,
    )
    investigation = await InvestigationService.get_investigation(
        db=db,
        project=project,
        incident=incident,
        investigation_id=investigation_id,
    )
    updated = await InvestigationService.transition_investigation_status(
        db=db,
        project=project,
        incident=incident,
        investigation=investigation,
        status_data=status_in,
    )
    return InvestigationResponse.model_validate(updated)


@router.delete("/{investigation_id}", response_model=InvestigationDeleteResponse)
async def delete_investigation(
    project_id: uuid.UUID,
    incident_id: uuid.UUID,
    investigation_id: uuid.UUID,
    project: Project = Depends(require_project_access),
    db: AsyncSession = Depends(get_authenticated_db),
) -> InvestigationDeleteResponse:
    """Delete an investigation within the authorized project and incident."""
    incident = await InvestigationService.get_incident_for_project(
        db=db,
        project=project,
        incident_id=incident_id,
    )
    investigation = await InvestigationService.get_investigation(
        db=db,
        project=project,
        incident=incident,
        investigation_id=investigation_id,
    )
    deleted_id = await InvestigationService.delete_investigation(
        db=db,
        project=project,
        incident=incident,
        investigation=investigation,
    )
    return InvestigationDeleteResponse(
        success=True,
        message="Investigation deleted successfully",
        investigation_id=deleted_id,
    )


@router.post("/{investigation_id}/run", response_model=InvestigationRunResponse)
@router.post("/{investigation_id}/run/", response_model=InvestigationRunResponse, include_in_schema=False)
async def run_investigation(
    project_id: uuid.UUID,
    incident_id: uuid.UUID,
    investigation_id: uuid.UUID,
    project: Project = Depends(require_project_access),
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_authenticated_db),
) -> InvestigationRunResponse:
    """Trigger an operational investigation run synchronously and persist its results.

    Enforces:
    1. Authenticated user has access to project_id (enforced by require_project_access & RLS).
    2. incident_id exists and strictly belongs to project_id.
    3. investigation_id exists and strictly belongs to incident_id.
    4. Lifecycle validation: rejects terminal investigations (422) or already running investigations (409).
    5. Persists collected evidence, root-cause summary, fix proposal, and verified approval artifact.
    """
    incident = await InvestigationService.get_incident_for_project(
        db=db,
        project=project,
        incident_id=incident_id,
    )
    investigation = await InvestigationService.get_investigation(
        db=db,
        project=project,
        incident=incident,
        investigation_id=investigation_id,
    )

    if investigation.status == InvestigationStatus.RUNNING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Investigation '{investigation.id}' is already running",
        )

    result = await InvestigationService.run_investigation_orchestration(
        db=db,
        project=project,
        incident=incident,
        investigation=investigation,
    )

    base_resp = InvestigationResponse.model_validate(investigation)
    return InvestigationRunResponse(
        **base_resp.model_dump(),
        evidence_count=getattr(result, "evidence_count", 0),
        has_root_cause_analysis=getattr(result, "has_root_cause_analysis", False),
        has_fix_proposal=getattr(result, "has_fix_proposal", False),
        approval_artifact_id=getattr(result, "approval_artifact_id", None),
        approval_status=getattr(result, "approval_status", None),
    )

