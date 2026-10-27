"""Add source, detected_at and indexes to incidents table for Incident Management.

Revision ID: 0004_incident_management
Revises: 0003_github_connections
Create Date: 2026-09-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0004_incident_management"
down_revision = "0003_github_connections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create incidentsource enum type in PostgreSQL
    incident_source_enum = postgresql.ENUM(
        "manual",
        "github",
        "monitoring",
        "webhook",
        "system",
        name="incidentsource",
        create_type=False,
    )
    incident_source_enum.create(op.get_bind(), checkfirst=True)

    # 2. Add columns to incidents table
    op.add_column(
        "incidents",
        sa.Column(
            "source",
            sa.Enum(
                "manual",
                "github",
                "monitoring",
                "webhook",
                "system",
                name="incidentsource",
            ),
            nullable=False,
            server_default=sa.text("'manual'"),
        ),
        schema="public",
    )
    op.add_column(
        "incidents",
        sa.Column(
            "detected_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        schema="public",
    )

    # 3. Create indexes
    op.create_index(
        "ix_incidents_project_id_source",
        "incidents",
        ["project_id", "source"],
        schema="public",
    )
    op.create_index(
        "ix_incidents_detected_at",
        "incidents",
        ["detected_at"],
        schema="public",
    )

    # 4. Ensure table permissions
    op.execute("GRANT ALL ON TABLE public.incidents TO authenticated;")


def downgrade() -> None:
    # 1. Drop indexes
    op.drop_index("ix_incidents_detected_at", table_name="incidents", schema="public")
    op.drop_index("ix_incidents_project_id_source", table_name="incidents", schema="public")

    # 2. Drop columns
    op.drop_column("incidents", "detected_at", schema="public")
    op.drop_column("incidents", "source", schema="public")

    # 3. Drop enum type
    incident_source_enum = postgresql.ENUM(
        "manual",
        "github",
        "monitoring",
        "webhook",
        "system",
        name="incidentsource",
    )
    incident_source_enum.drop(op.get_bind(), checkfirst=True)
