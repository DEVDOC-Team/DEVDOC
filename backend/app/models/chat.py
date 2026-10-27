"""Incident-scoped chat history models for Phase 16.1."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin, _utcnow


class ChatConversation(UUIDMixin, TimestampMixin, Base):
    """A user-visible conversation associated with an incident/investigation."""

    __tablename__ = "chat_conversations"
    __table_args__ = (
        UniqueConstraint("id", "project_id", name="uq_chat_conversations_id_project"),
        Index(
            "ix_chat_conversations_project_incident_updated",
            "project_id",
            "incident_id",
            "updated_at",
        ),
        ForeignKeyConstraint(
            ["incident_id", "project_id"],
            ["incidents.id", "incidents.project_id"],
            ondelete="CASCADE",
            name="fk_chat_conversations_incident_project",
        ),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    incident_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    investigation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("investigations.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="New conversation")
    last_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    messages: Mapped[list[ChatMessage]] = relationship(
        "ChatMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ChatMessage.created_at, ChatMessage.id",
    )

class ChatMessage(UUIDMixin, Base):
    """A bounded user or assistant message in a conversation."""

    __tablename__ = "chat_messages"
    __table_args__ = (
        ForeignKeyConstraint(
            ["conversation_id", "project_id"],
            ["chat_conversations.id", "chat_conversations.project_id"],
            ondelete="CASCADE",
            name="fk_chat_messages_conversation_project",
        ),
        CheckConstraint(
            "role IN ('user', 'assistant')",
            name="ck_chat_messages_role",
        ),
        Index("ix_chat_messages_conversation_created", "conversation_id", "created_at", "id"),
    )

    conversation_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=func.now(),
    )

    conversation: Mapped[ChatConversation] = relationship(
        "ChatConversation",
        back_populates="messages",
    )
