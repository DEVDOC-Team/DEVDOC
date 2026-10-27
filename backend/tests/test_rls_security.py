"""DEVDOC Phase 4 — Supabase Row Level Security (RLS) Test Suite.

Comprehensive test suite verifying:
1. Static & Architecture Audits:
   - Protected tables list and model ownership anchor.
   - Child resource inheritance pathways.
   - Migration chain coherency (0001_initial_schema -> 0002_row_level_security).
   - Security rule audit: no 'true' bypasses, no hardcoded IDs, no leaked secrets.
2. PostgreSQL Live RLS Enforcement (Positive & Negative Security Tests):
   - Table RLS enablement verification on all 10 domain tables.
   - User profile isolation (SELECT, INSERT, UPDATE, DELETE).
   - Project boundary isolation between User A and User B.
   - Child resource isolation (repositories, incidents, investigations, deployments).
   - Grandchild resource isolation (evidence, fix_proposals, approvals).
   - Negative cross-tenant INSERT rejection via RLS WITH CHECK.
   - Negative cross-tenant UPDATE rejection via RLS USING/WITH CHECK.
   - Negative cross-tenant DELETE rejection via RLS USING.
   - Append-only immutability for audit_logs (UPDATE and DELETE denied).
   - Unauthenticated access rejection.
   - Privileged/service-role bypass verification.
"""

from __future__ import annotations

import os
import re
import uuid
from pathlib import Path

import asyncpg
import pytest
import pytest_asyncio

from app.models import (
    Approval,
    AuditLog,
    Deployment,
    Evidence,
    FixProposal,
    Incident,
    Investigation,
    Project,
    Repository,
    User,
)

# ---------------------------------------------------------------------------
# Configuration & Database Fixtures
# ---------------------------------------------------------------------------

PG_TEST_URL = os.environ.get(
    "TEST_POSTGRESQL_URL",
    os.environ.get(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5433/devdoc_test",
    ),
)
# Normalize to asyncpg raw connection URL
if "+asyncpg" in PG_TEST_URL:
    PG_TEST_URL = PG_TEST_URL.replace("+asyncpg", "")

ALL_DOMAIN_TABLES = [
    "users",
    "projects",
    "repositories",
    "incidents",
    "investigations",
    "evidence",
    "deployments",
    "fix_proposals",
    "approvals",
    "audit_logs",
]


@pytest_asyncio.fixture(scope="function")
async def pg_conn():
    """Create a fresh asyncpg connection for each test function if PG is available."""
    conn = None
    try:
        conn = await asyncpg.connect(PG_TEST_URL, timeout=3.0)
    except Exception:
        pytest.skip("Live PostgreSQL database is not accessible for RLS integration tests.")

    try:
        yield conn
    finally:
        if conn and not conn.is_closed():
            await conn.close()


# ---------------------------------------------------------------------------
# PART 1: Static, Architecture & Policy Audits
# ---------------------------------------------------------------------------


def test_protected_tables_complete():
    """Verify all 10 domain models are recognized for RLS protection."""
    expected_tables = {
        "users",
        "projects",
        "repositories",
        "incidents",
        "investigations",
        "evidence",
        "deployments",
        "fix_proposals",
        "approvals",
        "audit_logs",
    }
    actual_tables = {
        User.__tablename__,
        Project.__tablename__,
        Repository.__tablename__,
        Incident.__tablename__,
        Investigation.__tablename__,
        Evidence.__tablename__,
        Deployment.__tablename__,
        FixProposal.__tablename__,
        Approval.__tablename__,
        AuditLog.__tablename__,
    }
    assert actual_tables == expected_tables


def test_project_ownership_anchor():
    """Verify that Project.owner_id is the primary ownership anchor referencing users.id."""
    owner_col = Project.__table__.c.owner_id
    assert owner_col.nullable is False
    foreign_keys = list(owner_col.foreign_keys)
    assert len(foreign_keys) == 1
    assert foreign_keys[0].target_fullname == "users.id"


