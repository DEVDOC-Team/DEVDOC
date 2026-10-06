"""Strict request and response contracts for incident chat history."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChatConversationCreate(BaseModel):
    title: str = Field(default="New conversation", min_length=1, max_length=200)
    investigation_id: uuid.UUID | None = None

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Title must contain non-whitespace characters")
        return normalized

    model_config = ConfigDict(extra="forbid")


class ChatConversationUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=200)

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Title must contain non-whitespace characters")
        return normalized

    model_config = ConfigDict(extra="forbid")


class ChatMessageCreate(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=20_000)

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Message content must contain non-whitespace characters")
        return value

    model_config = ConfigDict(extra="forbid")


class ChatConversationResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    incident_id: uuid.UUID
    investigation_id: uuid.UUID | None
    created_by_id: uuid.UUID | None
    title: str
    last_message_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChatConversationListResponse(BaseModel):
    items: list[ChatConversationResponse]
    total: int
    limit: int
    offset: int


class ChatMessageResponse(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChatMessageListResponse(BaseModel):
    items: list[ChatMessageResponse]
    total: int
    limit: int
    offset: int
