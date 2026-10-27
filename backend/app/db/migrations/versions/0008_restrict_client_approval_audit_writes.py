"""Restrict direct authenticated-client writes to approval and audit records.

Revision ID: 0008_restrict_approval_audit
Revises: 0007_human_approval_audit
"""

from __future__ import annotations

from alembic import op

revision = "0008_restrict_approval_audit"
down_revision = "0007_human_approval_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Approval eligibility and audit provenance are enforced by trusted backend
    # services and database triggers, not by client-supplied row values.
    op.execute("DROP POLICY IF EXISTS approvals_insert_policy ON public.approvals;")
    op.execute("DROP POLICY IF EXISTS approvals_update_policy ON public.approvals;")
    op.execute("DROP POLICY IF EXISTS audit_logs_insert_policy ON public.audit_logs;")


def downgrade() -> None:
    op.execute(
        """
        CREATE POLICY approvals_insert_policy ON public.approvals
        FOR INSERT TO authenticated WITH CHECK (
          requested_by_id = (SELECT auth.uid())
          AND status = 'pending'
          AND approver_id IS NULL
          AND decision IS NULL
          AND verification_id IS NOT NULL
          AND EXISTS (
            SELECT 1 FROM public.fix_proposals fp
            JOIN public.investigations inv ON inv.id = fp.investigation_id
            WHERE fp.id = approvals.fix_proposal_id
              AND public.has_project_access(inv.project_id)
          )
        );
        """
    )
    op.execute(
        """
        CREATE POLICY approvals_update_policy ON public.approvals
        FOR UPDATE TO authenticated
        USING (
          status = 'pending'
          AND EXISTS (
            SELECT 1 FROM public.fix_proposals fp
            JOIN public.investigations inv ON inv.id = fp.investigation_id
            WHERE fp.id = approvals.fix_proposal_id
              AND public.has_project_access(inv.project_id)
          )
        )
        WITH CHECK (
          status IN ('approved', 'rejected', 'cancelled', 'expired', 'superseded')
          AND EXISTS (
            SELECT 1 FROM public.fix_proposals fp
            JOIN public.investigations inv ON inv.id = fp.investigation_id
            WHERE fp.id = approvals.fix_proposal_id
              AND public.has_project_access(inv.project_id)
          )
        );
        """
    )
    op.execute(
        """
        CREATE POLICY audit_logs_insert_policy ON public.audit_logs
        FOR INSERT TO authenticated WITH CHECK (
          (actor_id IS NULL OR actor_id = (SELECT auth.uid()))
          AND (project_id IS NULL OR public.has_project_access(project_id))
        );
        """
    )
