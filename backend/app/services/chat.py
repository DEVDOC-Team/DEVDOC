"""Business logic for incident-scoped chat conversations and durable history."""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import _utcnow
from app.models.chat import ChatConversation, ChatMessage
from app.models.incident import Incident
from app.models.investigation import Investigation
from app.models.project import Project
from app.models.user import User
from app.schemas.chat import ChatConversationCreate, ChatMessageCreate


class ChatHistoryService:
    """Project- and incident-bound persistence for chat history."""

    @staticmethod
    async def create_conversation(
        db: AsyncSession,
        project: Project,
        incident: Incident,
        current_user: User,
        data: ChatConversationCreate,
    ) -> ChatConversation:
        if data.investigation_id is not None:
            investigation = await db.scalar(
                select(Investigation).where(
                    Investigation.id == data.investigation_id,
                    Investigation.project_id == project.id,
                    Investigation.incident_id == incident.id,
                )
            )
            if investigation is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Investigation not found for this incident",
                )
        conversation = ChatConversation(
            id=uuid.uuid4(),
            project_id=project.id,
            incident_id=incident.id,
            investigation_id=data.investigation_id,
            created_by_id=current_user.id,
            title=data.title,
        )
        db.add(conversation)
        await db.flush()
        await db.refresh(conversation)
        return conversation

    @staticmethod
    async def list_conversations(
        db: AsyncSession,
        project: Project,
        incident: Incident,
        limit: int,
        offset: int,
    ) -> tuple[list[ChatConversation], int]:
        filters = (
            ChatConversation.project_id == project.id,
            ChatConversation.incident_id == incident.id,
        )
        total = int(
            await db.scalar(
                select(func.count()).select_from(ChatConversation).where(*filters)
            )
            or 0
        )
        items = list(
            (
                await db.scalars(
                    select(ChatConversation)
                    .where(*filters)
                    .order_by(
                        ChatConversation.updated_at.desc(),
                        ChatConversation.id.desc(),
                    )
                    .limit(limit)
                    .offset(offset)
                )
            ).all()
        )
        return items, total

    @staticmethod
    async def get_conversation(
        db: AsyncSession,
        project: Project,
        incident: Incident,
        conversation_id: uuid.UUID,
    ) -> ChatConversation:
        conversation = await db.scalar(
            select(ChatConversation).where(
                ChatConversation.id == conversation_id,
                ChatConversation.project_id == project.id,
                ChatConversation.incident_id == incident.id,
            )
        )
        if conversation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chat conversation not found",
            )
        return conversation

    @staticmethod
    async def rename_conversation(
        db: AsyncSession,
        conversation: ChatConversation,
        title: str,
    ) -> ChatConversation:
        conversation.title = title
        await db.flush()
        await db.refresh(conversation)
        return conversation

    @staticmethod
    async def delete_conversation(
        db: AsyncSession,
        conversation: ChatConversation,
    ) -> uuid.UUID:
        conversation_id = conversation.id
        await db.delete(conversation)
        await db.flush()
        return conversation_id

    @staticmethod
    async def list_messages(
        db: AsyncSession,
        conversation: ChatConversation,
        limit: int,
        offset: int,
    ) -> tuple[list[ChatMessage], int]:
        filters = (ChatMessage.conversation_id == conversation.id,)
        total = int(
            await db.scalar(select(func.count()).select_from(ChatMessage).where(*filters))
            or 0
        )
        items = list(
            (
                await db.scalars(
                    select(ChatMessage)
                    .where(*filters)
                    .order_by(ChatMessage.created_at, ChatMessage.id)
                    .limit(limit)
                    .offset(offset)
                )
            ).all()
        )
        return items, total

    @staticmethod
    async def add_message(
        db: AsyncSession,
        conversation: ChatConversation,
        data: ChatMessageCreate,
    ) -> ChatMessage:
        now = _utcnow()
        message = ChatMessage(
            id=uuid.uuid4(),
            conversation_id=conversation.id,
            project_id=conversation.project_id,
            role=data.role,
            content=data.content,
            created_at=now,
        )
        conversation.last_message_at = now
        db.add(message)
        await db.flush()
        await db.refresh(message)
        return message
