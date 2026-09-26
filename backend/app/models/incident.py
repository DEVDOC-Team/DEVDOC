"""Incident model.

An Incident is a detected or reported production problem that DEVDOC
is asked to investigate.  Each Incident belongs to exactly one Project
and may optionally be linked to a specific Repository.

Status lifecycle
----------------
OPEN → INVESTIGATING → RESOLVED | CLOSED
              ↓
           MITIGATED (partial fix applied, monitoring period)

Phase 3 additions
-----------------
* ``reported_by_id``   — FK to the user who reported the incident
                         (nullable: system/automated detection).
* ``resolved_at``      — timestamp when status transitioned to RESOLVED
                         or CLOSED; used for MTTD/MTTR analytics.
* Composite index on ``(project_id, status)`` — primary query pattern for
  listing incidents by project and status.
* Composite index on ``(project_id, severity)`` — for priority dashboards.
* ``CheckConstraint`` on ``affected_users`` — must be non-negative.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class IncidentSeverity(str, enum.Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class IncidentStatus(str, enum.Enum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    MITIGATED = "mitigated"
    RESOLVED = "resolved"
    CLOSED = "closed"


class Incident(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "incidents"

    __table_args__ = (
        CheckConstraint("affected_users >= 0", name="ck_incidents_affected_users_non_negative"),
        Index("ix_incidents_project_id_status", "project_id", "status"),
        Index("ix_incidents_project_id_severity", "project_id", "severity"),
    )

    # Ownership / grouping
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    repository_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("repositories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Who reported the incident (nullable for automated/system detection)
    reported_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Identification
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Classification
    severity: Mapped[IncidentSeverity] = mapped_column(
        SAEnum(IncidentSeverity, name="incidentseverity"),
        nullable=False,
        default=IncidentSeverity.MEDIUM,
    )
    status: Mapped[IncidentStatus] = mapped_column(
        SAEnum(IncidentStatus, name="incidentstatus"),
        nullable=False,
        default=IncidentStatus.OPEN,
        index=True,
    )

    # External reference (e.g. PagerDuty id, Jira ticket)
    external_ref: Mapped[str | None] = mapped_column(String(256), nullable=True)

    # Rough affected user count; updated as investigation progresses
    affected_users: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # MTTD / MTTR analytics — set when status transitions to RESOLVED/CLOSED
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ------------------------------------------------------------------ #
    # Relationships
    # ------------------------------------------------------------------ #
    project: Mapped[Project] = relationship("Project", back_populates="incidents")  # type: ignore[name-defined]
    repository: Mapped[Repository | None] = relationship("Repository", back_populates="incidents")  # type: ignore[name-defined]
    reported_by: Mapped[User | None] = relationship(  # type: ignore[name-defined]
        "User", foreign_keys=[reported_by_id]
    )
    investigations: Mapped[list[Investigation]] = relationship(  # type: ignore[name-defined]
        "Investigation", back_populates="incident", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return (
            f"<Incident id={self.id!s:.8} severity={self.severity} "
            f"status={self.status}>"
        )
