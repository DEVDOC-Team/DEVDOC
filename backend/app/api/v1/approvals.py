"""Authenticated Phase 18 approval and audit endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_authenticated_db, require_active_user, require_project_access
from app.models.project import Project
from app.models.user import User
from app.schemas.approval import (
    ApprovalAuditListResponse,
    ApprovalDecisionInput,
    ApprovalListResponse,
    ApprovalRequestCreate,
    ApprovalResponse,
)
from app.services.approval import ApprovalService

router = APIRouter(
    prefix="/projects/{project_id}/investigations/{investigation_id}/approvals",
    tags=["human-approval"],
)


@router.post("", response_model=ApprovalResponse, status_code=201)
@router.post("/", response_model=ApprovalResponse, status_code=201, include_in_schema=False)
async def create_approval_request(
    project_id: uuid.UUID,
    investigation_id: uuid.UUID,
    data: ApprovalRequestCreate,
    project: Project = Depends(require_project_access),
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_authenticated_db),
    request_id: Annotated[str | None, Header(alias="X-Request-ID")] = None,
) -> ApprovalResponse:
    return await ApprovalService.create_request(
        db, project, investigation_id, data.proposal_id, current_user, request_id
    )


@router.get("", response_model=ApprovalListResponse)
@router.get("/", response_model=ApprovalListResponse, include_in_schema=False)
async def list_approval_requests(
    project_id: uuid.UUID,
    investigation_id: uuid.UUID,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    project: Project = Depends(require_project_access),
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_authenticated_db),
    request_id: Annotated[str | None, Header(alias="X-Request-ID")] = None,
) -> ApprovalListResponse:
    items, total = await ApprovalService.list_requests(
        db, project, investigation_id, current_user, limit, offset, request_id
    )
    return ApprovalListResponse(items=items, total=total)


@router.get("/audit", response_model=ApprovalAuditListResponse)
async def list_approval_audit(
    project_id: uuid.UUID,
    investigation_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    project: Project = Depends(require_project_access),
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_authenticated_db),
) -> ApprovalAuditListResponse:
    items, total = await ApprovalService.list_audit_events(
        db, project, investigation_id, current_user, limit, offset
    )
    return ApprovalAuditListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/{approval_id}", response_model=ApprovalResponse)
async def get_approval_request(
    project_id: uuid.UUID,
    investigation_id: uuid.UUID,
    approval_id: uuid.UUID,
    project: Project = Depends(require_project_access),
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_authenticated_db),
    request_id: Annotated[str | None, Header(alias="X-Request-ID")] = None,
) -> ApprovalResponse:
    return await ApprovalService.get_request(
        db, project, investigation_id, approval_id, current_user, request_id
    )


@router.post("/{approval_id}/approve", response_model=ApprovalResponse)
async def approve_request(
    project_id: uuid.UUID,
    investigation_id: uuid.UUID,
    approval_id: uuid.UUID,
    data: ApprovalDecisionInput,
    project: Project = Depends(require_project_access),
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_authenticated_db),
    request_id: Annotated[str | None, Header(alias="X-Request-ID")] = None,
) -> ApprovalResponse:
    return await ApprovalService.approve(
        db,
        project,
        investigation_id,
        approval_id,
        current_user,
        data.reason,
        request_id,
    )


@router.post("/{approval_id}/reject", response_model=ApprovalResponse)
async def reject_request(
    project_id: uuid.UUID,
    investigation_id: uuid.UUID,
    approval_id: uuid.UUID,
    data: ApprovalDecisionInput,
    project: Project = Depends(require_project_access),
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_authenticated_db),
    request_id: Annotated[str | None, Header(alias="X-Request-ID")] = None,
) -> ApprovalResponse:
    return await ApprovalService.reject(
        db,
        project,
        investigation_id,
        approval_id,
        current_user,
        data.reason,
        request_id,
    )


@router.post("/{approval_id}/cancel", response_model=ApprovalResponse)
async def cancel_request(
    project_id: uuid.UUID,
    investigation_id: uuid.UUID,
    approval_id: uuid.UUID,
    data: ApprovalDecisionInput,
    project: Project = Depends(require_project_access),
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_authenticated_db),
    request_id: Annotated[str | None, Header(alias="X-Request-ID")] = None,
) -> ApprovalResponse:
    return await ApprovalService.cancel(
        db,
        project,
        investigation_id,
        approval_id,
        current_user,
        data.reason,
        request_id,
    )