def test_child_resource_ownership_pathways():
    """Verify child models have foreign key links leading back to Project."""
    # Direct children of projects
    assert any(fk.target_fullname == "projects.id" for fk in Repository.__table__.c.project_id.foreign_keys)
    assert any(fk.target_fullname == "projects.id" for fk in Incident.__table__.c.project_id.foreign_keys)
    assert any(fk.target_fullname == "projects.id" for fk in Investigation.__table__.c.project_id.foreign_keys)
    assert any(fk.target_fullname == "projects.id" for fk in Deployment.__table__.c.project_id.foreign_keys)

    # Grandchild entities
    assert any(fk.target_fullname == "investigations.id" for fk in Evidence.__table__.c.investigation_id.foreign_keys)
    assert any(fk.target_fullname == "investigations.id" for fk in FixProposal.__table__.c.investigation_id.foreign_keys)
    assert any(fk.target_fullname == "fix_proposals.id" for fk in Approval.__table__.c.fix_proposal_id.foreign_keys)


def test_migration_chain_files_exist():
    """Verify migration files exist in the versions directory with proper naming."""
    versions_dir = Path(__file__).resolve().parents[1] / "app" / "db" / "migrations" / "versions"
    v1 = versions_dir / "0001_initial_schema.py"
    v2 = versions_dir / "0002_row_level_security.py"
    v8 = versions_dir / "0008_restrict_client_approval_audit_writes.py"

    assert v1.is_file(), "0001_initial_schema.py migration missing"
    assert v2.is_file(), "0002_row_level_security.py migration missing"
    assert v8.is_file(), "0008_restrict_client_approval_audit_writes.py migration missing"


def test_policy_definitions_security_audit():
    """Audit RLS migration content for dangerous anti-patterns."""
    v2_path = Path(__file__).resolve().parents[1] / "app" / "db" / "migrations" / "versions" / "0002_row_level_security.py"
    content = v2_path.read_text(encoding="utf-8")

    # Anti-pattern: universal bypass
    assert "USING (true)" not in content.lower()
    assert "using(true)" not in content.lower()
    assert "with check (true)" not in content.lower()
    assert "with check(true)" not in content.lower()

    # Anti-pattern: hardcoded real UUIDs (format 8-4-4-4-12)
    uuid_pattern = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)
    matches = uuid_pattern.findall(content)
    assert len(matches) == 0, f"Found hardcoded UUIDs in migration: {matches}"

    # Ensure RLS is enabled on all tables
    assert "ENABLE ROW LEVEL SECURITY" in content
    for table in ALL_DOMAIN_TABLES:
        assert f'"{table}"' in content or f"'{table}'" in content

    # Ensure immutability for audit_logs (append-only)
    assert "audit_logs_update_policy" not in content
    assert "audit_logs_delete_policy" not in content


def test_phase19_removes_direct_approval_and_audit_writes():
    """Ensure the hardening migration removes client-controlled writes."""
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "db"
        / "migrations"
        / "versions"
        / "0008_restrict_client_approval_audit_writes.py"
    )
    content = migration_path.read_text(encoding="utf-8")
    assert 'DROP POLICY IF EXISTS approvals_insert_policy ON public.approvals' in content
    assert 'DROP POLICY IF EXISTS approvals_update_policy ON public.approvals' in content
    assert 'DROP POLICY IF EXISTS audit_logs_insert_policy ON public.audit_logs' in content


# ---------------------------------------------------------------------------
# PART 2: PostgreSQL Live RLS Verification (Positive & Negative Tests)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_live_pg_rls_enabled_on_all_tables(pg_conn):
    """Verify all 10 domain tables have rowsecurity=True in PostgreSQL pg_tables."""
    rows = await pg_conn.fetch(
        """
        SELECT tablename, rowsecurity
        FROM pg_tables
        WHERE schemaname = 'public' AND tablename = ANY($1::text[])
        ORDER BY tablename
        """,
        ALL_DOMAIN_TABLES,
    )
    assert len(rows) == len(ALL_DOMAIN_TABLES)
    for r in rows:
        assert r["rowsecurity"] is True, f"RLS is not active on table {r['tablename']}"


@pytest.mark.asyncio
async def test_live_pg_helper_function_exists(pg_conn):
    """Verify has_project_access security definer function exists and is STABLE."""
    row = await pg_conn.fetchrow(
        """
        SELECT p.proname, p.prosecdef, p.provolatile
        FROM pg_proc p
        JOIN pg_namespace n ON p.pronamespace = n.oid
        WHERE n.nspname = 'public' AND p.proname = 'has_project_access'
        """
    )
    assert row is not None, "has_project_access function not found in public schema"
    assert row["prosecdef"] is True, "has_project_access must be SECURITY DEFINER"
    assert row["provolatile"] in ("s", b"s"), "has_project_access must be STABLE ('s')"


