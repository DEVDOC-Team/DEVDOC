"""Project API router for DEVDOC."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_authenticated_db, require_active_user, require_project_access
from app.models.project import Project
from app.models.user import User
from app.schemas.github import (
    ProjectRepositoryAttach,
    ProjectRepositoryDeleteResponse,
    RepositoryResponse,
)
from app.schemas.project import (
    ProjectCreate,
    ProjectDeleteResponse,
    ProjectListResponse,
    ProjectResponse,
    ProjectUpdate,
)
from app.services.github import GitHubIntegrationService
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


# ---------------------------------------------------------------------------
# GitHub Repository Integration Endpoints (Phase 7)
# ---------------------------------------------------------------------------


@router.post(
    "/{project_id}/github/repository",
    response_model=RepositoryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def attach_github_repository(
    project_id: uuid.UUID,
    repo_in: ProjectRepositoryAttach,
    project: Project = Depends(require_project_access),
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_authenticated_db),
) -> RepositoryResponse:
    """Associate an authorized GitHub repository with the DEVDOC project.

    Verifies caller has access to the DEVDOC project (require_project_access)
    and that the user has an active GitHub connection with access to the repo.
    """
    repo = await GitHubIntegrationService.attach_repository_to_project(
        db=db,
        current_user=current_user,
        project=project,
        full_name=repo_in.full_name,
    )
    return RepositoryResponse.model_validate(repo)


@router.get(
    "/{project_id}/github/repository",
    response_model=RepositoryResponse,
)
async def get_project_github_repository(
    project_id: uuid.UUID,
    project: Project = Depends(require_project_access),
    db: AsyncSession = Depends(get_authenticated_db),
) -> RepositoryResponse:
    """Retrieve the connected GitHub repository for the project."""
    repo = await GitHubIntegrationService.get_project_repository(db, project)
    return RepositoryResponse.model_validate(repo)


@router.delete(
    "/{project_id}/github/repository",
    response_model=ProjectRepositoryDeleteResponse,
)
async def disconnect_project_github_repository(
    project_id: uuid.UUID,
    project: Project = Depends(require_project_access),
    db: AsyncSession = Depends(get_authenticated_db),
) -> ProjectRepositoryDeleteResponse:
    """Disconnect the GitHub repository from the DEVDOC project."""
    repo_id = await GitHubIntegrationService.disconnect_project_repository(db, project)
    return ProjectRepositoryDeleteResponse(
        success=True,
        message="Repository disconnected successfully from project",
        repository_id=repo_id,
    )


@router.get(
    "/{project_id}/github/branches",
    response_model=list[dict],
)
async def list_project_repository_branches(
    project_id: uuid.UUID,
    page: int = Query(1, ge=1),
    per_page: int = Query(30, ge=1, le=100),
    project: Project = Depends(require_project_access),
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_authenticated_db),
) -> list[dict]:
    """List branches for the connected GitHub repository."""
    return await GitHubIntegrationService.list_project_branches(
        db=db,
        user_id=current_user.id,
        project=project,
        page=page,
        per_page=per_page,
    )


@router.get(
    "/{project_id}/github/commits",
    response_model=list[dict],
)
async def list_project_repository_commits(
    project_id: uuid.UUID,
    sha: str | None = Query(None, description="SHA or branch to start listing commits from"),
    page: int = Query(1, ge=1),
    per_page: int = Query(30, ge=1, le=100),
    project: Project = Depends(require_project_access),
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_authenticated_db),
) -> list[dict]:
    """List commits on the connected GitHub repository."""
    return await GitHubIntegrationService.list_project_commits(
        db=db,
        user_id=current_user.id,
        project=project,
        sha=sha,
        page=page,
        per_page=per_page,
    )


@router.get(
    "/{project_id}/github/pulls",
    response_model=list[dict],
)
async def list_project_repository_pulls(
    project_id: uuid.UUID,
    state: str = Query("open", pattern=r"^(open|closed|all)$"),
    page: int = Query(1, ge=1),
    per_page: int = Query(30, ge=1, le=100),
    project: Project = Depends(require_project_access),
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_authenticated_db),
) -> list[dict]:
    """List pull requests on the connected GitHub repository."""
    return await GitHubIntegrationService.list_project_pulls(
        db=db,
        user_id=current_user.id,
        project=project,
        state=state,
        page=page,
        per_page=per_page,
    )


@router.get(
    "/{project_id}/github/issues",
    response_model=list[dict],
)
async def list_project_repository_issues(
    project_id: uuid.UUID,
    state: str = Query("open", pattern=r"^(open|closed|all)$"),
    page: int = Query(1, ge=1),
    per_page: int = Query(30, ge=1, le=100),
    project: Project = Depends(require_project_access),
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_authenticated_db),
) -> list[dict]:
    """List issues on the connected GitHub repository."""
    return await GitHubIntegrationService.list_project_issues(
        db=db,
        user_id=current_user.id,
        project=project,
        state=state,
        page=page,
        per_page=per_page,
    )


@router.get(
    "/{project_id}/github/contents",
)
async def get_project_repository_contents(
    project_id: uuid.UUID,
    path: str = Query(..., description="File path within the repository"),
    ref: str | None = Query(None, description="Git commit SHA, branch, or tag"),
    project: Project = Depends(require_project_access),
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_authenticated_db),
) -> dict:
    """Retrieve repository file contents or metadata for investigation."""
    return await GitHubIntegrationService.get_project_file_content(
        db=db,
        user_id=current_user.id,
        project=project,
        path=path,
        ref=ref,
    )


@router.get(
    "/{project_id}/github/workflows",
    response_model=dict,
)
async def list_project_repository_workflow_runs(
    project_id: uuid.UUID,
    page: int = Query(1, ge=1),
    per_page: int = Query(30, ge=1, le=100),
    project: Project = Depends(require_project_access),
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_authenticated_db),
) -> dict:
    """List GitHub Actions workflow runs for the connected repository."""
    return await GitHubIntegrationService.list_project_workflow_runs(
        db=db,
        user_id=current_user.id,
        project=project,
        page=page,
        per_page=per_page,
    )

