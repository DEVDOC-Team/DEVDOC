"""User model.

Represents a DEVDOC platform user.  Authentication identity (OAuth, JWT)
is resolved in a later phase; this model stores the authoritative profile.

RLS note
--------
PostgreSQL Row Level Security will eventually scope all queries by
``auth.uid() = id`` or ``auth.uid() = ANY(team_ids)`` depending on
the resource type.  The ``id`` column intentionally mirrors the
Supabase auth.users UUID so foreign-key relationships work across the
auth and public schemas without duplication.
"""

from __future__ import annotations

from sqlalchemy import Boolean, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class User(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "users"

    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
    )

    # Core identity — sourced from OAuth provider in the auth phase
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    # Platform status
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # The external identity provider subject (e.g. GitHub user id, Google sub)
    # Stored so we can link back during OAuth without exposing raw tokens.
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider_user_id: Mapped[str | None] = mapped_column(String(256), nullable=True)

    # ------------------------------------------------------------------ #
    # Relationships
    # ------------------------------------------------------------------ #
    projects: Mapped[list[Project]] = relationship(  # type: ignore[name-defined]
        "Project", back_populates="owner", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[list[AuditLog]] = relationship(  # type: ignore[name-defined]
        "AuditLog", back_populates="actor", cascade="all, delete-orphan"
    )
    approvals: Mapped[list[Approval]] = relationship(  # type: ignore[name-defined]
        "Approval", back_populates="approver", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id!s:.8} email={self.email!r}>"
