"""Project API router for DEVDOC."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_authenticated_db, require_active_user, require_project_access
from app.models.project import Project
from app.models.user import User
from app.schemas.project import (
    ProjectCreate,
    ProjectDeleteResponse,
    ProjectListResponse,
    ProjectResponse,
    ProjectUpdate,
)
from app.services.project import ProjectService

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED, include_in_schema=False)
async def create_project(
    project_in: ProjectCreate,
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_authenticated_db),
) -> ProjectResponse:
    """Create a new project owned by the authenticated user."""
    project = await ProjectService.create_project(db, current_user, project_in)
    return ProjectResponse.model_validate(project)


@router.get("", response_model=ProjectListResponse)
@router.get("/", response_model=ProjectListResponse, include_in_schema=False)
async def list_projects(
    limit: int = Query(50, ge=1, le=100, description="Page limit"),
    offset: int = Query(0, ge=0, description="Page offset"),
    include_inactive: bool = Query(False, description="Include soft-deleted inactive projects"),
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_authenticated_db),
) -> ProjectListResponse:
    """List all projects belonging to the authenticated user."""
    items, total = await ProjectService.list_user_projects(
        db=db,
        current_user=current_user,
        limit=limit,
        offset=offset,
        include_inactive=include_inactive,
    )
    return ProjectListResponse(
        items=[ProjectResponse.model_validate(p) for p in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: uuid.UUID,
    project: Project = Depends(require_project_access),
) -> ProjectResponse:
    """Retrieve an authorized project by its ID."""
    return ProjectResponse.model_validate(project)


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: uuid.UUID,
    project_update: ProjectUpdate,
    project: Project = Depends(require_project_access),
    db: AsyncSession = Depends(get_authenticated_db),
) -> ProjectResponse:
    """Update project metadata and settings."""
    updated_project = await ProjectService.update_project(db, project, project_update)
    return ProjectResponse.model_validate(updated_project)


@router.delete("/{project_id}", response_model=ProjectDeleteResponse)
async def delete_project(
    project_id: uuid.UUID,
    project: Project = Depends(require_project_access),
    db: AsyncSession = Depends(get_authenticated_db),
) -> ProjectDeleteResponse:
    """Delete an authorized project."""
    deleted_id = await ProjectService.delete_project(db, project)
    return ProjectDeleteResponse(
        success=True,
        message="Project deleted successfully",
        project_id=deleted_id,
    )