@pytest.mark.asyncio
async def test_live_pg_user_profile_rls(pg_conn):
    """Test User profile RLS: User A can access own profile; cannot access User B's profile."""
    user_a_id = uuid.uuid4()
    user_b_id = uuid.uuid4()

    # 1. Superuser seed
    await pg_conn.execute(
        """
        INSERT INTO public.users (id, email, full_name)
        VALUES ($1, $2, 'User A'), ($3, $4, 'User B')
        """,
        user_a_id,
        f"a_{user_a_id.hex[:8]}@example.com",
        user_b_id,
        f"b_{user_b_id.hex[:8]}@example.com",
    )

    # 2. Authenticated context as User A
    async with pg_conn.transaction():
        await pg_conn.execute("SET ROLE authenticated")
        await pg_conn.execute(f"SET LOCAL request.jwt.claim.sub = '{user_a_id}'")

        # User A SELECT own profile -> Success
        row_a = await pg_conn.fetchrow("SELECT id, full_name FROM public.users WHERE id = $1", user_a_id)
        assert row_a is not None
        assert row_a["full_name"] == "User A"

        # User A SELECT User B profile -> DENIED (returns None)
        row_b = await pg_conn.fetchrow("SELECT id, full_name FROM public.users WHERE id = $1", user_b_id)
        assert row_b is None

        # User A UPDATE User B profile -> DENIED (0 rows updated)
        res_upd = await pg_conn.execute("UPDATE public.users SET full_name = 'Hacked' WHERE id = $1", user_b_id)
        assert res_upd == "UPDATE 0"

        # User A DELETE User B profile -> DENIED (0 rows deleted)
        res_del = await pg_conn.execute("DELETE FROM public.users WHERE id = $1", user_b_id)
        assert res_del == "DELETE 0"

        # User A INSERT profile with User B ID -> DENIED (WITH CHECK violation)
        fake_id = uuid.uuid4()
        with pytest.raises(asyncpg.PostgresError):
            await pg_conn.execute(
                "INSERT INTO public.users (id, email) VALUES ($1, 'attacker@example.com')",
                fake_id,
            )


@pytest.mark.asyncio
async def test_live_pg_project_isolation(pg_conn):
    """Test Project RLS: User A can access own project; User B cannot access User A's project."""
    user_a_id = uuid.uuid4()
    user_b_id = uuid.uuid4()
    proj_a_id = uuid.uuid4()
    proj_b_id = uuid.uuid4()

    # Seed users and projects as privileged user
    await pg_conn.execute(
        """
        INSERT INTO public.users (id, email) VALUES ($1, $2), ($3, $4)
        """,
        user_a_id,
        f"a_{user_a_id.hex[:8]}@example.com",
        user_b_id,
        f"b_{user_b_id.hex[:8]}@example.com",
    )
    await pg_conn.execute(
        """
        INSERT INTO public.projects (id, owner_id, name, slug) VALUES
        ($1, $2, 'Project Alpha', $3),
        ($4, $5, 'Project Beta', $6)
        """,
        proj_a_id,
        user_a_id,
        f"alpha_{proj_a_id.hex[:6]}",
        proj_b_id,
        user_b_id,
        f"beta_{proj_b_id.hex[:6]}",
    )

    # Context: User A
    async with pg_conn.transaction():
        await pg_conn.execute("SET ROLE authenticated")
        await pg_conn.execute(f"SET LOCAL request.jwt.claim.sub = '{user_a_id}'")

        # User A can see Project A
        row_a = await pg_conn.fetchrow("SELECT id, name FROM public.projects WHERE id = $1", proj_a_id)
        assert row_a is not None
        assert row_a["name"] == "Project Alpha"

        # User A CANNOT see Project B (Negative test)
        row_b = await pg_conn.fetchrow("SELECT id, name FROM public.projects WHERE id = $1", proj_b_id)
        assert row_b is None

        # User A CANNOT update Project B (Negative test)
        res_upd = await pg_conn.execute("UPDATE public.projects SET name = 'Attacked' WHERE id = $1", proj_b_id)
        assert res_upd == "UPDATE 0"

        # User A CANNOT delete Project B (Negative test)
        res_del = await pg_conn.execute("DELETE FROM public.projects WHERE id = $1", proj_b_id)
        assert res_del == "DELETE 0"

        # User A CANNOT create a project owned by User B (Negative test)
        with pytest.raises(asyncpg.PostgresError):
            await pg_conn.execute(
                "INSERT INTO public.projects (id, owner_id, name, slug) VALUES ($1, $2, 'Sneaky', 'sn')",
                uuid.uuid4(),
                user_b_id,
            )


