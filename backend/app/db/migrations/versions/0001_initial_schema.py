"""Phase 3 initial database schema.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-09-27

Creates all 10 core DEVDOC domain tables and enums:
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
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # ENUMS
    # ------------------------------------------------------------------
    vcs_provider_enum = sa.Enum("github", "gitlab", "bitbucket", name="vcsprovider")
    incident_severity_enum = sa.Enum("critical", "high", "medium", "low", "info", name="incidentseverity")
    incident_status_enum = sa.Enum("open", "investigating", "mitigated", "resolved", "closed", name="incidentstatus")
    investigation_status_enum = sa.Enum(
        "pending", "running", "completed", "failed", "cancelled", name="investigationstatus"
    )
    evidence_kind_enum = sa.Enum(
        "log_excerpt",
        "stack_trace",
        "metric_snapshot",
        "config_diff",
        "commit_diff",
        "ci_log",
        "container_log",
        "documentation",
        "other",
        name="evidencekind",
    )
    deployment_status_enum = sa.Enum(
        "pending", "running", "success", "failed", "rolled_back", "cancelled", name="deploymentstatus"
    )
    fix_status_enum = sa.Enum(
        "draft",
        "sandbox_pending",
        "sandbox_running",
        "sandbox_passed",
        "sandbox_failed",
        "awaiting_approval",
        "approved",
        "rejected",
        "applied",
        "reverted",
        name="fixstatus",
    )
    approval_decision_enum = sa.Enum("approved", "rejected", name="approvaldecision")
    audit_outcome_enum = sa.Enum("success", "failure", "partial", name="auditoutcome")

    # ------------------------------------------------------------------
    # 1. users
    # ------------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("avatar_url", sa.String(length=2048), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_superuser", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("provider_user_id", sa.String(length=256), nullable=True),
        sa.Column("last_sign_in_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_provider_provider_user_id", "users", ["provider", "provider_user_id"])

    # ------------------------------------------------------------------
    # 2. projects
    # ------------------------------------------------------------------
    op.create_table(
        "projects",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("settings_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("owner_id", "slug", name="uq_projects_owner_slug"),
    )
    op.create_index("ix_projects_slug", "projects", ["slug"])
    op.create_index("ix_projects_owner_id", "projects", ["owner_id"])
    op.create_index("ix_projects_owner_id_is_active", "projects", ["owner_id", "is_active"])

    # ------------------------------------------------------------------
    # 3. repositories
    # ------------------------------------------------------------------
    op.create_table(
        "repositories",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", vcs_provider_enum, nullable=False),
        sa.Column("full_name", sa.String(length=512), nullable=False),
        sa.Column("provider_repo_id", sa.String(length=128), nullable=True),
        sa.Column("clone_url", sa.String(length=2048), nullable=True),
        sa.Column("default_branch", sa.String(length=255), nullable=False, server_default=sa.text("'main'")),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("language", sa.String(length=64), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("project_id", "provider", "full_name", name="uq_repositories_project_provider_name"),
    )
    op.create_index("ix_repositories_project_id", "repositories", ["project_id"])
    op.create_index("ix_repositories_full_name", "repositories", ["full_name"])
    op.create_index("ix_repositories_project_id_is_active", "repositories", ["project_id", "is_active"])

    # ------------------------------------------------------------------
    # 4. incidents
    # ------------------------------------------------------------------
    op.create_table(
        "incidents",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("repository_id", sa.Uuid(), sa.ForeignKey("repositories.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reported_by_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("severity", incident_severity_enum, nullable=False, server_default=sa.text("'medium'")),
        sa.Column("status", incident_status_enum, nullable=False, server_default=sa.text("'open'")),
        sa.Column("external_ref", sa.String(length=256), nullable=True),
        sa.Column("affected_users", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("affected_users >= 0", name="ck_incidents_affected_users_non_negative"),
    )
    op.create_index("ix_incidents_project_id", "incidents", ["project_id"])
    op.create_index("ix_incidents_repository_id", "incidents", ["repository_id"])
    op.create_index("ix_incidents_reported_by_id", "incidents", ["reported_by_id"])
    op.create_index("ix_incidents_status", "incidents", ["status"])
    op.create_index("ix_incidents_project_id_status", "incidents", ["project_id", "status"])
    op.create_index("ix_incidents_project_id_severity", "incidents", ["project_id", "severity"])

    # ------------------------------------------------------------------
    # 5. investigations
    # ------------------------------------------------------------------
    op.create_table(
        "investigations",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("incident_id", sa.Uuid(), sa.ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("initiated_by_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", investigation_status_enum, nullable=False, server_default=sa.text("'pending'")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("root_cause_summary", sa.Text(), nullable=True),
        sa.Column("confidence_score", sa.Integer(), nullable=True),
        sa.Column("tokens_used", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("estimated_cost_usd", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 100)",
            name="ck_investigations_confidence_score_range",
        ),
        sa.CheckConstraint("tokens_used >= 0", name="ck_investigations_tokens_non_negative"),
        sa.CheckConstraint("estimated_cost_usd >= 0", name="ck_investigations_cost_non_negative"),
    )
    op.create_index("ix_investigations_project_id", "investigations", ["project_id"])
    op.create_index("ix_investigations_incident_id", "investigations", ["incident_id"])
    op.create_index("ix_investigations_initiated_by_id", "investigations", ["initiated_by_id"])
    op.create_index("ix_investigations_status", "investigations", ["status"])
    op.create_index("ix_investigations_project_id_status", "investigations", ["project_id", "status"])
    op.create_index("ix_investigations_incident_id_status", "investigations", ["incident_id", "status"])

    # ------------------------------------------------------------------
    # 6. evidence
    # ------------------------------------------------------------------
    op.create_table(
        "evidence",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("investigation_id", sa.Uuid(), sa.ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", evidence_kind_enum, nullable=False),
        sa.Column("label", sa.String(length=512), nullable=False),
        sa.Column("raw_content", sa.Text(), nullable=True),
        sa.Column("source_url", sa.String(length=2048), nullable=True),
        sa.Column("source_metadata", sa.Text(), nullable=True),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("relevance_score", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "relevance_score IS NULL OR (relevance_score >= 0 AND relevance_score <= 100)",
            name="ck_evidence_relevance_score_range",
        ),
    )
    op.create_index("ix_evidence_investigation_id", "evidence", ["investigation_id"])
    op.create_index("ix_evidence_kind", "evidence", ["kind"])
    op.create_index("ix_evidence_investigation_id_kind", "evidence", ["investigation_id", "kind"])

    # ------------------------------------------------------------------
    # 7. deployments
    # ------------------------------------------------------------------
    op.create_table(
        "deployments",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("repository_id", sa.Uuid(), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("triggered_by_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("commit_sha", sa.String(length=40), nullable=False),
        sa.Column("ref", sa.String(length=255), nullable=False),
        sa.Column("environment", sa.String(length=100), nullable=False),
        sa.Column("status", deployment_status_enum, nullable=False, server_default=sa.text("'pending'")),
        sa.Column("pipeline_url", sa.String(length=2048), nullable=True),
        sa.Column("pipeline_id", sa.String(length=256), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("log_excerpt", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "length(commit_sha) = 40 OR length(commit_sha) = 7",
            name="ck_deployments_commit_sha_length",
        ),
    )
    op.create_index("ix_deployments_project_id", "deployments", ["project_id"])
    op.create_index("ix_deployments_repository_id", "deployments", ["repository_id"])
    op.create_index("ix_deployments_triggered_by_id", "deployments", ["triggered_by_id"])
    op.create_index("ix_deployments_environment", "deployments", ["environment"])
    op.create_index("ix_deployments_status", "deployments", ["status"])
    op.create_index("ix_deployments_project_id_env_status", "deployments", ["project_id", "environment", "status"])
    op.create_index("ix_deployments_repository_id_environment", "deployments", ["repository_id", "environment"])

    # ------------------------------------------------------------------
    # 8. fix_proposals
    # ------------------------------------------------------------------
    op.create_table(
        "fix_proposals",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("investigation_id", sa.Uuid(), sa.ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("target_repository_id", sa.Uuid(), sa.ForeignKey("repositories.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("patch_content", sa.Text(), nullable=True),
        sa.Column("affected_files", sa.Text(), nullable=True),
        sa.Column("status", fix_status_enum, nullable=False, server_default=sa.text("'draft'")),
        sa.Column("sandbox_run_id", sa.String(length=256), nullable=True),
        sa.Column("sandbox_log", sa.Text(), nullable=True),
        sa.Column("confidence_score", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 100)",
            name="ck_fix_proposals_confidence_score_range",
        ),
    )
    op.create_index("ix_fix_proposals_investigation_id", "fix_proposals", ["investigation_id"])
    op.create_index("ix_fix_proposals_created_by_id", "fix_proposals", ["created_by_id"])
    op.create_index("ix_fix_proposals_target_repository_id", "fix_proposals", ["target_repository_id"])
    op.create_index("ix_fix_proposals_status", "fix_proposals", ["status"])
    op.create_index("ix_fix_proposals_investigation_id_status", "fix_proposals", ["investigation_id", "status"])

    # ------------------------------------------------------------------
    # 9. approvals
    # ------------------------------------------------------------------
    op.create_table(
        "approvals",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("fix_proposal_id", sa.Uuid(), sa.ForeignKey("fix_proposals.id", ondelete="CASCADE"), nullable=False),
        sa.Column("approver_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("decision", approval_decision_enum, nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("applied_commit_sha", sa.String(length=40), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("fix_proposal_id", "approver_id", name="uq_approvals_fix_proposal_approver"),
    )
    op.create_index("ix_approvals_fix_proposal_id", "approvals", ["fix_proposal_id"])
    op.create_index("ix_approvals_approver_id", "approvals", ["approver_id"])
    op.create_index("ix_approvals_decision", "approvals", ["decision"])
    op.create_index("ix_approvals_fix_proposal_id_decision", "approvals", ["fix_proposal_id", "decision"])

    # ------------------------------------------------------------------
    # 10. audit_logs
    # ------------------------------------------------------------------
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=True),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("diff", sa.Text(), nullable=True),
        sa.Column("outcome", audit_outcome_enum, nullable=True),
        sa.Column("session_id", sa.String(length=128), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_audit_logs_actor_id", "audit_logs", ["actor_id"])
    op.create_index("ix_audit_logs_project_id", "audit_logs", ["project_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_entity_type", "audit_logs", ["entity_type"])
    op.create_index("ix_audit_logs_entity_id", "audit_logs", ["entity_id"])
    op.create_index("ix_audit_logs_outcome", "audit_logs", ["outcome"])
    op.create_index("ix_audit_logs_session_id", "audit_logs", ["session_id"])
    op.create_index("ix_audit_logs_project_id_action", "audit_logs", ["project_id", "action"])
    op.create_index("ix_audit_logs_actor_id_created_at", "audit_logs", ["actor_id", "created_at"])
    op.create_index("ix_audit_logs_entity_type_entity_id", "audit_logs", ["entity_type", "entity_id"])


def downgrade() -> None:
    # Drop tables in reverse dependency order
    op.drop_table("audit_logs")
    op.drop_table("approvals")
    op.drop_table("fix_proposals")
    op.drop_table("deployments")
    op.drop_table("evidence")
    op.drop_table("investigations")
    op.drop_table("incidents")
    op.drop_table("repositories")
    op.drop_table("projects")
    op.drop_table("users")

    # Drop enum types
    sa.Enum(name="auditoutcome").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="approvaldecision").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="fixstatus").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="deploymentstatus").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="evidencekind").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="investigationstatus").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="incidentstatus").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="incidentseverity").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="vcsprovider").drop(op.get_bind(), checkfirst=True)
