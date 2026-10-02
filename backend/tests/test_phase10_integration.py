"""Tests for Phase 10 orchestrator integration with InvestigationService."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.incident import Incident, IncidentSeverity, IncidentStatus
from app.models.investigation import Investigation, InvestigationStatus
from app.models.project import Project
from app.models.user import User
from app.services.investigation import InvestigationService
from orchestrator.contracts.execution import FailurePolicy, WorkflowDefinition
from orchestrator.contracts.stage import BaseStage
from orchestrator.core.context import InvestigationContext
from orchestrator.core.orchestrator import DEVDOCOrchestrator
from orchestrator.core.result import ExecutionStatus, StageResult
from orchestrator.stages.registry import StageRegistry

SQLITE_TEST_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="function")
async def sqlite_engine():
    engine = create_async_engine(SQLITE_TEST_URL, echo=False, future=True)
    async with engine.begin() as conn:
        await conn.execute(text("PRAGMA foreign_keys = ON"))
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def async_db_session(sqlite_engine) -> AsyncGenerator[AsyncSession]:
    factory = async_sessionmaker(
        bind=sqlite_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with factory() as session:
        yield session


class FailingCustomStage(BaseStage):
    @property
    def stage_id(self) -> str:
        return "failing_stage"

    @property
    def name(self) -> str:
        return "Failing Stage"

    async def execute(self, context: InvestigationContext) -> StageResult:
        return StageResult(
            stage_id=self.stage_id,
            status=ExecutionStatus.FAILED,
            error_message="Simulation engine failure",
        )


@pytest.mark.asyncio
async def test_build_orchestration_context_from_model() -> None:
    user_id = uuid.uuid4()
    proj_id = uuid.uuid4()
    inc_id = uuid.uuid4()
    inv_id = uuid.uuid4()

    inv = Investigation(
        id=inv_id,
        project_id=proj_id,
        incident_id=inc_id,
        initiated_by_id=user_id,
        status=InvestigationStatus.PENDING,
        tokens_used=0,
        estimated_cost_usd=0,
    )

    ctx = InvestigationService.build_orchestration_context(inv)
    assert ctx.investigation_id == inv_id
    assert ctx.incident_id == inc_id
    assert ctx.project_id == proj_id
    assert ctx.initiated_by_id == user_id
    assert isinstance(ctx.execution_id, uuid.UUID)


@pytest.mark.asyncio
async def test_service_run_orchestration_success_lifecycle(
    async_db_session: AsyncSession,
) -> None:
    user = User(id=uuid.uuid4(), email="investigator@devdoc.io", is_active=True)
    async_db_session.add(user)
    await async_db_session.flush()

    project = Project(id=uuid.uuid4(), name="Test Project", slug="test-project", owner_id=user.id)
    async_db_session.add(project)
    await async_db_session.flush()

    incident = Incident(
        id=uuid.uuid4(),
        project_id=project.id,
        reported_by_id=user.id,
        title="Outage in worker",
        status=IncidentStatus.OPEN,
        severity=IncidentSeverity.HIGH,
    )
    async_db_session.add(incident)
    await async_db_session.flush()

    investigation = Investigation(
        id=uuid.uuid4(),
        project_id=project.id,
        incident_id=incident.id,
        initiated_by_id=user.id,
        status=InvestigationStatus.PENDING,
        tokens_used=0,
        estimated_cost_usd=0,
    )
    async_db_session.add(investigation)
    await async_db_session.flush()

    # Run orchestration
    result = await InvestigationService.run_investigation_orchestration(
        db=async_db_session,
        project=project,
        incident=incident,
        investigation=investigation,
    )

    assert result.status == ExecutionStatus.SUCCESS
    assert investigation.status == InvestigationStatus.COMPLETED
    assert investigation.started_at is not None
    assert investigation.completed_at is not None
    assert investigation.error_message is None


@pytest.mark.asyncio
async def test_service_run_orchestration_failure_lifecycle(
    async_db_session: AsyncSession,
) -> None:
    user = User(id=uuid.uuid4(), email="investigator2@devdoc.io", is_active=True)
    async_db_session.add(user)
    await async_db_session.flush()

    project = Project(id=uuid.uuid4(), name="Project 2", slug="project-2", owner_id=user.id)
    async_db_session.add(project)
    await async_db_session.flush()

    incident = Incident(
        id=uuid.uuid4(),
        project_id=project.id,
        reported_by_id=user.id,
        title="Service unreachable",
        status=IncidentStatus.OPEN,
        severity=IncidentSeverity.CRITICAL,
    )
    async_db_session.add(incident)
    await async_db_session.flush()

    investigation = Investigation(
        id=uuid.uuid4(),
        project_id=project.id,
        incident_id=incident.id,
        initiated_by_id=user.id,
        status=InvestigationStatus.RUNNING,
        tokens_used=0,
        estimated_cost_usd=0,
    )
    async_db_session.add(investigation)
    await async_db_session.flush()

    reg = StageRegistry()
    reg.register(FailingCustomStage())
    wf = WorkflowDefinition(
        workflow_id="failing_wf",
        name="Failing Pipeline",
        stage_ids=["failing_stage"],
        failure_policy=FailurePolicy.FAIL_FAST,
    )
    orch = DEVDOCOrchestrator(registry=reg, workflow=wf)

    result = await InvestigationService.run_investigation_orchestration(
        db=async_db_session,
        project=project,
        incident=incident,
        investigation=investigation,
        orchestrator=orch,
    )

    assert result.status == ExecutionStatus.FAILED
    assert investigation.status == InvestigationStatus.FAILED
    assert investigation.completed_at is not None
    assert "Simulation engine failure" in (investigation.error_message or "")


@pytest.mark.asyncio
async def test_service_run_orchestration_terminal_status_rejected(
    async_db_session: AsyncSession,
) -> None:
    user = User(id=uuid.uuid4(), email="investigator3@devdoc.io", is_active=True)

    async_db_session.add(user)
    await async_db_session.flush()

    project = Project(id=uuid.uuid4(), name="Project 3", slug="project-3", owner_id=user.id)
    async_db_session.add(project)
    await async_db_session.flush()

    incident = Incident(
        id=uuid.uuid4(),
        project_id=project.id,
        reported_by_id=user.id,
        title="Incident 3",
        status=IncidentStatus.OPEN,
        severity=IncidentSeverity.LOW,
    )
    async_db_session.add(incident)
    await async_db_session.flush()

    investigation = Investigation(
        id=uuid.uuid4(),
        project_id=project.id,
        incident_id=incident.id,
        initiated_by_id=user.id,
        status=InvestigationStatus.COMPLETED,
        tokens_used=0,
        estimated_cost_usd=0,
    )
    async_db_session.add(investigation)
    await async_db_session.flush()

    with pytest.raises(HTTPException) as exc:
        await InvestigationService.run_investigation_orchestration(
            db=async_db_session,
            project=project,
            incident=incident,
            investigation=investigation,
        )
    assert exc.value.status_code == 422
    assert "Cannot orchestrate investigation with terminal status" in exc.value.detail
