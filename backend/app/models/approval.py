"""Approval model.

An Approval records a human decision (approve or reject) on a
FixProposal.  DEVDOC requires explicit human sign-off before applying
any proposed fix to production.

Audit requirements
------------------
* approver_id  — who made the decision
* decision     — APPROVED | REJECTED
* rationale    — free-text justification (required for rejection)
* timestamp    — inherited from TimestampMixin (created_at is the decision time)

Phase 3 additions
-----------------
* ``UniqueConstraint`` on ``(fix_proposal_id, approver_id)`` — one
  approver may only render one decision per proposal.  If they change
  their mind, the old record must be updated (not duplicated).
* ``review_note``   — optional private note visible only to the reviewer
                      (separate from the ``rationale`` which is surfaced
                      to the proposal author).
* Composite index on ``(fix_proposal_id, decision)`` — for querying
  who approved/rejected a proposal.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class ApprovalDecision(str, enum.Enum):
    APPROVED = "approved"
    REJECTED = "rejected"


class ApprovalStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    SUPERSEDED = "superseded"


class Approval(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "approvals"

    __table_args__ = (
        UniqueConstraint(
            "fix_proposal_id", "approver_id",
            name="uq_approvals_fix_proposal_approver",
        ),
        Index("ix_approvals_fix_proposal_id_decision", "fix_proposal_id", "decision"),
        Index(
            "uq_approvals_one_pending_per_proposal",
            "fix_proposal_id",
            unique=True,
            postgresql_where=sa.text("status = 'pending'"),
            sqlite_where=sa.text("status = 'pending'"),
        ),
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'expired', 'cancelled', 'superseded')",
            name="ck_approvals_status",
        ),
        CheckConstraint(
            "(status = 'pending' AND decision IS NULL AND approver_id IS NULL AND decided_at IS NULL) "
            "OR (status = 'approved' AND decision = 'approved' AND approver_id IS NOT NULL "
            "AND decided_at IS NOT NULL) "
            "OR (status = 'rejected' AND decision = 'rejected' AND approver_id IS NOT NULL "
            "AND decided_at IS NOT NULL) "
            "OR (status IN ('expired', 'cancelled', 'superseded') AND decision IS NULL "
            "AND decided_at IS NOT NULL)",
            name="ck_approvals_state_consistency",
        ),
        CheckConstraint(
            "status <> 'pending' OR "
            "(verification_id IS NOT NULL AND proposal_fingerprint IS NOT NULL "
            "AND verification_fingerprint IS NOT NULL AND expires_at IS NOT NULL)",
            name="ck_approvals_pending_binding",
        ),
        ForeignKeyConstraint(
            ["fix_proposal_id", "verification_id"],
            ["approval_artifacts.fix_proposal_id", "approval_artifacts.id"],
            name="fk_approvals_proposal_verification",
            ondelete="RESTRICT",
        ),
    )

    fix_proposal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("fix_proposals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    approver_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )

    requested_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    verification_id: Mapped[uuid.UUID | None] = mapped_column(
        nullable=True,
        index=True,
    )
    status: Mapped[ApprovalStatus] = mapped_column(
        SAEnum(
            ApprovalStatus,
            name="approvalstatus",
            native_enum=False,
            values_callable=lambda enum_type: [item.value for item in enum_type],
            length=16,
        ),
        nullable=False,
        default=ApprovalStatus.PENDING,
        server_default=ApprovalStatus.PENDING.value,
        index=True,
    )
    proposal_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    verification_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision: Mapped[ApprovalDecision | None] = mapped_column(
        SAEnum(
            ApprovalDecision,
            name="approvaldecision",
            values_callable=lambda enum_type: [item.value for item in enum_type],
        ),
        nullable=True,
        index=True,
    )

    # Required for REJECTED; optional for APPROVED
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Private reviewer note (not shown to proposal author)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Git ref actually applied (populated by the deployment agent after APPROVED)
    applied_commit_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # ------------------------------------------------------------------ #
    # Relationships
    # ------------------------------------------------------------------ #
    fix_proposal: Mapped[FixProposal] = relationship(  # type: ignore[name-defined]
        "FixProposal", back_populates="approvals"
    )
    approver: Mapped[User | None] = relationship(  # type: ignore[name-defined]
        "User", back_populates="approvals", foreign_keys=[approver_id]
    )
    requested_by: Mapped[User] = relationship(  # type: ignore[name-defined]
        "User", foreign_keys=[requested_by_id]
    )
    verification: Mapped[ApprovalArtifact | None] = relationship(  # type: ignore[name-defined]
        "ApprovalArtifact", viewonly=True
    )

    def __repr__(self) -> str:
        return (
            f"<Approval id={self.id!s:.8} status={self.status} "
            f"approver={self.approver_id!s:.8}>"
        )