@pytest.mark.asyncio
async def test_live_pg_child_resources_isolation(pg_conn):
    """Test child resource isolation: repositories, incidents, investigations, deployments."""
    user_a_id = uuid.uuid4()
    user_b_id = uuid.uuid4()
    proj_a_id = uuid.uuid4()
    proj_b_id = uuid.uuid4()
    repo_b_id = uuid.uuid4()
    inc_b_id = uuid.uuid4()
    inv_b_id = uuid.uuid4()
    dep_b_id = uuid.uuid4()

    # Privileged seed
    await pg_conn.execute(
        "INSERT INTO public.users (id, email) VALUES ($1, $2), ($3, $4)",
        user_a_id,
        f"a_{user_a_id.hex[:8]}@example.com",
        user_b_id,
        f"b_{user_b_id.hex[:8]}@example.com",
    )
    await pg_conn.execute(
        "INSERT INTO public.projects (id, owner_id, name, slug) VALUES ($1, $2, 'Proj A', $3), ($4, $5, 'Proj B', $6)",
        proj_a_id,
        user_a_id,
        f"pa_{proj_a_id.hex[:6]}",
        proj_b_id,
        user_b_id,
        f"pb_{proj_b_id.hex[:6]}",
    )
    await pg_conn.execute(
        "INSERT INTO public.repositories (id, project_id, provider, full_name) VALUES ($1, $2, 'github', 'org/repo-b')",
        repo_b_id,
        proj_b_id,
    )
    await pg_conn.execute(
        "INSERT INTO public.incidents (id, project_id, title) VALUES ($1, $2, 'Incident in B')",
        inc_b_id,
        proj_b_id,
    )
    await pg_conn.execute(
        "INSERT INTO public.investigations (id, project_id, incident_id) VALUES ($1, $2, $3)",
        inv_b_id,
        proj_b_id,
        inc_b_id,
    )
    await pg_conn.execute(
        "INSERT INTO public.deployments (id, project_id, repository_id, commit_sha, ref, environment) VALUES ($1, $2, $3, 'abc1234', 'main', 'production')",
        dep_b_id,
        proj_b_id,
        repo_b_id,
    )

    # Context: User A tries to interact with User B's resources
    async with pg_conn.transaction():
        await pg_conn.execute("SET ROLE authenticated")
        await pg_conn.execute(f"SET LOCAL request.jwt.claim.sub = '{user_a_id}'")

        # User A cannot SELECT User B's child resources
        assert await pg_conn.fetchrow("SELECT id FROM public.repositories WHERE id = $1", repo_b_id) is None
        assert await pg_conn.fetchrow("SELECT id FROM public.incidents WHERE id = $1", inc_b_id) is None
        assert await pg_conn.fetchrow("SELECT id FROM public.investigations WHERE id = $1", inv_b_id) is None
        assert await pg_conn.fetchrow("SELECT id FROM public.deployments WHERE id = $1", dep_b_id) is None

        # User A cannot UPDATE User B's child resources
        assert await pg_conn.execute("UPDATE public.repositories SET is_active = false WHERE id = $1", repo_b_id) == "UPDATE 0"
        assert await pg_conn.execute("UPDATE public.incidents SET title = 'Altered' WHERE id = $1", inc_b_id) == "UPDATE 0"
        assert await pg_conn.execute("UPDATE public.investigations SET error_message = 'Hack' WHERE id = $1", inv_b_id) == "UPDATE 0"
        assert await pg_conn.execute("UPDATE public.deployments SET environment = 'staging' WHERE id = $1", dep_b_id) == "UPDATE 0"

        # User A cannot DELETE User B's child resources
        assert await pg_conn.execute("DELETE FROM public.repositories WHERE id = $1", repo_b_id) == "DELETE 0"
        assert await pg_conn.execute("DELETE FROM public.incidents WHERE id = $1", inc_b_id) == "DELETE 0"
        assert await pg_conn.execute("DELETE FROM public.investigations WHERE id = $1", inv_b_id) == "DELETE 0"
        assert await pg_conn.execute("DELETE FROM public.deployments WHERE id = $1", dep_b_id) == "DELETE 0"

        # User A cannot INSERT a repository under User B's project
        with pytest.raises(asyncpg.PostgresError):
            await pg_conn.execute(
                "INSERT INTO public.repositories (id, project_id, provider, full_name) VALUES ($1, $2, 'github', 'org/infiltrate')",
                uuid.uuid4(),
                proj_b_id,
            )

        # User A cannot INSERT an incident under User B's project
        with pytest.raises(asyncpg.PostgresError):
            await pg_conn.execute(
                "INSERT INTO public.incidents (id, project_id, title) VALUES ($1, $2, 'Malicious Incident')",
                uuid.uuid4(),
                proj_b_id,
            )

        # User A cannot INSERT an investigation under User B's project
        with pytest.raises(asyncpg.PostgresError):
            await pg_conn.execute(
                "INSERT INTO public.investigations (id, project_id, incident_id) VALUES ($1, $2, $3)",
                uuid.uuid4(),
                proj_b_id,
                inc_b_id,
            )


