"""Repository model.

A Repository represents a GitHub (or future VCS) repository connected
to a DEVDOC Project.  Source code, CI/CD configuration, and deployment
artefacts are resolved against this entity.

Phase 3 additions
-----------------
* ``is_active``       — flag to soft-disable a repository without
                        removing history.
* ``language``        — primary programming language (GitHub API field);
                        useful for routing AI agents.
* ``description``     — repository description from provider.
* ``last_synced_at``  — when DEVDOC last fetched repository metadata
                        from the VCS provider.
* Composite index on ``(project_id, is_active)`` for listing active
  repositories per project.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class VCSProvider(str, enum.Enum):
    GITHUB = "github"
    GITLAB = "gitlab"
    BITBUCKET = "bitbucket"


class Repository(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "repositories"

    __table_args__ = (
        UniqueConstraint(
            "project_id", "provider", "full_name",
            name="uq_repositories_project_provider_name",
        ),
        Index("ix_repositories_project_id_is_active", "project_id", "is_active"),
    )

    # Ownership / grouping
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # VCS coordinates
    provider: Mapped[VCSProvider] = mapped_column(
        SAEnum(VCSProvider, name="vcsprovider"), nullable=False
    )
    # e.g. "acme-corp/backend-api"
    full_name: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    # Provider-assigned numeric id for webhook validation
    provider_repo_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # URL shown in UI
    clone_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    default_branch: Mapped[str] = mapped_column(
        String(255), nullable=False, default="main"
    )

    # Repository metadata from provider (non-sensitive)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Lifecycle
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ------------------------------------------------------------------ #
    # Relationships
    # ------------------------------------------------------------------ #
    project: Mapped[Project] = relationship("Project", back_populates="repositories")  # type: ignore[name-defined]
    incidents: Mapped[list[Incident]] = relationship(  # type: ignore[name-defined]
        "Incident", back_populates="repository"
    )
    deployments: Mapped[list[Deployment]] = relationship(  # type: ignore[name-defined]
        "Deployment", back_populates="repository", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Repository id={self.id!s:.8} full_name={self.full_name!r}>"
