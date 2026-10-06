"""Add incident-scoped chat history for Phase 16.1.

Revision ID: 0006_chat_history
Revises: 0005_investigation_api
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_chat_history"
down_revision = "0005_investigation_api"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_incidents_id_project",
        "incidents",
        ["id", "project_id"],
        schema="public",
    )
    op.create_table(
        "chat_conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("incident_id", sa.Uuid(), nullable=False),
        sa.Column("investigation_id", sa.Uuid(), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["public.projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["incident_id", "project_id"],
            ["public.incidents.id", "public.incidents.project_id"],
            ondelete="CASCADE",
            name="fk_chat_conversations_incident_project",
        ),
        sa.ForeignKeyConstraint(["investigation_id"], ["public.investigations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["public.users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "project_id", name="uq_chat_conversations_id_project"),
        schema="public",
    )
    op.create_index(
        "ix_chat_conversations_project_incident_updated",
        "chat_conversations",
        ["project_id", "incident_id", "updated_at"],
        schema="public",
    )
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("role IN ('user', 'assistant')", name="ck_chat_messages_role"),
        sa.ForeignKeyConstraint(
            ["conversation_id", "project_id"],
            ["public.chat_conversations.id", "public.chat_conversations.project_id"],
            ondelete="CASCADE",
            name="fk_chat_messages_conversation_project",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["public.projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        schema="public",
    )
    op.create_index(
        "ix_chat_messages_conversation_created",
        "chat_messages",
        ["conversation_id", "created_at", "id"],
        schema="public",
    )

    for table in ("chat_conversations", "chat_messages"):
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"GRANT ALL ON TABLE public.{table} TO authenticated;")

    op.execute(
        "CREATE POLICY chat_conversations_select_policy ON public.chat_conversations "
        "FOR SELECT TO authenticated USING (public.has_project_access(project_id));"
    )
    op.execute(
        "CREATE POLICY chat_conversations_insert_policy ON public.chat_conversations "
        "FOR INSERT TO authenticated WITH CHECK (public.has_project_access(project_id));"
    )
    op.execute(
        "CREATE POLICY chat_conversations_update_policy ON public.chat_conversations "
        "FOR UPDATE TO authenticated USING (public.has_project_access(project_id)) "
        "WITH CHECK (public.has_project_access(project_id));"
    )
    op.execute(
        "CREATE POLICY chat_conversations_delete_policy ON public.chat_conversations "
        "FOR DELETE TO authenticated USING (public.has_project_access(project_id));"
    )
    op.execute(
        "CREATE POLICY chat_messages_select_policy ON public.chat_messages "
        "FOR SELECT TO authenticated USING (public.has_project_access(project_id));"
    )
    op.execute(
        "CREATE POLICY chat_messages_insert_policy ON public.chat_messages "
        "FOR INSERT TO authenticated WITH CHECK (public.has_project_access(project_id));"
    )
    op.execute(
        "CREATE POLICY chat_messages_delete_policy ON public.chat_messages "
        "FOR DELETE TO authenticated USING (public.has_project_access(project_id));"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS chat_messages_delete_policy ON public.chat_messages;")
    op.execute("DROP POLICY IF EXISTS chat_messages_insert_policy ON public.chat_messages;")
    op.execute("DROP POLICY IF EXISTS chat_messages_select_policy ON public.chat_messages;")
    op.execute("DROP POLICY IF EXISTS chat_conversations_delete_policy ON public.chat_conversations;")
    op.execute("DROP POLICY IF EXISTS chat_conversations_update_policy ON public.chat_conversations;")
    op.execute("DROP POLICY IF EXISTS chat_conversations_insert_policy ON public.chat_conversations;")
    op.execute("DROP POLICY IF EXISTS chat_conversations_select_policy ON public.chat_conversations;")
    op.drop_index("ix_chat_messages_conversation_created", table_name="chat_messages", schema="public")
    op.drop_table("chat_messages", schema="public")
    op.drop_index(
        "ix_chat_conversations_project_incident_updated",
        table_name="chat_conversations",
        schema="public",
    )
    op.drop_table("chat_conversations", schema="public")
    op.drop_constraint(
        "uq_incidents_id_project",
        "incidents",
        type_="unique",
        schema="public",
    )
