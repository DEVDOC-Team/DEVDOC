"""Project model.

A Project is the top-level DEVDOC organisational unit.
Every repository, incident, and investigation belongs to a project.

Ownership model
---------------
``owner_id`` → users.id   (the user who created the project)

In the RLS phase, policies will ensure only project members can
read/write project-scoped resources.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class Project(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "projects"

    __table_args__ = (
        UniqueConstraint("owner_id", "slug", name="uq_projects_owner_slug"),
    )

    # Human-readable name and machine-friendly slug
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Ownership — RLS anchor
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ------------------------------------------------------------------ #
    # Relationships
    # ------------------------------------------------------------------ #
    owner: Mapped[User] = relationship("User", back_populates="projects")  # type: ignore[name-defined]
    repositories: Mapped[list[Repository]] = relationship(  # type: ignore[name-defined]
        "Repository", back_populates="project", cascade="all, delete-orphan"
    )
    incidents: Mapped[list[Incident]] = relationship(  # type: ignore[name-defined]
        "Incident", back_populates="project", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Project id={self.id!s:.8} slug={self.slug!r}>"