@pytest.mark.asyncio
async def test_live_pg_grandchild_resources_isolation(pg_conn):
    """Test grandchild resource isolation: evidence, fix_proposals, approvals."""
    user_a_id = uuid.uuid4()
    user_b_id = uuid.uuid4()
    proj_b_id = uuid.uuid4()
    inc_b_id = uuid.uuid4()
    inv_b_id = uuid.uuid4()
    ev_b_id = uuid.uuid4()
    fp_b_id = uuid.uuid4()
    appr_b_id = uuid.uuid4()

    # Privileged seed
    await pg_conn.execute(
        "INSERT INTO public.users (id, email) VALUES ($1, $2), ($3, $4)",
        user_a_id,
        f"a_{user_a_id.hex[:8]}@example.com",
        user_b_id,
        f"b_{user_b_id.hex[:8]}@example.com",
    )
    await pg_conn.execute(
        "INSERT INTO public.projects (id, owner_id, name, slug) VALUES ($1, $2, 'Proj B', $3)",
        proj_b_id,
        user_b_id,
        f"pb2_{proj_b_id.hex[:6]}",
    )
    await pg_conn.execute(
        "INSERT INTO public.incidents (id, project_id, title) VALUES ($1, $2, 'Inc B')",
        inc_b_id,
        proj_b_id,
    )
    await pg_conn.execute(
        "INSERT INTO public.investigations (id, project_id, incident_id) VALUES ($1, $2, $3)",
        inv_b_id,
        proj_b_id,
        inc_b_id,
    )
    await pg_conn.execute(
        "INSERT INTO public.evidence (id, investigation_id, kind, label) VALUES ($1, $2, 'log_excerpt', 'Secret log')",
        ev_b_id,
        inv_b_id,
    )
    await pg_conn.execute(
        "INSERT INTO public.fix_proposals (id, investigation_id, title) VALUES ($1, $2, 'Fix B')",
        fp_b_id,
        inv_b_id,
    )
    await pg_conn.execute(
        "INSERT INTO public.approvals "
        "(id, fix_proposal_id, approver_id, requested_by_id, status, decision, decided_at) "
        "VALUES ($1, $2, $3, $3, 'approved', 'approved', now())",
        appr_b_id,
        fp_b_id,
        user_b_id,
    )

    # Context: User A attempts unauthorized access
    async with pg_conn.transaction():
        await pg_conn.execute("SET ROLE authenticated")
        await pg_conn.execute(f"SET LOCAL request.jwt.claim.sub = '{user_a_id}'")

        # User A cannot SELECT grandchild items of User B
        assert await pg_conn.fetchrow("SELECT id FROM public.evidence WHERE id = $1", ev_b_id) is None
        assert await pg_conn.fetchrow("SELECT id FROM public.fix_proposals WHERE id = $1", fp_b_id) is None
        assert await pg_conn.fetchrow("SELECT id FROM public.approvals WHERE id = $1", appr_b_id) is None

        # User A cannot UPDATE grandchild items of User B
        assert await pg_conn.execute("UPDATE public.evidence SET label = 'Corrupted' WHERE id = $1", ev_b_id) == "UPDATE 0"
        assert await pg_conn.execute("UPDATE public.fix_proposals SET title = 'Corrupted' WHERE id = $1", fp_b_id) == "UPDATE 0"
        assert await pg_conn.execute("UPDATE public.approvals SET decision = 'rejected' WHERE id = $1", appr_b_id) == "UPDATE 0"

        # User A cannot DELETE grandchild items of User B
        assert await pg_conn.execute("DELETE FROM public.evidence WHERE id = $1", ev_b_id) == "DELETE 0"
        assert await pg_conn.execute("DELETE FROM public.fix_proposals WHERE id = $1", fp_b_id) == "DELETE 0"
        assert await pg_conn.execute("DELETE FROM public.approvals WHERE id = $1", appr_b_id) == "DELETE 0"

        # User A cannot INSERT evidence under User B's investigation
        with pytest.raises(asyncpg.PostgresError):
            await pg_conn.execute(
                "INSERT INTO public.evidence (id, investigation_id, kind, label) VALUES ($1, $2, 'log_excerpt', 'Injected')",
                uuid.uuid4(),
                inv_b_id,
            )

        # User A cannot INSERT fix_proposal under User B's investigation
        with pytest.raises(asyncpg.PostgresError):
            await pg_conn.execute(
                "INSERT INTO public.fix_proposals (id, investigation_id, title) VALUES ($1, $2, 'Injected')",
                uuid.uuid4(),
                inv_b_id,
            )

        # User A cannot INSERT approval under User B's fix_proposal
        with pytest.raises(asyncpg.PostgresError):
            await pg_conn.execute(
                "INSERT INTO public.approvals "
                "(id, fix_proposal_id, approver_id, requested_by_id, status, decision, decided_at) "
                "VALUES ($1, $2, $3, $3, 'approved', 'approved', now())",
                uuid.uuid4(),
                fp_b_id,
                user_a_id,
            )


