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

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class ApprovalDecision(str, enum.Enum):
    APPROVED = "approved"
    REJECTED = "rejected"


class Approval(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "approvals"

    __table_args__ = (
        UniqueConstraint(
            "fix_proposal_id", "approver_id",
            name="uq_approvals_fix_proposal_approver",
        ),
        Index("ix_approvals_fix_proposal_id_decision", "fix_proposal_id", "decision"),
    )

    fix_proposal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("fix_proposals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    approver_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    decision: Mapped[ApprovalDecision] = mapped_column(
        SAEnum(ApprovalDecision, name="approvaldecision"),
        nullable=False,
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
    approver: Mapped[User] = relationship("User", back_populates="approvals")  # type: ignore[name-defined]

    def __repr__(self) -> str:
        return (
            f"<Approval id={self.id!s:.8} decision={self.decision} "
            f"approver={self.approver_id!s:.8}>"
        )
