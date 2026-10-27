"""User GitHub Connection model.

Stores secure GitHub OAuth credentials and metadata connected to a DEVDOC User.
Row Level Security (RLS) ensures each user can only read, write, and delete
their own connection (user_id = auth.uid()).
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.user import User


class UserGitHubConnection(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "user_github_connections"

    __table_args__ = (
        UniqueConstraint("user_id", name="uq_user_github_connections_user_id"),
        Index("ix_user_github_connections_github_user_id", "github_user_id"),
    )

    # Scoped to authenticated user
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # GitHub account coordinates
    github_user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    github_username: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    avatar_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    # Credentials — NEVER exposed in API responses or logs
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    token_type: Mapped[str] = mapped_column(String(64), nullable=False, default="bearer")
    scope: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # Relationships
    user: Mapped[User] = relationship("User", back_populates="github_connection")

    def __repr__(self) -> str:
        return f"<UserGitHubConnection user_id={self.user_id!s:.8} github_username={self.github_username!r}>"
