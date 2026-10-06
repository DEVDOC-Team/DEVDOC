"""Incident-scoped chat history API."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_authenticated_db, require_active_user, require_project_access
from app.models.project import Project
from app.models.user import User
from app.schemas.chat import (
    ChatConversationCreate,
    ChatConversationListResponse,
    ChatConversationResponse,
    ChatConversationUpdate,
    ChatMessageCreate,
    ChatMessageListResponse,
    ChatMessageResponse,
)
from app.services.chat import ChatHistoryService
from app.services.investigation import InvestigationService

router = APIRouter(
    prefix="/projects/{project_id}/incidents/{incident_id}/conversations",
    tags=["chat-history"],
)


@router.post("", response_model=ChatConversationResponse, status_code=status.HTTP_201_CREATED)
@router.post(
    "/", response_model=ChatConversationResponse, status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
async def create_conversation(
    project_id: uuid.UUID,
    incident_id: uuid.UUID,
    data: ChatConversationCreate,
    project: Project = Depends(require_project_access),
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_authenticated_db),
) -> ChatConversationResponse:
    incident = await InvestigationService.get_incident_for_project(db, project, incident_id)
    conversation = await ChatHistoryService.create_conversation(
        db, project, incident, current_user, data
    )
    return ChatConversationResponse.model_validate(conversation)


@router.get("", response_model=ChatConversationListResponse)
@router.get("/", response_model=ChatConversationListResponse, include_in_schema=False)
async def list_conversations(
    project_id: uuid.UUID,
    incident_id: uuid.UUID,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    project: Project = Depends(require_project_access),
    db: AsyncSession = Depends(get_authenticated_db),
) -> ChatConversationListResponse:
    incident = await InvestigationService.get_incident_for_project(db, project, incident_id)
    items, total = await ChatHistoryService.list_conversations(
        db, project, incident, limit, offset
    )
    return ChatConversationListResponse(
        items=[ChatConversationResponse.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{conversation_id}", response_model=ChatConversationResponse)
async def get_conversation(
    project_id: uuid.UUID,
    incident_id: uuid.UUID,
    conversation_id: uuid.UUID,
    project: Project = Depends(require_project_access),
    db: AsyncSession = Depends(get_authenticated_db),
) -> ChatConversationResponse:
    incident = await InvestigationService.get_incident_for_project(db, project, incident_id)
    conversation = await ChatHistoryService.get_conversation(
        db, project, incident, conversation_id
    )
    return ChatConversationResponse.model_validate(conversation)


@router.patch("/{conversation_id}", response_model=ChatConversationResponse)
async def rename_conversation(
    project_id: uuid.UUID,
    incident_id: uuid.UUID,
    conversation_id: uuid.UUID,
    data: ChatConversationUpdate,
    project: Project = Depends(require_project_access),
    db: AsyncSession = Depends(get_authenticated_db),
) -> ChatConversationResponse:
    incident = await InvestigationService.get_incident_for_project(db, project, incident_id)
    conversation = await ChatHistoryService.get_conversation(
        db, project, incident, conversation_id
    )
    updated = await ChatHistoryService.rename_conversation(db, conversation, data.title)
    return ChatConversationResponse.model_validate(updated)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    project_id: uuid.UUID,
    incident_id: uuid.UUID,
    conversation_id: uuid.UUID,
    project: Project = Depends(require_project_access),
    db: AsyncSession = Depends(get_authenticated_db),
) -> Response:
    incident = await InvestigationService.get_incident_for_project(db, project, incident_id)
    conversation = await ChatHistoryService.get_conversation(
        db, project, incident, conversation_id
    )
    await ChatHistoryService.delete_conversation(db, conversation)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{conversation_id}/messages", response_model=ChatMessageListResponse)
async def list_messages(
    project_id: uuid.UUID,
    incident_id: uuid.UUID,
    conversation_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    project: Project = Depends(require_project_access),
    db: AsyncSession = Depends(get_authenticated_db),
) -> ChatMessageListResponse:
    incident = await InvestigationService.get_incident_for_project(db, project, incident_id)
    conversation = await ChatHistoryService.get_conversation(
        db, project, incident, conversation_id
    )
    items, total = await ChatHistoryService.list_messages(db, conversation, limit, offset)
    return ChatMessageListResponse(
        items=[ChatMessageResponse.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/{conversation_id}/messages",
    response_model=ChatMessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_message(
    project_id: uuid.UUID,
    incident_id: uuid.UUID,
    conversation_id: uuid.UUID,
    data: ChatMessageCreate,
    project: Project = Depends(require_project_access),
    db: AsyncSession = Depends(get_authenticated_db),
) -> ChatMessageResponse:
    incident = await InvestigationService.get_incident_for_project(db, project, incident_id)
    conversation = await ChatHistoryService.get_conversation(
        db, project, incident, conversation_id
    )
    message = await ChatHistoryService.add_message(db, conversation, data)
    return ChatMessageResponse.model_validate(message)