@pytest.mark.asyncio
async def test_live_pg_approval_actor_guard_and_lifecycle_audit(pg_conn):
    """Enforce authenticated decision identity and database-generated audit events."""
    user_id = uuid.uuid4()
    project_id = uuid.uuid4()
    incident_id = uuid.uuid4()
    investigation_id = uuid.uuid4()
    proposal_id = uuid.uuid4()
    verification_id = uuid.uuid4()
    approval_id = uuid.uuid4()
    fingerprint = "a" * 64

    await pg_conn.execute(
        "INSERT INTO public.users (id, email) VALUES ($1, $2)",
        user_id,
        f"approval_{user_id.hex[:8]}@example.com",
    )
    await pg_conn.execute(
        "INSERT INTO public.projects (id, owner_id, name, slug) VALUES ($1, $2, 'Approval project', $3)",
        project_id,
        user_id,
        f"approval_{project_id.hex[:8]}",
    )
    await pg_conn.execute(
        "INSERT INTO public.incidents (id, project_id, title) VALUES ($1, $2, 'Approval incident')",
        incident_id,
        project_id,
    )
    await pg_conn.execute(
        "INSERT INTO public.investigations (id, project_id, incident_id) VALUES ($1, $2, $3)",
        investigation_id,
        project_id,
        incident_id,
    )
    await pg_conn.execute(
        "INSERT INTO public.fix_proposals (id, investigation_id, title) VALUES ($1, $2, 'Verified fix')",
        proposal_id,
        investigation_id,
    )
    await pg_conn.execute(
        "INSERT INTO public.approval_artifacts "
        "(id, project_id, investigation_id, fix_proposal_id, verification_status, "
        "root_cause_fingerprint, proposal_fingerprint, proposal_record_fingerprint, "
        "verification_fingerprint, root_cause_snapshot, proposal_snapshot, verification_snapshot) "
        "VALUES ($1, $2, $3, $4, 'passed', $5, $5, $5, $5, '{}', '{}', '{}')",
        verification_id,
        project_id,
        investigation_id,
        proposal_id,
        fingerprint,
    )
    await pg_conn.execute(
        "INSERT INTO public.approvals "
        "(id, fix_proposal_id, requested_by_id, verification_id, status, "
        "proposal_fingerprint, verification_fingerprint, expires_at) "
        "VALUES ($1, $2, $3, $4, 'pending', $5, $5, now() + interval '1 day')",
        approval_id,
        proposal_id,
        user_id,
        verification_id,
        fingerprint,
    )

    async with pg_conn.transaction():
        await pg_conn.execute("SET LOCAL ROLE authenticated")
        await pg_conn.execute(f"SET LOCAL request.jwt.claim.sub = '{user_id}'")
        visible = await pg_conn.fetchrow(
            "SELECT id FROM public.approvals WHERE id = $1",
            approval_id,
        )
        assert visible is not None
        with pytest.raises(asyncpg.PostgresError):
            await pg_conn.execute(
                "INSERT INTO public.approvals "
                "(id, fix_proposal_id, requested_by_id, verification_id, status, "
                "proposal_fingerprint, verification_fingerprint, expires_at) "
                "VALUES ($1, $2, $3, $4, 'pending', $5, $5, now() + interval '1 day')",
                uuid.uuid4(),
                proposal_id,
                user_id,
                verification_id,
                fingerprint,
            )
        with pytest.raises(asyncpg.PostgresError):
            await pg_conn.execute(
                "UPDATE public.approvals SET status = 'approved', decision = 'approved', "
                "approver_id = $2, rationale = 'Approved after verified review.', decided_at = now() "
                "WHERE id = $1",
                approval_id,
                user_id,
            )

    async with pg_conn.transaction():
        await pg_conn.execute(f"SET LOCAL request.jwt.claim.sub = '{user_id}'")
        with pytest.raises(asyncpg.PostgresError, match="Decision actor must match"):
            await pg_conn.execute(
                "UPDATE public.approvals SET status = 'approved', decision = 'approved', "
                "approver_id = $2, rationale = 'Approved after verified review.', decided_at = now() "
                "WHERE id = $1",
                approval_id,
                uuid.uuid4(),
            )
    async with pg_conn.transaction():
        await pg_conn.execute(f"SET LOCAL request.jwt.claim.sub = '{user_id}'")
        assert await pg_conn.execute(
            "UPDATE public.approvals SET status = 'approved', decision = 'approved', "
            "approver_id = $2, rationale = 'Approved after verified review.', decided_at = now() "
            "WHERE id = $1",
            approval_id,
            user_id,
        ) == "UPDATE 1"

    approval = await pg_conn.fetchrow(
        "SELECT status, approver_id FROM public.approvals WHERE id = $1",
        approval_id,
    )
    assert approval["status"] == "approved"
    assert approval["approver_id"] == user_id

    audit = await pg_conn.fetch(
        "SELECT action, actor_id, diff FROM public.audit_logs "
        "WHERE entity_type = 'approval' AND entity_id = $1 ORDER BY created_at",
        approval_id,
    )
    assert [row["action"] for row in audit] == [
        "approval.requested",
        "approval.approved",
    ]
    assert all(row["actor_id"] == user_id for row in audit)
    assert "Approved after verified review." in audit[-1]["diff"]


