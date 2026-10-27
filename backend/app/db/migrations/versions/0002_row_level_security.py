"""Supabase Row Level Security (RLS) policies.

Revision ID: 0002_row_level_security
Revises: 0001_initial_schema
Create Date: 2026-09-27

Enables Row Level Security (RLS) and defines granular security policies for all
10 DEVDOC domain tables:
- users
- projects
- repositories
- incidents
- investigations
- evidence
- deployments
- fix_proposals
- approvals
- audit_logs

Security Architecture:
- Uses Supabase auth.uid() as the identity anchor.
- Enforces project ownership boundary (has_project_access helper).
- Cascades authorization to child and grandchild resources.
- Protects immutability of audit_logs (append-only; no UPDATE/DELETE policies).
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0002_row_level_security"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None

# List of all protected tables
TABLES = [
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

POLICIES = [
    # ------------------------------------------------------------------
    # USERS
    # ------------------------------------------------------------------
    (
        "users",
        "users_select_policy",
        "CREATE POLICY users_select_policy ON public.users "
        "FOR SELECT TO authenticated "
        "USING (id = (SELECT auth.uid()))",
    ),
    (
        "users",
        "users_insert_policy",
        "CREATE POLICY users_insert_policy ON public.users "
        "FOR INSERT TO authenticated "
        "WITH CHECK (id = (SELECT auth.uid()))",
    ),
    (
        "users",
        "users_update_policy",
        "CREATE POLICY users_update_policy ON public.users "
        "FOR UPDATE TO authenticated "
        "USING (id = (SELECT auth.uid())) "
        "WITH CHECK (id = (SELECT auth.uid()))",
    ),
    (
        "users",
        "users_delete_policy",
        "CREATE POLICY users_delete_policy ON public.users "
        "FOR DELETE TO authenticated "
        "USING (id = (SELECT auth.uid()))",
    ),
    # ------------------------------------------------------------------
    # PROJECTS
    # ------------------------------------------------------------------
    (
        "projects",
        "projects_select_policy",
        "CREATE POLICY projects_select_policy ON public.projects "
        "FOR SELECT TO authenticated "
        "USING (owner_id = (SELECT auth.uid()))",
    ),
    (
        "projects",
        "projects_insert_policy",
        "CREATE POLICY projects_insert_policy ON public.projects "
        "FOR INSERT TO authenticated "
        "WITH CHECK (owner_id = (SELECT auth.uid()))",
    ),
    (
        "projects",
        "projects_update_policy",
        "CREATE POLICY projects_update_policy ON public.projects "
        "FOR UPDATE TO authenticated "
        "USING (owner_id = (SELECT auth.uid())) "
        "WITH CHECK (owner_id = (SELECT auth.uid()))",
    ),
    (
        "projects",
        "projects_delete_policy",
        "CREATE POLICY projects_delete_policy ON public.projects "
        "FOR DELETE TO authenticated "
        "USING (owner_id = (SELECT auth.uid()))",
    ),
    # ------------------------------------------------------------------
    # REPOSITORIES
    # ------------------------------------------------------------------
    (
        "repositories",
        "repositories_select_policy",
        "CREATE POLICY repositories_select_policy ON public.repositories "
        "FOR SELECT TO authenticated "
        "USING (public.has_project_access(project_id))",
    ),
    (
        "repositories",
        "repositories_insert_policy",
        "CREATE POLICY repositories_insert_policy ON public.repositories "
        "FOR INSERT TO authenticated "
        "WITH CHECK (public.has_project_access(project_id))",
    ),
    (
        "repositories",
        "repositories_update_policy",
        "CREATE POLICY repositories_update_policy ON public.repositories "
        "FOR UPDATE TO authenticated "
        "USING (public.has_project_access(project_id)) "
        "WITH CHECK (public.has_project_access(project_id))",
    ),
    (
        "repositories",
        "repositories_delete_policy",
        "CREATE POLICY repositories_delete_policy ON public.repositories "
        "FOR DELETE TO authenticated "
        "USING (public.has_project_access(project_id))",
    ),
    # ------------------------------------------------------------------
    # INCIDENTS
    # ------------------------------------------------------------------
    (
        "incidents",
        "incidents_select_policy",
        "CREATE POLICY incidents_select_policy ON public.incidents "
        "FOR SELECT TO authenticated "
        "USING (public.has_project_access(project_id))",
    ),
    (
        "incidents",
        "incidents_insert_policy",
        "CREATE POLICY incidents_insert_policy ON public.incidents "
        "FOR INSERT TO authenticated "
        "WITH CHECK (public.has_project_access(project_id))",
    ),
    (
        "incidents",
        "incidents_update_policy",
        "CREATE POLICY incidents_update_policy ON public.incidents "
        "FOR UPDATE TO authenticated "
        "USING (public.has_project_access(project_id)) "
        "WITH CHECK (public.has_project_access(project_id))",
    ),
    (
        "incidents",
        "incidents_delete_policy",
        "CREATE POLICY incidents_delete_policy ON public.incidents "
        "FOR DELETE TO authenticated "
        "USING (public.has_project_access(project_id))",
    ),
    # ------------------------------------------------------------------
    # INVESTIGATIONS
    # ------------------------------------------------------------------
    (
        "investigations",
        "investigations_select_policy",
        "CREATE POLICY investigations_select_policy ON public.investigations "
        "FOR SELECT TO authenticated "
        "USING (public.has_project_access(project_id))",
    ),
    (
        "investigations",
        "investigations_insert_policy",
        "CREATE POLICY investigations_insert_policy ON public.investigations "
        "FOR INSERT TO authenticated "
        "WITH CHECK (public.has_project_access(project_id))",
    ),
    (
        "investigations",
        "investigations_update_policy",
        "CREATE POLICY investigations_update_policy ON public.investigations "
        "FOR UPDATE TO authenticated "
        "USING (public.has_project_access(project_id)) "
        "WITH CHECK (public.has_project_access(project_id))",
    ),
    (
        "investigations",
        "investigations_delete_policy",
        "CREATE POLICY investigations_delete_policy ON public.investigations "
        "FOR DELETE TO authenticated "
        "USING (public.has_project_access(project_id))",
    ),
    # ------------------------------------------------------------------
    # EVIDENCE
    # ------------------------------------------------------------------
    (
        "evidence",
        "evidence_select_policy",
        "CREATE POLICY evidence_select_policy ON public.evidence "
        "FOR SELECT TO authenticated "
        "USING ("
        "  EXISTS ("
        "    SELECT 1 FROM public.investigations inv "
        "    WHERE inv.id = evidence.investigation_id "
        "      AND public.has_project_access(inv.project_id)"
        "  )"
        ")",
    ),
    (
        "evidence",
        "evidence_insert_policy",
        "CREATE POLICY evidence_insert_policy ON public.evidence "
        "FOR INSERT TO authenticated "
        "WITH CHECK ("
        "  EXISTS ("
        "    SELECT 1 FROM public.investigations inv "
        "    WHERE inv.id = evidence.investigation_id "
        "      AND public.has_project_access(inv.project_id)"
        "  )"
        ")",
    ),
    (
        "evidence",
        "evidence_update_policy",
        "CREATE POLICY evidence_update_policy ON public.evidence "
        "FOR UPDATE TO authenticated "
        "USING ("
        "  EXISTS ("
        "    SELECT 1 FROM public.investigations inv "
        "    WHERE inv.id = evidence.investigation_id "
        "      AND public.has_project_access(inv.project_id)"
        "  )"
        ") "
        "WITH CHECK ("
        "  EXISTS ("
        "    SELECT 1 FROM public.investigations inv "
        "    WHERE inv.id = evidence.investigation_id "
        "      AND public.has_project_access(inv.project_id)"
        "  )"
        ")",
    ),
    (
        "evidence",
        "evidence_delete_policy",
        "CREATE POLICY evidence_delete_policy ON public.evidence "
        "FOR DELETE TO authenticated "
        "USING ("
        "  EXISTS ("
        "    SELECT 1 FROM public.investigations inv "
        "    WHERE inv.id = evidence.investigation_id "
        "      AND public.has_project_access(inv.project_id)"
        "  )"
        ")",
    ),
    # ------------------------------------------------------------------
    # DEPLOYMENTS
    # ------------------------------------------------------------------
    (
        "deployments",
        "deployments_select_policy",
        "CREATE POLICY deployments_select_policy ON public.deployments "
        "FOR SELECT TO authenticated "
        "USING (public.has_project_access(project_id))",
    ),
    (
        "deployments",
        "deployments_insert_policy",
        "CREATE POLICY deployments_insert_policy ON public.deployments "
        "FOR INSERT TO authenticated "
        "WITH CHECK (public.has_project_access(project_id))",
    ),
    (
        "deployments",
        "deployments_update_policy",
        "CREATE POLICY deployments_update_policy ON public.deployments "
        "FOR UPDATE TO authenticated "
        "USING (public.has_project_access(project_id)) "
        "WITH CHECK (public.has_project_access(project_id))",
    ),
    (
        "deployments",
        "deployments_delete_policy",
        "CREATE POLICY deployments_delete_policy ON public.deployments "
        "FOR DELETE TO authenticated "
        "USING (public.has_project_access(project_id))",
    ),
    # ------------------------------------------------------------------
    # FIX_PROPOSALS
    # ------------------------------------------------------------------
    (
        "fix_proposals",
        "fix_proposals_select_policy",
        "CREATE POLICY fix_proposals_select_policy ON public.fix_proposals "
        "FOR SELECT TO authenticated "
        "USING ("
        "  EXISTS ("
        "    SELECT 1 FROM public.investigations inv "
        "    WHERE inv.id = fix_proposals.investigation_id "
        "      AND public.has_project_access(inv.project_id)"
        "  )"
        ")",
    ),
    (
        "fix_proposals",
        "fix_proposals_insert_policy",
        "CREATE POLICY fix_proposals_insert_policy ON public.fix_proposals "
        "FOR INSERT TO authenticated "
        "WITH CHECK ("
        "  EXISTS ("
        "    SELECT 1 FROM public.investigations inv "
        "    WHERE inv.id = fix_proposals.investigation_id "
        "      AND public.has_project_access(inv.project_id)"
        "  )"
        ")",
    ),
    (
        "fix_proposals",
        "fix_proposals_update_policy",
        "CREATE POLICY fix_proposals_update_policy ON public.fix_proposals "
        "FOR UPDATE TO authenticated "
        "USING ("
        "  EXISTS ("
        "    SELECT 1 FROM public.investigations inv "
        "    WHERE inv.id = fix_proposals.investigation_id "
        "      AND public.has_project_access(inv.project_id)"
        "  )"
        ") "
        "WITH CHECK ("
        "  EXISTS ("
        "    SELECT 1 FROM public.investigations inv "
        "    WHERE inv.id = fix_proposals.investigation_id "
        "      AND public.has_project_access(inv.project_id)"
        "  )"
        ")",
    ),
    (
        "fix_proposals",
        "fix_proposals_delete_policy",
        "CREATE POLICY fix_proposals_delete_policy ON public.fix_proposals "
        "FOR DELETE TO authenticated "
        "USING ("
        "  EXISTS ("
        "    SELECT 1 FROM public.investigations inv "
        "    WHERE inv.id = fix_proposals.investigation_id "
        "      AND public.has_project_access(inv.project_id)"
        "  )"
        ")",
    ),
    # ------------------------------------------------------------------
    # APPROVALS
    # ------------------------------------------------------------------
    (
        "approvals",
        "approvals_select_policy",
        "CREATE POLICY approvals_select_policy ON public.approvals "
        "FOR SELECT TO authenticated "
        "USING ("
        "  EXISTS ("
        "    SELECT 1 FROM public.fix_proposals fp "
        "    JOIN public.investigations inv ON fp.investigation_id = inv.id "
        "    WHERE fp.id = approvals.fix_proposal_id "
        "      AND public.has_project_access(inv.project_id)"
        "  )"
        ")",
    ),
    (
        "approvals",
        "approvals_insert_policy",
        "CREATE POLICY approvals_insert_policy ON public.approvals "
        "FOR INSERT TO authenticated "
        "WITH CHECK ("
        "  approver_id = (SELECT auth.uid()) "
        "  AND EXISTS ("
        "    SELECT 1 FROM public.fix_proposals fp "
        "    JOIN public.investigations inv ON fp.investigation_id = inv.id "
        "    WHERE fp.id = approvals.fix_proposal_id "
        "      AND public.has_project_access(inv.project_id)"
        "  )"
        ")",
    ),
    (
        "approvals",
        "approvals_update_policy",
        "CREATE POLICY approvals_update_policy ON public.approvals "
        "FOR UPDATE TO authenticated "
        "USING ("
        "  approver_id = (SELECT auth.uid()) "
        "  AND EXISTS ("
        "    SELECT 1 FROM public.fix_proposals fp "
        "    JOIN public.investigations inv ON fp.investigation_id = inv.id "
        "    WHERE fp.id = approvals.fix_proposal_id "
        "      AND public.has_project_access(inv.project_id)"
        "  )"
        ") "
        "WITH CHECK ("
        "  approver_id = (SELECT auth.uid()) "
        "  AND EXISTS ("
        "    SELECT 1 FROM public.fix_proposals fp "
        "    JOIN public.investigations inv ON fp.investigation_id = inv.id "
        "    WHERE fp.id = approvals.fix_proposal_id "
        "      AND public.has_project_access(inv.project_id)"
        "  )"
        ")",
    ),
    (
        "approvals",
        "approvals_delete_policy",
        "CREATE POLICY approvals_delete_policy ON public.approvals "
        "FOR DELETE TO authenticated "
        "USING ("
        "  approver_id = (SELECT auth.uid()) "
        "  AND EXISTS ("
        "    SELECT 1 FROM public.fix_proposals fp "
        "    JOIN public.investigations inv ON fp.investigation_id = inv.id "
        "    WHERE fp.id = approvals.fix_proposal_id "
        "      AND public.has_project_access(inv.project_id)"
        "  )"
        ")",
    ),
    # ------------------------------------------------------------------
    # AUDIT_LOGS (Append-only: SELECT & INSERT only; NO UPDATE or DELETE)
    # ------------------------------------------------------------------
    (
        "audit_logs",
        "audit_logs_select_policy",
        "CREATE POLICY audit_logs_select_policy ON public.audit_logs "
        "FOR SELECT TO authenticated "
        "USING ("
        "  (project_id IS NOT NULL AND public.has_project_access(project_id)) "
        "  OR actor_id = (SELECT auth.uid())"
        ")",
    ),
    (
        "audit_logs",
        "audit_logs_insert_policy",
        "CREATE POLICY audit_logs_insert_policy ON public.audit_logs "
        "FOR INSERT TO authenticated "
        "WITH CHECK ("
        "  (actor_id IS NULL OR actor_id = (SELECT auth.uid())) "
        "  AND (project_id IS NULL OR public.has_project_access(project_id))"
        ")",
    ),
]


def upgrade() -> None:
    # 1. Ensure Supabase / PostgreSQL auth roles and functions exist
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                CREATE ROLE authenticated;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
                CREATE ROLE anon;
            END IF;

            IF NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'auth') THEN
                CREATE SCHEMA auth;
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM pg_proc p
                JOIN pg_namespace n ON p.pronamespace = n.oid
                WHERE n.nspname = 'auth' AND p.proname = 'uid'
            ) THEN
                EXECUTE 'CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS $fn$ SELECT NULLIF(current_setting(''request.jwt.claim.sub'', true), '''')::uuid; $fn$';
            END IF;
        END $$;
        """
    )

    # 2. Authorization Helper Functions
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.has_project_access(p_project_id uuid)
        RETURNS boolean
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = public
        AS $$
          SELECT EXISTS (
            SELECT 1 FROM public.projects
            WHERE id = p_project_id AND owner_id = (SELECT auth.uid())
          );
        $$;
        """
    )

    # 3. Grant schema and table access to authenticated role
    op.execute("GRANT USAGE ON SCHEMA public TO authenticated, anon;")
    op.execute("GRANT ALL ON ALL TABLES IN SCHEMA public TO authenticated;")
    op.execute("GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO authenticated;")

    # 4. Enable Row Level Security (RLS) on all tables
    for table in TABLES:
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY;")

    # 5. Define RLS Policies individually
    for _table, _policy_name, policy_sql in POLICIES:
        op.execute(policy_sql)


def downgrade() -> None:
    # Drop all policies
    for table, policy_name, _ in reversed(POLICIES):
        op.execute(f"DROP POLICY IF EXISTS {policy_name} ON public.{table};")

    # Disable RLS on all tables
    for table in TABLES:
        op.execute(f"ALTER TABLE public.{table} DISABLE ROW LEVEL SECURITY;")

    # Drop helper function
    op.execute("DROP FUNCTION IF EXISTS public.has_project_access(uuid);")
