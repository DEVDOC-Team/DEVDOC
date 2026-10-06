"""Immutable, server-recorded bundle that Phase 18 allows a human to review."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDMixin, _utcnow


class ApprovalArtifact(UUIDMixin, Base):
    """Phase 15–17 outputs, captured by the trusted orchestration boundary."""

    __tablename__ = "approval_artifacts"

    __table_args__ = (
        UniqueConstraint(
            "fix_proposal_id",
            "id",
            name="uq_approval_artifacts_proposal_id",
        ),
        CheckConstraint(
            "length(proposal_fingerprint) = 64 AND "
            "length(proposal_record_fingerprint) = 64 AND "
            "length(verification_fingerprint) = 64",
            name="ck_approval_artifacts_fingerprint_length",
        ),
        CheckConstraint(
            "verification_status IN "
            "('passed', 'failed', 'inconclusive', 'timeout', 'cancelled', 'unsafe', 'setup_failed')",
            name="ck_approval_artifacts_verification_status",
        ),
        Index("ix_approval_artifacts_project_created", "project_id", "created_at"),
        Index("ix_approval_artifacts_investigation_created", "investigation_id", "created_at"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("investigations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    fix_proposal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("fix_proposals.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    verification_status: Mapped[str] = mapped_column(String(24), nullable=False)
    root_cause_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    proposal_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    proposal_record_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    verification_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    root_cause_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    proposal_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    verification_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
    )

@event.listens_for(ApprovalArtifact, "before_update")
def _prevent_artifact_update(_mapper: object, _connection: object, _target: ApprovalArtifact) -> None:
    raise ValueError("Approval review artifacts are immutable")


@event.listens_for(ApprovalArtifact, "before_delete")
def _prevent_artifact_delete(_mapper: object, _connection: object, _target: ApprovalArtifact) -> None:
    raise ValueError("Approval review artifacts are immutable")
