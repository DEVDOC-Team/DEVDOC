"""Deployment model.

A Deployment represents a version of a Repository that was released to
an environment (production, staging, etc.).  DEVDOC correlates
Incidents with Deployments to identify "change that caused the problem".
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
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

    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # The git ref that was deployed
    commit_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    ref: Mapped[str] = mapped_column(String(255), nullable=False)  # branch or tag
    environment: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    status: Mapped[DeploymentStatus] = mapped_column(
        SAEnum(DeploymentStatus, name="deploymentstatus"),
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
    repository: Mapped[Repository] = relationship(  # type: ignore[name-defined]
        "Repository", back_populates="deployments"
    )

    def __repr__(self) -> str:
        return (
            f"<Deployment id={self.id!s:.8} env={self.environment!r} "
            f"ref={self.ref!r} status={self.status}>"
        )
