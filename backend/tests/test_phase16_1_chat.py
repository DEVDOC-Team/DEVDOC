"""Phase 16.1 chat history persistence tests using isolated SQLite."""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.chat import ChatMessage
from app.models.incident import Incident
from app.models.investigation import Investigation
from app.models.project import Project
from app.models.user import User
from app.schemas.chat import ChatConversationCreate, ChatMessageCreate
from app.services.chat import ChatHistoryService

DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    engine = create_async_engine(DB_URL)
    async with engine.begin() as connection:
        await connection.execute(text("PRAGMA foreign_keys = ON"))
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def entities(db: AsyncSession) -> tuple[User, Project, Incident, Investigation]:
    user = User(email=f"{uuid.uuid4()}@example.test")
    db.add(user)
    await db.flush()
    project = Project(name="Example", slug=f"example-{uuid.uuid4().hex[:8]}", owner_id=user.id)
    db.add(project)
    await db.flush()
    incident = Incident(project_id=project.id, title="Elevated API errors")
    db.add(incident)
    await db.flush()
    investigation = Investigation(
        project_id=project.id,
        incident_id=incident.id,
        initiated_by_id=user.id,
    )
    db.add(investigation)
    await db.flush()
    return user, project, incident, investigation


@pytest.mark.asyncio
async def test_chat_history_round_trip_and_bounded_order(
    db: AsyncSession,
    entities: tuple[User, Project, Incident, Investigation],
) -> None:
    user, project, incident, investigation = entities
    conversation = await ChatHistoryService.create_conversation(
        db,
        project,
        incident,
        user,
        ChatConversationCreate(title="  Investigation discussion  ", investigation_id=investigation.id),
    )
    user_message = await ChatHistoryService.add_message(
        db,
        conversation,
        ChatMessageCreate(role="user", content="What changed before the alert?"),
    )
    assistant_message = await ChatHistoryService.add_message(
        db,
        conversation,
        ChatMessageCreate(role="assistant", content="The deployment changed worker settings."),
    )

    items, total = await ChatHistoryService.list_messages(db, conversation, limit=1, offset=0)
    assert total == 2
    assert items == [user_message]
    assert user_message.created_at <= assistant_message.created_at
    assert conversation.last_message_at is not None

    conversations, total_conversations = await ChatHistoryService.list_conversations(
        db, project, incident, limit=20, offset=0
    )
    assert total_conversations == 1
    assert conversations == [conversation]
    assert conversation.title == "Investigation discussion"


@pytest.mark.asyncio
async def test_chat_conversation_rejects_investigation_from_another_incident(
    db: AsyncSession,
    entities: tuple[User, Project, Incident, Investigation],
) -> None:
    user, project, incident, investigation = entities
    other_incident = Incident(project_id=project.id, title="Different incident")
    db.add(other_incident)
    await db.flush()
    other_investigation = Investigation(
        project_id=project.id,
        incident_id=other_incident.id,
        initiated_by_id=user.id,
    )
    db.add(other_investigation)
    await db.flush()

    with pytest.raises(HTTPException) as error:
        await ChatHistoryService.create_conversation(
            db,
            project,
            incident,
            user,
            ChatConversationCreate(investigation_id=other_investigation.id),
        )
    assert error.value.status_code == 404
    assert await db.scalar(text("SELECT count(*) FROM chat_conversations")) == 0
    assert investigation.id != other_investigation.id


@pytest.mark.asyncio
async def test_chat_messages_require_nonblank_content() -> None:
    with pytest.raises(ValueError):
        ChatMessageCreate(role="user", content="  ")
    with pytest.raises(ValueError):
        ChatMessageCreate.model_validate(
            {"role": "system", "content": "Hidden system instruction"}
        )


@pytest.mark.asyncio
async def test_database_rejects_cross_project_message_conversation_reference(
    db: AsyncSession,
    entities: tuple[User, Project, Incident, Investigation],
) -> None:
    user, project, incident, _ = entities
    conversation = await ChatHistoryService.create_conversation(
        db, project, incident, user, ChatConversationCreate()
    )
    message = ChatMessage(
        conversation_id=conversation.id,
        project_id=uuid.uuid4(),
        role="user",
        content="A forged project reference",
    )
    db.add(message)
    with pytest.raises(IntegrityError):
        await db.flush()
