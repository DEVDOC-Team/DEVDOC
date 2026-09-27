"""Add user_github_connections table with Row Level Security.

Revision ID: 0003_github_connections
Revises: 0002_row_level_security
Create Date: 2026-09-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0003_github_connections"
down_revision = "0002_row_level_security"
branch_labels = None
depends_on = None

POLICIES = [
    (
        "user_github_connections_select_policy",
        "CREATE POLICY user_github_connections_select_policy ON public.user_github_connections "
        "FOR SELECT TO authenticated "
        "USING (user_id = (SELECT auth.uid()))",
    ),
    (
        "user_github_connections_insert_policy",
        "CREATE POLICY user_github_connections_insert_policy ON public.user_github_connections "
        "FOR INSERT TO authenticated "
        "WITH CHECK (user_id = (SELECT auth.uid()))",
    ),
    (
        "user_github_connections_update_policy",
        "CREATE POLICY user_github_connections_update_policy ON public.user_github_connections "
        "FOR UPDATE TO authenticated "
        "USING (user_id = (SELECT auth.uid())) "
        "WITH CHECK (user_id = (SELECT auth.uid()))",
    ),
    (
        "user_github_connections_delete_policy",
        "CREATE POLICY user_github_connections_delete_policy ON public.user_github_connections "
        "FOR DELETE TO authenticated "
        "USING (user_id = (SELECT auth.uid()))",
    ),
]


def upgrade() -> None:
    # 1. Create user_github_connections table
    op.create_table(
        "user_github_connections",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("public.users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("github_user_id", sa.String(length=128), nullable=False),
        sa.Column("github_username", sa.String(length=255), nullable=False),
        sa.Column("avatar_url", sa.String(length=2048), nullable=True),
        sa.Column("access_token", sa.Text(), nullable=False),
        sa.Column("token_type", sa.String(length=64), nullable=False, server_default="bearer"),
        sa.Column("scope", sa.String(length=512), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        schema="public",
    )

    op.create_index(
        "ix_user_github_connections_user_id",
        "user_github_connections",
        ["user_id"],
        unique=True,
        schema="public",
    )
    op.create_index(
        "ix_user_github_connections_github_user_id",
        "user_github_connections",
        ["github_user_id"],
        schema="public",
    )
    op.create_index(
        "ix_user_github_connections_github_username",
        "user_github_connections",
        ["github_username"],
        schema="public",
    )

    # 2. Grant table permissions to authenticated role
    op.execute("GRANT ALL ON TABLE public.user_github_connections TO authenticated;")

    # 3. Enable RLS
    op.execute("ALTER TABLE public.user_github_connections ENABLE ROW LEVEL SECURITY;")

    # 4. Create RLS Policies
    for _policy_name, policy_sql in POLICIES:
        op.execute(policy_sql)


def downgrade() -> None:
    # 1. Drop RLS policies
    for policy_name, _ in reversed(POLICIES):
        op.execute(f"DROP POLICY IF EXISTS {policy_name} ON public.user_github_connections;")

    # 2. Disable RLS
    op.execute("ALTER TABLE public.user_github_connections DISABLE ROW LEVEL SECURITY;")

    # 3. Drop table
    op.drop_table("user_github_connections", schema="public")
