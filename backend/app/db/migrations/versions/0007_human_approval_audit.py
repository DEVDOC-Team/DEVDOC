"""Persist verified review artifacts and make approvals human-controlled and auditable.

Revision ID: 0007_human_approval_audit
Revises: 0006_chat_history
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007_human_approval_audit"
down_revision = "0006_chat_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "approval_artifacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("investigation_id", sa.Uuid(), nullable=False),
        sa.Column("fix_proposal_id", sa.Uuid(), nullable=False),
        sa.Column("verification_status", sa.String(length=24), nullable=False),
        sa.Column("root_cause_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("proposal_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("proposal_record_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("verification_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("root_cause_snapshot", sa.Text(), nullable=False),
        sa.Column("proposal_snapshot", sa.Text(), nullable=False),
        sa.Column("verification_snapshot", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(root_cause_fingerprint) = 64 AND "
            "length(proposal_fingerprint) = 64 AND "
            "length(proposal_record_fingerprint) = 64 AND "
            "length(verification_fingerprint) = 64",
            name="ck_approval_artifacts_fingerprint_length",
        ),
        sa.CheckConstraint(
            "verification_status IN "
            "('passed', 'failed', 'inconclusive', 'timeout', 'cancelled', 'unsafe', 'setup_failed')",
            name="ck_approval_artifacts_verification_status",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["public.projects.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["investigation_id"], ["public.investigations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["fix_proposal_id"], ["public.fix_proposals.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "fix_proposal_id", "id", name="uq_approval_artifacts_proposal_id"
        ),
        schema="public",
    )
    op.create_index(
        "ix_approval_artifacts_project_id",
        "approval_artifacts",
        ["project_id"],
        schema="public",
    )
    op.create_index(
        "ix_approval_artifacts_investigation_id",
        "approval_artifacts",
        ["investigation_id"],
        schema="public",
    )
    op.create_index(
        "ix_approval_artifacts_fix_proposal_id",
        "approval_artifacts",
        ["fix_proposal_id"],
        schema="public",
    )
    op.create_index(
        "ix_approval_artifacts_project_created",
        "approval_artifacts",
        ["project_id", "created_at"],
        schema="public",
    )
    op.create_index(
        "ix_approval_artifacts_investigation_created",
        "approval_artifacts",
        ["investigation_id", "created_at"],
        schema="public",
    )

    op.add_column(
        "approvals",
        sa.Column("requested_by_id", sa.Uuid(), nullable=True),
        schema="public",
    )
    op.add_column(
        "approvals",
        sa.Column("verification_id", sa.Uuid(), nullable=True),
        schema="public",
    )
    op.add_column(
        "approvals",
        sa.Column("status", sa.String(length=16), nullable=True),
        schema="public",
    )
    op.add_column(
        "approvals",
        sa.Column("proposal_fingerprint", sa.String(length=64), nullable=True),
        schema="public",
    )
    op.add_column(
        "approvals",
        sa.Column("verification_fingerprint", sa.String(length=64), nullable=True),
        schema="public",
    )
    op.add_column(
        "approvals",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        schema="public",
    )
    op.add_column(
        "approvals",
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        schema="public",
    )
    op.execute(
        "UPDATE public.approvals SET requested_by_id = approver_id, "
        "status = decision::text, decided_at = created_at"
    )
    op.alter_column(
        "approvals", "requested_by_id", nullable=False, schema="public"
    )
    op.alter_column(
        "approvals",
        "status",
        nullable=False,
        server_default="pending",
        schema="public",
    )
    op.alter_column("approvals", "approver_id", nullable=True, schema="public")
    op.alter_column("approvals", "decision", nullable=True, schema="public")
    op.drop_constraint(
        "approvals_approver_id_fkey", "approvals", type_="foreignkey", schema="public"
    )
    op.create_foreign_key(
        "fk_approvals_approver_id_users",
        "approvals",
        "users",
        ["approver_id"],
        ["id"],
        source_schema="public",
        referent_schema="public",
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_approvals_requested_by_id_users",
        "approvals",
        "users",
        ["requested_by_id"],
        ["id"],
        source_schema="public",
        referent_schema="public",
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_approvals_proposal_verification",
        "approvals",
        "approval_artifacts",
        ["fix_proposal_id", "verification_id"],
        ["fix_proposal_id", "id"],
        source_schema="public",
        referent_schema="public",
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_approvals_status",
        "approvals",
        "status IN ('pending', 'approved', 'rejected', 'expired', 'cancelled', 'superseded')",
        schema="public",
    )
    op.create_check_constraint(
        "ck_approvals_state_consistency",
        "approvals",
        "(status = 'pending' AND decision IS NULL AND approver_id IS NULL AND decided_at IS NULL) "
        "OR (status = 'approved' AND decision = 'approved' AND approver_id IS NOT NULL "
        "AND decided_at IS NOT NULL) "
        "OR (status = 'rejected' AND decision = 'rejected' AND approver_id IS NOT NULL "
        "AND decided_at IS NOT NULL) "
        "OR (status IN ('expired', 'cancelled', 'superseded') AND decision IS NULL "
        "AND decided_at IS NOT NULL)",
        schema="public",
    )
    op.create_check_constraint(
        "ck_approvals_pending_binding",
        "approvals",
        "status <> 'pending' OR "
        "(verification_id IS NOT NULL AND proposal_fingerprint IS NOT NULL "
        "AND verification_fingerprint IS NOT NULL AND expires_at IS NOT NULL)",
        schema="public",
    )
    op.create_index(
        "ix_approvals_requested_by_id",
        "approvals",
        ["requested_by_id"],
        schema="public",
    )
    op.create_index(
        "ix_approvals_verification_id",
        "approvals",
        ["verification_id"],
        schema="public",
    )
    op.create_index(
        "ix_approvals_status",
        "approvals",
        ["status"],
        schema="public",
    )
    op.create_index(
        "ix_approvals_one_pending_per_proposal",
        "approvals",
        ["fix_proposal_id"],
        unique=True,
        schema="public",
        postgresql_where=sa.text("status = 'pending'"),
    )

    for policy in (
        "approvals_select_policy",
        "approvals_insert_policy",
        "approvals_update_policy",
        "approvals_delete_policy",
    ):
        op.execute(f"DROP POLICY IF EXISTS {policy} ON public.approvals;")
    op.execute(
        "CREATE POLICY approvals_select_policy ON public.approvals "
        "FOR SELECT TO authenticated USING (EXISTS ("
        "SELECT 1 FROM public.fix_proposals fp "
        "JOIN public.investigations inv ON inv.id = fp.investigation_id "
        "WHERE fp.id = approvals.fix_proposal_id "
        "AND public.has_project_access(inv.project_id)));"
    )
    op.execute(
        "CREATE POLICY approvals_insert_policy ON public.approvals "
        "FOR INSERT TO authenticated WITH CHECK ("
        "requested_by_id = (SELECT auth.uid()) "
        "AND status = 'pending' AND approver_id IS NULL AND decision IS NULL "
        "AND verification_id IS NOT NULL "
        "AND EXISTS (SELECT 1 FROM public.fix_proposals fp "
        "JOIN public.investigations inv ON inv.id = fp.investigation_id "
        "WHERE fp.id = approvals.fix_proposal_id "
        "AND public.has_project_access(inv.project_id)));"
    )
    op.execute(
        "CREATE POLICY approvals_update_policy ON public.approvals "
        "FOR UPDATE TO authenticated USING (status = 'pending' "
        "AND EXISTS (SELECT 1 FROM public.fix_proposals fp "
        "JOIN public.investigations inv ON inv.id = fp.investigation_id "
        "WHERE fp.id = approvals.fix_proposal_id "
        "AND public.has_project_access(inv.project_id))) "
        "WITH CHECK ("
        "status IN ('approved', 'rejected', 'cancelled', 'expired', 'superseded') "
        "AND EXISTS (SELECT 1 FROM public.fix_proposals fp "
        "JOIN public.investigations inv ON inv.id = fp.investigation_id "
        "WHERE fp.id = approvals.fix_proposal_id "
        "AND public.has_project_access(inv.project_id)));"
    )

    op.execute("ALTER TABLE public.approval_artifacts ENABLE ROW LEVEL SECURITY;")
    op.execute("GRANT SELECT ON TABLE public.approval_artifacts TO authenticated;")
    op.execute(
        "CREATE POLICY approval_artifacts_select_policy ON public.approval_artifacts "
        "FOR SELECT TO authenticated USING (public.has_project_access(project_id));"
    )
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
          ) OR EXISTS (
            SELECT 1 FROM public.users
            WHERE id = (SELECT auth.uid()) AND is_superuser = true
          );
        $$;
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.prevent_phase18_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          IF TG_TABLE_NAME = 'audit_logs'
             AND TG_OP = 'UPDATE'
             AND pg_trigger_depth() > 1
             AND OLD.actor_id IS NOT NULL
             AND NEW.actor_id IS NULL
             AND (to_jsonb(NEW) - 'actor_id') = (to_jsonb(OLD) - 'actor_id') THEN
            RETURN NEW;
          END IF;
          RAISE EXCEPTION 'Phase 18 records are immutable';
        END;
        $$;
        """
    )
    op.execute(
        "CREATE TRIGGER approval_artifacts_immutable "
        "BEFORE UPDATE OR DELETE ON public.approval_artifacts "
        "FOR EACH ROW EXECUTE FUNCTION public.prevent_phase18_mutation();"
    )
    op.execute(
        "CREATE TRIGGER audit_logs_immutable "
        "BEFORE UPDATE OR DELETE ON public.audit_logs "
        "FOR EACH ROW EXECUTE FUNCTION public.prevent_phase18_mutation();"
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.guard_approval_transition()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = public
        AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'Approval requests cannot be deleted';
          END IF;
          IF OLD.status <> 'pending' THEN
            RAISE EXCEPTION 'Terminal approval requests are immutable';
          END IF;
          IF NEW.status NOT IN ('approved', 'rejected', 'expired', 'cancelled', 'superseded') THEN
            RAISE EXCEPTION 'Invalid approval state transition';
          END IF;
          IF NEW.status IN ('approved', 'rejected') THEN
            IF NEW.approver_id IS DISTINCT FROM (SELECT auth.uid()) THEN
              RAISE EXCEPTION 'Decision actor must match the authenticated user';
            END IF;
            IF NEW.decided_at IS NULL OR NEW.rationale IS NULL
               OR length(btrim(NEW.rationale)) < 8 THEN
              RAISE EXCEPTION 'A decision timestamp and meaningful reason are required';
            END IF;
            IF (NEW.status = 'approved' AND NEW.decision <> 'approved')
               OR (NEW.status = 'rejected' AND NEW.decision <> 'rejected') THEN
              RAISE EXCEPTION 'Decision does not match approval state';
            END IF;
          ELSIF NEW.decision IS NOT NULL OR NEW.approver_id IS NOT NULL THEN
            RAISE EXCEPTION 'Non-decision terminal transitions cannot impersonate a reviewer';
          END IF;
          IF NEW.status = 'cancelled' THEN
            IF NEW.requested_by_id IS DISTINCT FROM (SELECT auth.uid())
               AND NOT EXISTS (
                 SELECT 1 FROM public.users
                 WHERE id = (SELECT auth.uid()) AND is_superuser = true
               ) THEN
              RAISE EXCEPTION 'Only the requester or a platform administrator can cancel';
            END IF;
            IF NEW.rationale IS NULL OR length(btrim(NEW.rationale)) < 8 THEN
              RAISE EXCEPTION 'A meaningful cancellation reason is required';
            END IF;
          ELSIF NEW.status = 'expired'
                AND (NEW.expires_at IS NULL OR NEW.expires_at > now()) THEN
            RAISE EXCEPTION 'An approval request cannot expire before its deadline';
          END IF;
          IF NEW.fix_proposal_id IS DISTINCT FROM OLD.fix_proposal_id
             OR NEW.requested_by_id IS DISTINCT FROM OLD.requested_by_id
             OR NEW.verification_id IS DISTINCT FROM OLD.verification_id
             OR NEW.proposal_fingerprint IS DISTINCT FROM OLD.proposal_fingerprint
             OR NEW.verification_fingerprint IS DISTINCT FROM OLD.verification_fingerprint
             OR NEW.expires_at IS DISTINCT FROM OLD.expires_at
             OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
            RAISE EXCEPTION 'Approval binding fields are immutable';
          END IF;
          RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        "CREATE TRIGGER approvals_state_guard "
        "BEFORE UPDATE OR DELETE ON public.approvals "
        "FOR EACH ROW EXECUTE FUNCTION public.guard_approval_transition();"
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.audit_approval_change()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = public
        AS $$
        DECLARE
          v_project_id uuid;
          v_actor_id uuid;
          v_action text;
          v_status text;
        BEGIN
          SELECT inv.project_id INTO v_project_id
          FROM public.fix_proposals fp
          JOIN public.investigations inv ON inv.id = fp.investigation_id
          WHERE fp.id = NEW.fix_proposal_id;
          v_actor_id := COALESCE((SELECT auth.uid()), NEW.approver_id, NEW.requested_by_id);
          IF TG_OP = 'INSERT' THEN
            v_action := 'approval.requested';
          ELSE
            v_action := 'approval.' || NEW.status;
          END IF;
          v_status := NEW.status;
          INSERT INTO public.audit_logs (
            actor_id, project_id, action, entity_type, entity_id,
            description, diff, outcome, session_id, created_at, updated_at
          ) VALUES (
            v_actor_id, v_project_id, v_action, 'approval', NEW.id,
            'Phase 18 approval request lifecycle event.',
            json_build_object(
              'proposal_id', NEW.fix_proposal_id,
              'verification_id', NEW.verification_id,
              'proposal_fingerprint', NEW.proposal_fingerprint,
              'verification_fingerprint', NEW.verification_fingerprint,
              'status', v_status,
              'reason', NEW.rationale
            )::text,
            'success', current_setting('devdoc.request_id', true), now(), now()
          );
          RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        "CREATE TRIGGER approvals_audit_insert "
        "AFTER INSERT ON public.approvals "
        "FOR EACH ROW EXECUTE FUNCTION public.audit_approval_change();"
    )
    op.execute(
        "CREATE TRIGGER approvals_audit_transition "
        "AFTER UPDATE OF status ON public.approvals "
        "FOR EACH ROW WHEN (OLD.status IS DISTINCT FROM NEW.status) "
        "EXECUTE FUNCTION public.audit_approval_change();"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS approvals_audit_transition ON public.approvals;")
    op.execute("DROP TRIGGER IF EXISTS approvals_audit_insert ON public.approvals;")
    op.execute("DROP TRIGGER IF EXISTS approvals_state_guard ON public.approvals;")
    op.execute("DROP TRIGGER IF EXISTS audit_logs_immutable ON public.audit_logs;")
    op.execute("DROP TRIGGER IF EXISTS approval_artifacts_immutable ON public.approval_artifacts;")
    op.execute("DROP FUNCTION IF EXISTS public.audit_approval_change();")
    op.execute("DROP FUNCTION IF EXISTS public.guard_approval_transition();")
    op.execute("DROP FUNCTION IF EXISTS public.prevent_phase18_mutation();")
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
    op.execute("DROP POLICY IF EXISTS approval_artifacts_select_policy ON public.approval_artifacts;")
    op.execute("ALTER TABLE public.approval_artifacts DISABLE ROW LEVEL SECURITY;")
    for policy in (
        "approvals_update_policy",
        "approvals_insert_policy",
        "approvals_select_policy",
    ):
        op.execute(f"DROP POLICY IF EXISTS {policy} ON public.approvals;")
    op.execute(
        "CREATE POLICY approvals_select_policy ON public.approvals "
        "FOR SELECT TO authenticated USING (EXISTS ("
        "SELECT 1 FROM public.fix_proposals fp "
        "JOIN public.investigations inv ON fp.investigation_id = inv.id "
        "WHERE fp.id = approvals.fix_proposal_id "
        "AND public.has_project_access(inv.project_id)));"
    )
    op.execute(
        "CREATE POLICY approvals_insert_policy ON public.approvals "
        "FOR INSERT TO authenticated WITH CHECK (approver_id = (SELECT auth.uid()) "
        "AND EXISTS (SELECT 1 FROM public.fix_proposals fp "
        "JOIN public.investigations inv ON fp.investigation_id = inv.id "
        "WHERE fp.id = approvals.fix_proposal_id "
        "AND public.has_project_access(inv.project_id)));"
    )
    op.execute(
        "CREATE POLICY approvals_update_policy ON public.approvals "
        "FOR UPDATE TO authenticated USING (approver_id = (SELECT auth.uid()) "
        "AND EXISTS (SELECT 1 FROM public.fix_proposals fp "
        "JOIN public.investigations inv ON fp.investigation_id = inv.id "
        "WHERE fp.id = approvals.fix_proposal_id "
        "AND public.has_project_access(inv.project_id))) "
        "WITH CHECK (approver_id = (SELECT auth.uid()) "
        "AND EXISTS (SELECT 1 FROM public.fix_proposals fp "
        "JOIN public.investigations inv ON fp.investigation_id = inv.id "
        "WHERE fp.id = approvals.fix_proposal_id "
        "AND public.has_project_access(inv.project_id)));"
    )
    op.execute(
        "CREATE POLICY approvals_delete_policy ON public.approvals "
        "FOR DELETE TO authenticated USING (approver_id = (SELECT auth.uid()) "
        "AND EXISTS (SELECT 1 FROM public.fix_proposals fp "
        "JOIN public.investigations inv ON fp.investigation_id = inv.id "
        "WHERE fp.id = approvals.fix_proposal_id "
        "AND public.has_project_access(inv.project_id)));"
    )

    op.drop_index(
        "ix_approvals_one_pending_per_proposal", table_name="approvals", schema="public"
    )
    op.drop_index("ix_approvals_status", table_name="approvals", schema="public")
    op.drop_index("ix_approvals_verification_id", table_name="approvals", schema="public")
    op.drop_index("ix_approvals_requested_by_id", table_name="approvals", schema="public")
    op.drop_constraint("ck_approvals_state_consistency", "approvals", schema="public")
    op.drop_constraint("ck_approvals_pending_binding", "approvals", schema="public")
    op.drop_constraint("ck_approvals_status", "approvals", schema="public")
    op.drop_constraint(
        "fk_approvals_proposal_verification", "approvals", type_="foreignkey", schema="public"
    )
    op.drop_constraint(
        "fk_approvals_requested_by_id_users", "approvals", type_="foreignkey", schema="public"
    )
    op.drop_constraint(
        "fk_approvals_approver_id_users", "approvals", type_="foreignkey", schema="public"
    )
    op.drop_column("approvals", "decided_at", schema="public")
    op.drop_column("approvals", "expires_at", schema="public")
    op.drop_column("approvals", "verification_fingerprint", schema="public")
    op.drop_column("approvals", "proposal_fingerprint", schema="public")
    op.drop_column("approvals", "status", schema="public")
    op.drop_column("approvals", "verification_id", schema="public")
    op.drop_column("approvals", "requested_by_id", schema="public")
    op.alter_column("approvals", "decision", nullable=False, schema="public")
    op.alter_column("approvals", "approver_id", nullable=False, schema="public")
    op.create_foreign_key(
        "approvals_approver_id_fkey",
        "approvals",
        "users",
        ["approver_id"],
        ["id"],
        source_schema="public",
        referent_schema="public",
        ondelete="CASCADE",
    )
    op.drop_index(
        "ix_approval_artifacts_investigation_created",
        table_name="approval_artifacts",
        schema="public",
    )
    op.drop_index(
        "ix_approval_artifacts_project_created",
        table_name="approval_artifacts",
        schema="public",
    )
    op.drop_index(
        "ix_approval_artifacts_fix_proposal_id",
        table_name="approval_artifacts",
        schema="public",
    )
    op.drop_index(
        "ix_approval_artifacts_investigation_id",
        table_name="approval_artifacts",
        schema="public",
    )
    op.drop_index(
        "ix_approval_artifacts_project_id",
        table_name="approval_artifacts",
        schema="public",
    )
    op.drop_table("approval_artifacts", schema="public")
