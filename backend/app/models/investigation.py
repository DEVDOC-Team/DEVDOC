"""Investigation model.

An Investigation is the DEVDOC AI-agent run that analyses an Incident.
One Incident may have multiple Investigations (e.g. re-investigation
after a fix attempt, or investigating a regression).

Status lifecycle
----------------
PENDING → RUNNING → COMPLETED | FAILED | CANCELLED
"""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, Text
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

    # Ownership / grouping
    incident_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Lifecycle
    status: Mapped[InvestigationStatus] = mapped_column(
        SAEnum(InvestigationStatus, name="investigationstatus"),
        nullable=False,
        default=InvestigationStatus.PENDING,
        index=True,
    )

    # AI output (populated when status = COMPLETED)
    root_cause_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence_score: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )  # 0-100

    # Token/cost tracking (for budget guard in the AI phase)
    tokens_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estimated_cost_usd: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )  # stored as micro-USD (×1_000_000)

    # Failure details
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ------------------------------------------------------------------ #
    # Relationships
    # ------------------------------------------------------------------ #
    incident: Mapped[Incident] = relationship("Incident", back_populates="investigations")  # type: ignore[name-defined]
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
