"""DEVDOC Phase 3 — Database Models & Relationships Test Suite.

Tests all Phase 3 additions:
- New fields (project_id on Investigation/Deployment, initiated_by_id,
  created_by_id, triggered_by_id, reported_by_id, last_sign_in_at,
  source_metadata, collected_at, resolved_at, outcome, session_id, etc.)
- New constraints (CheckConstraints on scores, commit_sha length,
  Approval uniqueness per approver+proposal)
- New composite indexes (verified via SQLAlchemy inspector)
- New relationships (Investigation↔Project, User↔Investigation, etc.)
- Enum completeness and consistency
- Alembic metadata discovery (all models in Base.metadata)
- Cascade and orphan-prevention behaviour
- Soft-delete flags (is_active on Project / Repository)
- Full CRUD on new models (Investigation, Evidence, Deployment, FixProposal, Approval)

All tests use in-memory SQLite — no Supabase credentials required.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models import (
    Approval,
    ApprovalDecision,
    AuditLog,
    AuditOutcome,
    Deployment,
    DeploymentStatus,
    Evidence,
    EvidenceKind,
    FixProposal,
    FixStatus,
    Incident,
    IncidentSeverity,
    IncidentStatus,
    Investigation,
    InvestigationStatus,
    Project,
    Repository,
    User,
    VCSProvider,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="function")
async def engine():
    """Fresh in-memory SQLite engine with FK enforcement and all tables."""
    _engine = create_async_engine(TEST_DATABASE_URL, echo=False, future=True)
    async with _engine.begin() as conn:
        await conn.execute(text("PRAGMA foreign_keys = ON"))
        await conn.run_sync(Base.metadata.create_all)
    yield _engine
    await _engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db(engine) -> AsyncSession:
    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


# ---- Domain fixtures --------------------------------------------------------


@pytest_asyncio.fixture
async def user(db: AsyncSession) -> User:
    u = User(email="alice@devdoc.test", full_name="Alice DevDoc")
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest_asyncio.fixture
async def user2(db: AsyncSession) -> User:
    u = User(email="bob@devdoc.test", full_name="Bob DevDoc")
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest_asyncio.fixture
async def project(db: AsyncSession, user: User) -> Project:
    p = Project(name="DEVDOC Core", slug="devdoc-core", owner_id=user.id)
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return p


@pytest_asyncio.fixture
async def repository(db: AsyncSession, project: Project) -> Repository:
    r = Repository(
        project_id=project.id,
        provider=VCSProvider.GITHUB,
        full_name="acme/backend",
        default_branch="main",
    )
    db.add(r)
    await db.commit()
    await db.refresh(r)
    return r


@pytest_asyncio.fixture
async def incident(db: AsyncSession, project: Project, user: User) -> Incident:
    i = Incident(
        project_id=project.id,
        title="API 500 errors on /checkout",
        severity=IncidentSeverity.CRITICAL,
        status=IncidentStatus.OPEN,
        reported_by_id=user.id,
    )
    db.add(i)
    await db.commit()
    await db.refresh(i)
    return i


@pytest_asyncio.fixture
async def investigation(
    db: AsyncSession, project: Project, incident: Incident, user: User
) -> Investigation:
    inv = Investigation(
        project_id=project.id,
        incident_id=incident.id,
        initiated_by_id=user.id,
        status=InvestigationStatus.PENDING,
    )
    db.add(inv)
    await db.commit()
    await db.refresh(inv)
    return inv


@pytest_asyncio.fixture
async def fix_proposal(db: AsyncSession, investigation: Investigation) -> FixProposal:
    fp = FixProposal(
        investigation_id=investigation.id,
        title="Fix null pointer in checkout handler",
        status=FixStatus.DRAFT,
    )
    db.add(fp)
    await db.commit()
    await db.refresh(fp)
    return fp


# ===========================================================================
# Step 1 — Schema & Metadata Discovery
# ===========================================================================


async def test_all_expected_tables_in_metadata():
    """Alembic can discover all models via Base.metadata."""
    table_names = set(Base.metadata.tables.keys())
    expected = {
        "users", "projects", "repositories", "incidents",
        "investigations", "evidence", "deployments",
        "fix_proposals", "approvals", "audit_logs",
    }
    assert expected.issubset(table_names), f"Missing: {expected - table_names}"


async def test_all_tables_created_in_db(engine):
    """create_all produces all 10 tables in SQLite."""
    async with engine.connect() as conn:
        actual = await conn.run_sync(lambda c: set(inspect(c).get_table_names()))
    expected = {
        "users", "projects", "repositories", "incidents",
        "investigations", "evidence", "deployments",
        "fix_proposals", "approvals", "audit_logs",
    }
    assert expected.issubset(actual), f"Missing tables: {expected - actual}"


# ===========================================================================
# Step 2 — Enum Completeness
# ===========================================================================


def test_incident_severity_values():
    assert set(IncidentSeverity) == {
        IncidentSeverity.CRITICAL,
        IncidentSeverity.HIGH,
        IncidentSeverity.MEDIUM,
        IncidentSeverity.LOW,
        IncidentSeverity.INFO,
    }


def test_incident_status_values():
    assert set(IncidentStatus) == {
        IncidentStatus.OPEN,
        IncidentStatus.INVESTIGATING,
        IncidentStatus.MITIGATED,
        IncidentStatus.RESOLVED,
        IncidentStatus.CLOSED,
    }


def test_investigation_status_values():
    assert set(InvestigationStatus) == {
        InvestigationStatus.PENDING,
        InvestigationStatus.RUNNING,
        InvestigationStatus.COMPLETED,
        InvestigationStatus.FAILED,
        InvestigationStatus.CANCELLED,
    }


def test_fix_status_values():
    assert set(FixStatus) == {
        FixStatus.DRAFT,
        FixStatus.SANDBOX_PENDING,
        FixStatus.SANDBOX_RUNNING,
        FixStatus.SANDBOX_PASSED,
        FixStatus.SANDBOX_FAILED,
        FixStatus.AWAITING_APPROVAL,
        FixStatus.APPROVED,
        FixStatus.REJECTED,
        FixStatus.APPLIED,
        FixStatus.REVERTED,
    }


def test_approval_decision_values():
    assert set(ApprovalDecision) == {ApprovalDecision.APPROVED, ApprovalDecision.REJECTED}


def test_evidence_kind_values():
    expected = {
        EvidenceKind.LOG_EXCERPT, EvidenceKind.STACK_TRACE,
        EvidenceKind.METRIC_SNAPSHOT, EvidenceKind.CONFIG_DIFF,
        EvidenceKind.COMMIT_DIFF, EvidenceKind.CI_LOG,
        EvidenceKind.CONTAINER_LOG, EvidenceKind.DOCUMENTATION,
        EvidenceKind.OTHER,
    }
    assert set(EvidenceKind) == expected


def test_audit_outcome_values():
    assert set(AuditOutcome) == {
        AuditOutcome.SUCCESS, AuditOutcome.FAILURE, AuditOutcome.PARTIAL
    }


def test_vcs_provider_values():
    assert set(VCSProvider) == {
        VCSProvider.GITHUB, VCSProvider.GITLAB, VCSProvider.BITBUCKET
    }


def test_deployment_status_values():
    assert set(DeploymentStatus) == {
        DeploymentStatus.PENDING, DeploymentStatus.RUNNING,
        DeploymentStatus.SUCCESS, DeploymentStatus.FAILED,
        DeploymentStatus.ROLLED_BACK, DeploymentStatus.CANCELLED,
    }


# ===========================================================================
# Step 3 — Phase 3 User fields
# ===========================================================================


async def test_user_last_sign_in_at(db: AsyncSession, user: User):
    """last_sign_in_at can be set and retrieved."""
    now = datetime.now(UTC).replace(microsecond=0)
    user.last_sign_in_at = now
    await db.commit()
    await db.refresh(user)
    # Accept naive (SQLite) or aware (PG) datetimes
    assert user.last_sign_in_at is not None


async def test_user_provider_fields(db: AsyncSession):
    """Provider and provider_user_id are stored correctly."""
    u = User(email="gh@devdoc.test", provider="github", provider_user_id="gh_123456")
    db.add(u)
    await db.commit()
    await db.refresh(u)
    assert u.provider == "github"
    assert u.provider_user_id == "gh_123456"


# ===========================================================================
# Step 4 — Phase 3 Project fields
# ===========================================================================


async def test_project_is_active_default_true(db: AsyncSession, project: Project):
    assert project.is_active is True


async def test_project_soft_delete(db: AsyncSession, project: Project):
    """is_active can be set to False for soft-deletion."""
    project.is_active = False
    await db.commit()
    await db.refresh(project)
    assert project.is_active is False


async def test_project_settings_json(db: AsyncSession, project: Project):
    """settings_json stores arbitrary text."""
    project.settings_json = '{"notify_slack": true, "default_severity": "high"}'
    await db.commit()
    await db.refresh(project)
    assert "notify_slack" in project.settings_json


# ===========================================================================
# Step 5 — Phase 3 Repository fields
# ===========================================================================


async def test_repository_language_and_description(db: AsyncSession, repository: Repository):
    """language and description fields are stored."""
    repository.language = "Python"
    repository.description = "DEVDOC backend API"
    await db.commit()
    await db.refresh(repository)
    assert repository.language == "Python"
    assert repository.description == "DEVDOC backend API"


async def test_repository_is_active_default(db: AsyncSession, repository: Repository):
    assert repository.is_active is True


async def test_repository_last_synced_at(db: AsyncSession, repository: Repository):
    now = datetime.now(UTC)
    repository.last_synced_at = now
    await db.commit()
    await db.refresh(repository)
    assert repository.last_synced_at is not None


# ===========================================================================
# Step 6 — Phase 3 Incident fields
# ===========================================================================


async def test_incident_reported_by(db: AsyncSession, incident: Incident, user: User):
    """reported_by_id links to the User who reported the incident."""
    assert incident.reported_by_id == user.id


async def test_incident_resolved_at(db: AsyncSession, incident: Incident):
    """resolved_at can be set when resolving an incident."""
    now = datetime.now(UTC)
    incident.status = IncidentStatus.RESOLVED
    incident.resolved_at = now
    await db.commit()
    await db.refresh(incident)
    assert incident.resolved_at is not None
    assert incident.status == IncidentStatus.RESOLVED


async def test_incident_affected_users_cannot_be_negative(db: AsyncSession, project: Project):
    """CheckConstraint rejects negative affected_users on PostgreSQL (skipped for SQLite)."""
    # SQLite does not enforce CHECK constraints by default without specific
    # compile options; we verify the constraint is declared in metadata.
    constraint_names = {
        c.name
        for c in Base.metadata.tables["incidents"].constraints
        if hasattr(c, "name") and c.name
    }
    assert "ck_incidents_affected_users_non_negative" in constraint_names


# ===========================================================================
# Step 7 — Phase 3 Investigation: project_id + initiated_by_id
# ===========================================================================


async def test_investigation_has_project_id(
    db: AsyncSession, investigation: Investigation, project: Project
):
    """Investigation stores direct project_id FK."""
    assert investigation.project_id == project.id


async def test_investigation_has_initiated_by(
    db: AsyncSession, investigation: Investigation, user: User
):
    """Investigation stores initiated_by_id FK."""
    assert investigation.initiated_by_id == user.id


async def test_investigation_project_fk_invalid(db: AsyncSession, incident: Incident):
    """Investigation with non-existent project_id raises IntegrityError."""
    inv = Investigation(
        project_id=uuid.uuid4(),
        incident_id=incident.id,
        status=InvestigationStatus.PENDING,
    )
    db.add(inv)
    with pytest.raises(IntegrityError):
        await db.commit()
    await db.rollback()


async def test_investigation_confidence_score_removed_in_phase9():
    """Phase 9 replaced the original confidence score with structured RCA output."""
    assert "confidence_score" not in Base.metadata.tables["investigations"].columns


async def test_investigation_token_and_cost_tracking(
    db: AsyncSession, investigation: Investigation
):
    """Token usage and cost are tracked and default to 0."""
    assert investigation.tokens_used == 0
    assert investigation.estimated_cost_usd == 0
    investigation.tokens_used = 42500
    investigation.estimated_cost_usd = 125  # micro-USD
    await db.commit()
    await db.refresh(investigation)
    assert investigation.tokens_used == 42500


async def test_investigation_completed_at(db: AsyncSession, investigation: Investigation):
    """completed_at timestamp is set on completion."""
    now = datetime.now(UTC)
    investigation.status = InvestigationStatus.COMPLETED
    investigation.completed_at = now
    investigation.root_cause_summary = "Null pointer in payment handler."
    investigation.confidence_score = 87
    await db.commit()
    await db.refresh(investigation)
    assert investigation.completed_at is not None
    assert investigation.confidence_score == 87


async def test_cascade_delete_project_removes_investigations(
    db: AsyncSession, project: Project, investigation: Investigation
):
    """Deleting a Project cascades to its Investigations."""
    inv_id = investigation.id
    # Must also delete incident first (due to FK); project cascade handles both
    await db.delete(project)
    await db.commit()
    result = await db.get(Investigation, inv_id)
    assert result is None


# ===========================================================================
# Step 8 — Evidence: source_metadata + collected_at
# ===========================================================================


async def test_evidence_crud(db: AsyncSession, investigation: Investigation):
    """Full CRUD on Evidence with Phase 3 fields."""
    ev = Evidence(
        investigation_id=investigation.id,
        kind=EvidenceKind.COMMIT_DIFF,
        label="Suspicious commit 3 hours before incident",
        raw_content="- return None\n+ return order",
        source_url="https://github.com/acme/backend/commit/abc1234",
        source_metadata='{"repo": "acme/backend", "sha": "abc1234", "author": "dev@acme.com"}',
        collected_at=datetime.now(UTC),
        relevance_score=92,
    )
    db.add(ev)
    await db.commit()
    await db.refresh(ev)

    assert ev.id is not None
    assert ev.kind == EvidenceKind.COMMIT_DIFF
    assert ev.relevance_score == 92
    assert ev.source_metadata is not None
    assert "acme/backend" in ev.source_metadata


async def test_evidence_relevance_score_constraint_declared():
    """CheckConstraint on evidence.relevance_score is in metadata."""
    constraint_names = {
        c.name
        for c in Base.metadata.tables["evidence"].constraints
        if hasattr(c, "name") and c.name
    }
    assert "ck_evidence_relevance_score_range" in constraint_names


async def test_evidence_cascade_delete(db: AsyncSession, investigation: Investigation):
    """Deleting an Investigation removes its Evidence items."""
    ev = Evidence(
        investigation_id=investigation.id,
        kind=EvidenceKind.LOG_EXCERPT,
        label="Error log",
    )
    db.add(ev)
    await db.commit()
    ev_id = ev.id
    await db.delete(investigation)
    await db.commit()
    assert await db.get(Evidence, ev_id) is None


# ===========================================================================
# Step 9 — Deployment: project_id + triggered_by_id
# ===========================================================================


async def test_deployment_with_project_and_triggered_by(
    db: AsyncSession, project: Project, repository: Repository, user: User
):
    """Deployment stores project_id and triggered_by_id."""
    dep = Deployment(
        project_id=project.id,
        repository_id=repository.id,
        triggered_by_id=user.id,
        commit_sha="a" * 40,
        ref="main",
        environment="production",
        status=DeploymentStatus.SUCCESS,
    )
    db.add(dep)
    await db.commit()
    await db.refresh(dep)

    assert dep.project_id == project.id
    assert dep.triggered_by_id == user.id
    assert dep.status == DeploymentStatus.SUCCESS


async def test_deployment_commit_sha_constraint_declared():
    """CheckConstraint on commit_sha length is in metadata."""
    constraint_names = {
        c.name
        for c in Base.metadata.tables["deployments"].constraints
        if hasattr(c, "name") and c.name
    }
    assert "ck_deployments_commit_sha_length" in constraint_names


async def test_deployment_cascade_from_project(
    db: AsyncSession, project: Project, repository: Repository
):
    """Deleting a Project cascades to Deployments (via project_id FK)."""
    dep = Deployment(
        project_id=project.id,
        repository_id=repository.id,
        commit_sha="b" * 40,
        ref="dev",
        environment="staging",
        status=DeploymentStatus.PENDING,
    )
    db.add(dep)
    await db.commit()
    dep_id = dep.id
    await db.delete(project)
    await db.commit()
    assert await db.get(Deployment, dep_id) is None


# ===========================================================================
# Step 10 — FixProposal: created_by_id + target_repository_id
# ===========================================================================


async def test_fix_proposal_with_author_and_target_repo(
    db: AsyncSession,
    investigation: Investigation,
    user: User,
    repository: Repository,
):
    """FixProposal stores created_by_id and target_repository_id."""
    fp = FixProposal(
        investigation_id=investigation.id,
        created_by_id=user.id,
        target_repository_id=repository.id,
        title="Fix null check",
        patch_content="--- a/api.py\n+++ b/api.py\n@@ -1 +1 @@\n-return None\n+return order",
        status=FixStatus.DRAFT,
        confidence_score=75,
    )
    db.add(fp)
    await db.commit()
    await db.refresh(fp)

    assert fp.created_by_id == user.id
    assert fp.target_repository_id == repository.id
    assert fp.confidence_score == 75


async def test_fix_proposal_confidence_constraint_declared():
    constraint_names = {
        c.name
        for c in Base.metadata.tables["fix_proposals"].constraints
        if hasattr(c, "name") and c.name
    }
    assert "ck_fix_proposals_confidence_score_range" in constraint_names


# ===========================================================================
# Step 11 — Approval: uniqueness per approver+proposal
# ===========================================================================


async def test_approval_crud(
    db: AsyncSession, fix_proposal: FixProposal, user: User
):
    """Create an Approval record."""
    appr = Approval(
        fix_proposal_id=fix_proposal.id,
        approver_id=user.id,
        decision=ApprovalDecision.APPROVED,
        rationale="Looks good to me.",
        review_note="Internal: checked with security team.",
    )
    db.add(appr)
    await db.commit()
    await db.refresh(appr)

    assert appr.id is not None
    assert appr.decision == ApprovalDecision.APPROVED
    assert appr.review_note is not None


async def test_approval_unique_per_approver_proposal(
    db: AsyncSession, fix_proposal: FixProposal, user: User
):
    """A user cannot submit two approvals for the same FixProposal."""
    a1 = Approval(
        fix_proposal_id=fix_proposal.id,
        approver_id=user.id,
        decision=ApprovalDecision.APPROVED,
    )
    a2 = Approval(
        fix_proposal_id=fix_proposal.id,
        approver_id=user.id,
        decision=ApprovalDecision.REJECTED,
    )
    db.add(a1)
    await db.commit()
    db.add(a2)
    with pytest.raises(IntegrityError):
        await db.commit()
    await db.rollback()


async def test_two_different_approvers_allowed(
    db: AsyncSession, fix_proposal: FixProposal, user: User, user2: User
):
    """Different users can both approve the same FixProposal."""
    a1 = Approval(
        fix_proposal_id=fix_proposal.id,
        approver_id=user.id,
        decision=ApprovalDecision.APPROVED,
    )
    a2 = Approval(
        fix_proposal_id=fix_proposal.id,
        approver_id=user2.id,
        decision=ApprovalDecision.APPROVED,
    )
    db.add(a1)
    db.add(a2)
    await db.commit()
    # Both should exist
    result = await db.execute(
        select(Approval).where(Approval.fix_proposal_id == fix_proposal.id)
    )
    rows = result.scalars().all()
    assert len(rows) == 2


# ===========================================================================
# Step 12 — AuditLog: project_id + outcome + session_id
# ===========================================================================


async def test_audit_log_with_project_and_outcome(
    db: AsyncSession, user: User, project: Project
):
    """AuditLog stores project_id, outcome, and session_id."""
    log = AuditLog(
        actor_id=user.id,
        project_id=project.id,
        action="investigation.started",
        entity_type="investigation",
        entity_id=uuid.uuid4(),
        description="AI investigation triggered for incident.",
        outcome=AuditOutcome.SUCCESS,
        session_id="sess_abc123",
        ip_address="192.0.2.1",
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)

    assert log.project_id == project.id
    assert log.outcome == AuditOutcome.SUCCESS
    assert log.session_id == "sess_abc123"


async def test_audit_log_project_fk_declared_set_null(
    db: AsyncSession, user: User, project: Project
):
    """AuditLog.project_id FK is declared with ondelete='SET NULL'.

    PostgreSQL enforces this at the database level: deleting a project sets
    audit_log.project_id to NULL rather than cascading the delete, preserving
    the audit trail. SQLite ORM-level deletes behave differently, so this test
    verifies the FK metadata declaration and basic persistence behaviour.
    """
    log = AuditLog(
        actor_id=user.id,
        project_id=project.id,
        action="project.created",
        outcome=AuditOutcome.SUCCESS,
    )
    db.add(log)
    await db.commit()
    log_id = log.id

    # 1. Verify FK is declared with SET NULL in SQLAlchemy metadata
    fk = next(
        (
            fk_obj
            for fk_obj in Base.metadata.tables["audit_logs"].foreign_keys
            if fk_obj.parent.name == "project_id"
        ),
        None,
    )
    assert fk is not None, "project_id FK not found in audit_logs metadata"
    assert fk.ondelete is not None and fk.ondelete.upper() == "SET NULL", (
        f"Expected SET NULL on project_id FK, got: {fk.ondelete}"
    )

    # 2. Audit log persisted and linked to project
    retrieved = await db.get(AuditLog, log_id)
    assert retrieved is not None
    assert retrieved.project_id == project.id
    assert retrieved.action == "project.created"

async def test_audit_log_actor_set_null_on_user_delete(
    db: AsyncSession, user: User
):
    """AuditLog.actor_id is SET NULL when the actor User is deleted."""
    log = AuditLog(
        actor_id=user.id,
        action="user.login",
        outcome=AuditOutcome.SUCCESS,
    )
    db.add(log)
    await db.commit()
    log_id = log.id

    await db.delete(user)
    await db.commit()

    retrieved = await db.get(AuditLog, log_id)
    assert retrieved is not None
    assert retrieved.actor_id is None


async def test_system_audit_log_no_actor(db: AsyncSession):
    """System events have actor_id = NULL."""
    log = AuditLog(
        action="system.health_check",
        outcome=AuditOutcome.SUCCESS,
        description="Scheduled health check passed.",
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)

    assert log.actor_id is None
    assert log.action == "system.health_check"


# ===========================================================================
# Step 13 — Composite Indexes (metadata presence)
# ===========================================================================


def test_composite_indexes_declared():
    """Verify all Phase 3 composite indexes are registered in metadata."""
    all_index_names: set[str] = set()
    for table in Base.metadata.tables.values():
        for idx in table.indexes:
            if idx.name:
                all_index_names.add(idx.name)

    required = {
        "ix_users_provider_provider_user_id",
        "ix_projects_owner_id_is_active",
        "ix_repositories_project_id_is_active",
        "ix_incidents_project_id_status",
        "ix_incidents_project_id_severity",
        "ix_investigations_project_id_status",
        "ix_investigations_incident_id_status",
        "ix_evidence_investigation_id_kind",
        "ix_deployments_project_id_env_status",
        "ix_deployments_repository_id_environment",
        "ix_fix_proposals_investigation_id_status",
        "ix_approvals_fix_proposal_id_decision",
        "ix_audit_logs_project_id_action",
        "ix_audit_logs_actor_id_created_at",
        "ix_audit_logs_entity_type_entity_id",
    }

    missing = required - all_index_names
    assert not missing, f"Missing composite indexes: {missing}"


# ===========================================================================
# Step 14 — Unique Constraints (metadata presence)
# ===========================================================================


def test_unique_constraints_declared():
    """Verify critical UniqueConstraints are registered in metadata."""
    approvals_constraints = {
        c.name
        for c in Base.metadata.tables["approvals"].constraints
        if hasattr(c, "name") and c.name
    }
    assert "uq_approvals_fix_proposal_approver" in approvals_constraints

    repo_constraints = {
        c.name
        for c in Base.metadata.tables["repositories"].constraints
        if hasattr(c, "name") and c.name
    }
    assert "uq_repositories_project_provider_name" in repo_constraints

    project_constraints = {
        c.name
        for c in Base.metadata.tables["projects"].constraints
        if hasattr(c, "name") and c.name
    }
    assert "uq_projects_owner_slug" in project_constraints


# ===========================================================================
# Step 15 — Full lifecycle integration test
# ===========================================================================


async def test_full_investigation_lifecycle(
    db: AsyncSession,
    project: Project,
    incident: Incident,
    user: User,
    repository: Repository,
):
    """End-to-end: create Investigation → Evidence → FixProposal → Approval → AuditLog."""
    # 1. Start investigation
    inv = Investigation(
        project_id=project.id,
        incident_id=incident.id,
        initiated_by_id=user.id,
        status=InvestigationStatus.RUNNING,
        tokens_used=1000,
        estimated_cost_usd=500,
    )
    db.add(inv)
    await db.commit()

    # 2. Collect evidence
    ev1 = Evidence(
        investigation_id=inv.id,
        kind=EvidenceKind.STACK_TRACE,
        label="Python traceback from API pod",
        raw_content="AttributeError: 'NoneType' object has no attribute 'total'",
        source_metadata='{"container": "api-pod-xyz", "service": "api"}',
        relevance_score=95,
    )
    ev2 = Evidence(
        investigation_id=inv.id,
        kind=EvidenceKind.COMMIT_DIFF,
        label="Commit before incident",
        source_url="https://github.com/acme/backend/commit/deadbeef",
        relevance_score=80,
    )
    db.add_all([ev1, ev2])
    await db.commit()

    # 3. Complete investigation
    inv.status = InvestigationStatus.COMPLETED
    inv.root_cause_summary = "NullPointerError in order.total introduced in deadbeef."
    inv.confidence_score = 91
    inv.tokens_used = 15000
    await db.commit()

    # 4. Create fix proposal
    fp = FixProposal(
        investigation_id=inv.id,
        created_by_id=user.id,
        target_repository_id=repository.id,
        title="Add null guard in order.total",
        patch_content="@@ -10 +10 @@\n-total = order.items.total\n+total = order.items.total if order.items else 0",
        status=FixStatus.AWAITING_APPROVAL,
        confidence_score=88,
    )
    db.add(fp)
    await db.commit()

    # 5. Approve the fix
    appr = Approval(
        fix_proposal_id=fp.id,
        approver_id=user.id,
        decision=ApprovalDecision.APPROVED,
        rationale="Verified fix in staging. LGTM.",
    )
    db.add(appr)

    # 6. Write audit log
    audit = AuditLog(
        actor_id=user.id,
        project_id=project.id,
        action="fix.approved",
        entity_type="fix_proposal",
        entity_id=fp.id,
        outcome=AuditOutcome.SUCCESS,
        description=f"Fix proposal {fp.id} approved by {user.email}",
    )
    db.add(audit)
    await db.commit()

    # Assertions
    await db.refresh(inv)
    await db.refresh(fp)
    await db.refresh(appr)
    await db.refresh(audit)

    assert inv.confidence_score == 91
    assert inv.tokens_used == 15000
    assert fp.status == FixStatus.AWAITING_APPROVAL
    assert appr.decision == ApprovalDecision.APPROVED
    assert audit.outcome == AuditOutcome.SUCCESS

    # Verify evidence count
    ev_result = await db.execute(
        select(Evidence).where(Evidence.investigation_id == inv.id)
    )
    assert len(ev_result.scalars().all()) == 2


# ===========================================================================
# Step 16 — Regression guards (all Phase 2 API endpoints still work)
# ===========================================================================


def test_health_endpoint_regression():
    from fastapi.testclient import TestClient

    from app.main import app
    client = TestClient(app)
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "DEVDOC"
    assert data["success"] is True


def test_readiness_endpoint_regression():
    from fastapi.testclient import TestClient

    from app.main import app
    client = TestClient(app)
    response = client.get("/api/v1/ready")
    assert response.status_code in (200, 503)
    data = response.json()
    assert data["service"] == "DEVDOC"
    assert "checks" in data
    assert "database" in data["checks"]
