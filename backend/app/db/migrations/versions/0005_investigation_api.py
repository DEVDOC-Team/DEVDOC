"""Add summary and started_at to investigations, remove speculative root_cause_summary and confidence_score.

Revision ID: 0005_investigation_api
Revises: 0004_incident_management
Create Date: 2026-09-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0005_investigation_api"
down_revision = "0004_incident_management"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add summary and started_at columns to investigations table
    op.add_column(
        "investigations",
        sa.Column(
            "summary",
            sa.Text(),
            nullable=True,
        ),
        schema="public",
    )
    op.add_column(
        "investigations",
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        schema="public",
    )

    # 2. Create indexes
    op.create_index(
        "ix_investigations_started_at",
        "investigations",
        ["started_at"],
        schema="public",
    )
    op.create_index(
        "ix_investigations_created_at",
        "investigations",
        ["created_at"],
        schema="public",
    )

    # 3. Remove speculative future AI fields from Phase 9 Investigation foundation
    op.drop_constraint(
        "ck_investigations_confidence_score_range",
        "investigations",
        type_="check",
        schema="public",
    )
    op.drop_column("investigations", "confidence_score", schema="public")
    op.drop_column("investigations", "root_cause_summary", schema="public")

    # 4. Ensure table permissions
    op.execute("GRANT ALL ON TABLE public.investigations TO authenticated;")


def downgrade() -> None:
    # 1. Re-add speculative fields removed in upgrade
    op.add_column(
        "investigations",
        sa.Column("root_cause_summary", sa.Text(), nullable=True),
        schema="public",
    )
    op.add_column(
        "investigations",
        sa.Column("confidence_score", sa.Integer(), nullable=True),
        schema="public",
    )
    op.create_check_constraint(
        "ck_investigations_confidence_score_range",
        "investigations",
        "confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 100)",
        schema="public",
    )

    # 2. Drop indexes
    op.drop_index("ix_investigations_created_at", table_name="investigations", schema="public")
    op.drop_index("ix_investigations_started_at", table_name="investigations", schema="public")

    # 3. Drop columns
    op.drop_column("investigations", "started_at", schema="public")
    op.drop_column("investigations", "summary", schema="public")