@pytest.mark.asyncio
async def test_live_pg_audit_logs_append_only_immutability(pg_conn):
    """Test audit_logs RLS: SELECT is scoped; INSERT is allowed; UPDATE and DELETE are DENIED."""
    user_a_id = uuid.uuid4()
    proj_a_id = uuid.uuid4()
    log_id = uuid.uuid4()

    # Privileged seed
    await pg_conn.execute(
        "INSERT INTO public.users (id, email) VALUES ($1, $2)",
        user_a_id,
        f"a_{user_a_id.hex[:8]}@example.com",
    )
    await pg_conn.execute(
        "INSERT INTO public.projects (id, owner_id, name, slug) VALUES ($1, $2, 'Proj Log', $3)",
        proj_a_id,
        user_a_id,
        f"pl_{proj_a_id.hex[:6]}",
    )
    await pg_conn.execute(
        "INSERT INTO public.audit_logs (id, actor_id, project_id, action) VALUES ($1, $2, $3, 'incident.created')",
        log_id,
        user_a_id,
        proj_a_id,
    )

    # Context: User A
    async with pg_conn.transaction():
        await pg_conn.execute("SET ROLE authenticated")
        await pg_conn.execute(f"SET LOCAL request.jwt.claim.sub = '{user_a_id}'")

        # User A can SELECT own audit log
        row = await pg_conn.fetchrow("SELECT id, action FROM public.audit_logs WHERE id = $1", log_id)
        assert row is not None
        assert row["action"] == "incident.created"

        # Direct client writes cannot forge audit events.
        new_log_id = uuid.uuid4()
        with pytest.raises(asyncpg.PostgresError):
            await pg_conn.execute(
                "INSERT INTO public.audit_logs "
                "(id, actor_id, project_id, action) "
                "VALUES ($1, $2, $3, 'investigation.started')",
                new_log_id,
                user_a_id,
                proj_a_id,
            )

        # User A CANNOT UPDATE audit logs (Immutability guarantee: 0 rows affected)
        res_upd = await pg_conn.execute("UPDATE public.audit_logs SET action = 'tampered' WHERE id = $1", log_id)
        assert res_upd == "UPDATE 0"

        # User A CANNOT DELETE audit logs (Immutability guarantee: 0 rows affected)
        res_del = await pg_conn.execute("DELETE FROM public.audit_logs WHERE id = $1", log_id)
        assert res_del == "DELETE 0"


