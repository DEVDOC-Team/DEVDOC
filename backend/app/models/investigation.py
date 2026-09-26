"""Investigation model.

An Investigation is the DEVDOC AI-agent run that analyses an Incident.
One Incident may have multiple Investigations (e.g. re-investigation
after a fix attempt, or investigating a regression).

Status lifecycle
----------------
PENDING → RUNNING → COMPLETED | FAILED | CANCELLED

Phase 3 additions
-----------------
* ``project_id``        — direct FK to Project for project-scoped queries
                          without joining through Incident.  Denormalised
                          intentionally for query performance.
* ``initiated_by_id``   — FK to the User who triggered the investigation
                          (nullable for future automated triggers).
* ``completed_at``      — timestamp when status → COMPLETED or FAILED.
* ``CheckConstraint``   — confidence_score must be NULL or 0–100.
* Composite index on ``(project_id, status)`` — primary query pattern
  for listing investigations per project by status.
* Composite index on ``(incident_id, status)`` — for incident detail view.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class InvestigationStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Investigation(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "investigations"

    __table_args__ = (
        CheckConstraint(
            "confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 100)",
            name="ck_investigations_confidence_score_range",
        ),
        CheckConstraint("tokens_used >= 0", name="ck_investigations_tokens_non_negative"),
        CheckConstraint(
            "estimated_cost_usd >= 0", name="ck_investigations_cost_non_negative"
        ),
        Index("ix_investigations_project_id_status", "project_id", "status"),
        Index("ix_investigations_incident_id_status", "incident_id", "status"),
    )

    # Direct project FK — denormalised for efficient project-scoped queries
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Parent incident
    incident_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Who triggered this investigation (nullable for future automated triggers)
    initiated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Lifecycle
    status: Mapped[InvestigationStatus] = mapped_column(
        SAEnum(InvestigationStatus, name="investigationstatus"),
        nullable=False,
        default=InvestigationStatus.PENDING,
        index=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # AI output (populated when status = COMPLETED)
    root_cause_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence_score: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )  # 0-100; constrained by CHECK above

    # Token/cost tracking (for budget guard in the AI phase)
    # Preserved from Phase 2 — do NOT remove.
    tokens_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estimated_cost_usd: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )  # stored as micro-USD (×1_000_000)

    # Failure details
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ------------------------------------------------------------------ #
    # Relationships
    # ------------------------------------------------------------------ #
    project: Mapped[Project] = relationship("Project", back_populates="investigations")  # type: ignore[name-defined]
    incident: Mapped[Incident] = relationship("Incident", back_populates="investigations")  # type: ignore[name-defined]
    initiated_by: Mapped[User | None] = relationship(  # type: ignore[name-defined]
        "User", back_populates="investigations", foreign_keys=[initiated_by_id]
    )
    evidence_items: Mapped[list[Evidence]] = relationship(  # type: ignore[name-defined]
        "Evidence", back_populates="investigation", cascade="all, delete-orphan"
    )
    fix_proposals: Mapped[list[FixProposal]] = relationship(  # type: ignore[name-defined]
        "FixProposal", back_populates="investigation", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return (
            f"<Investigation id={self.id!s:.8} status={self.status} "
            f"tokens={self.tokens_used}>"
        )
