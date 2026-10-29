"""Deployment model.

A Deployment represents a version of a Repository that was released to
an environment (production, staging, etc.).  DEVDOC correlates
Incidents with Deployments to identify "change that caused the problem".

Phase 3 additions
-----------------
* ``project_id``   — direct FK to Project (denormalised; avoids join
                     through Repository for project-scoped queries).
* ``triggered_by_id`` — FK to User who triggered the deployment
                     (nullable for automated/CI deployments).
* Composite index on ``(project_id, environment, status)`` — primary
  query pattern for listing deployments per environment.
* Composite index on ``(repository_id, environment)`` — for repository
  deployment history.
* ``CheckConstraint`` on ``commit_sha`` length — must be 7 or 40 chars
  (short or full SHA).
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class DeploymentStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    CANCELLED = "cancelled"


class Deployment(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "deployments"

    __table_args__ = (
        CheckConstraint(
            "length(commit_sha) = 40 OR length(commit_sha) = 7",
            name="ck_deployments_commit_sha_length",
        ),
        Index("ix_deployments_project_id_env_status", "project_id", "environment", "status"),
        Index("ix_deployments_repository_id_environment", "repository_id", "environment"),
    )

    # Direct project FK for efficient project-scoped queries
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Who triggered the deployment (nullable for CI/automated deployments)
    triggered_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # The git ref that was deployed
    commit_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    ref: Mapped[str] = mapped_column(String(255), nullable=False)  # branch or tag
    environment: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    status: Mapped[DeploymentStatus] = mapped_column(
        SAEnum(
            DeploymentStatus,
            name="deploymentstatus",
            values_callable=lambda enum_type: [item.value for item in enum_type],
        ),
        nullable=False,
        default=DeploymentStatus.PENDING,
        index=True,
    )

    # CI/CD pipeline reference (GitHub Actions run id, Jenkins build number…)
    pipeline_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    pipeline_id: Mapped[str | None] = mapped_column(String(256), nullable=True)

    # Deployment window
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Raw CI log or error message (truncated — full log in object storage later)
    log_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ------------------------------------------------------------------ #
    # Relationships
    # ------------------------------------------------------------------ #
    project: Mapped[Project] = relationship("Project", foreign_keys=[project_id])  # type: ignore[name-defined]
    repository: Mapped[Repository] = relationship(  # type: ignore[name-defined]
        "Repository", back_populates="deployments"
    )
    triggered_by: Mapped[User | None] = relationship(  # type: ignore[name-defined]
        "User", foreign_keys=[triggered_by_id]
    )

    def __repr__(self) -> str:
        return (
            f"<Deployment id={self.id!s:.8} env={self.environment!r} "
            f"ref={self.ref!r} status={self.status}>"
        )