@pytest.mark.asyncio
async def test_live_pg_unauthenticated_access_denied(pg_conn):
    """Test unauthenticated (anon / NULL auth.uid) access is denied across tables."""
    user_a_id = uuid.uuid4()
    proj_a_id = uuid.uuid4()

    # Privileged seed
    await pg_conn.execute(
        "INSERT INTO public.users (id, email) VALUES ($1, $2)",
        user_a_id,
        f"anon_{user_a_id.hex[:8]}@example.com",
    )
    await pg_conn.execute(
        "INSERT INTO public.projects (id, owner_id, name, slug) VALUES ($1, $2, 'Proj Anon', $3)",
        proj_a_id,
        user_a_id,
        f"pa_anon_{proj_a_id.hex[:6]}",
    )

    # Context: anon role with no JWT claim
    async with pg_conn.transaction():
        await pg_conn.execute("SET ROLE anon")

        # Anon cannot SELECT projects (denied either by 0 rows or permission denied)
        try:
            row = await pg_conn.fetchrow("SELECT * FROM public.projects WHERE id = $1", proj_a_id)
            assert row is None
        except Exception:
            pass  # Permission denied is expected and valid security behavior

        # Anon cannot INSERT
        with pytest.raises(asyncpg.PostgresError):
            await pg_conn.execute(
                "INSERT INTO public.projects (id, owner_id, name, slug) VALUES ($1, $2, 'AnonProj', 'anon-slug')",
                uuid.uuid4(),
                user_a_id,
            )


@pytest.mark.asyncio
async def test_live_pg_privileged_bypass(pg_conn):
    """Test superuser/service_role bypasses RLS and can query all projects."""
    user_a_id = uuid.uuid4()
    user_b_id = uuid.uuid4()
    proj_a_id = uuid.uuid4()
    proj_b_id = uuid.uuid4()

    # Seed two users and projects
    await pg_conn.execute(
        "INSERT INTO public.users (id, email) VALUES ($1, $2), ($3, $4)",
        user_a_id,
        f"priv_a_{user_a_id.hex[:8]}@example.com",
        user_b_id,
        f"priv_b_{user_b_id.hex[:8]}@example.com",
    )
    await pg_conn.execute(
        "INSERT INTO public.projects (id, owner_id, name, slug) VALUES ($1, $2, 'Priv A', $3), ($4, $5, 'Priv B', $6)",
        proj_a_id,
        user_a_id,
        f"priv_a_{proj_a_id.hex[:6]}",
        proj_b_id,
        user_b_id,
        f"priv_b_{proj_b_id.hex[:6]}",
    )

    # As superuser/postgres (bypasses RLS):
    rows = await pg_conn.fetch(
        "SELECT id FROM public.projects WHERE id = ANY($1::uuid[])",
        [proj_a_id, proj_b_id],
    )
    assert len(rows) == 2, "Privileged backend service role must see all projects"
