"""AuditLog model.

Every significant action in DEVDOC is recorded as an immutable audit
log entry.  Rows are append-only — never updated or deleted by the
application (database-level constraints will enforce this in the RLS
phase via a restrictive UPDATE/DELETE policy).

Design notes
------------
* ``actor_id``   — nullable to allow system-generated events (cron jobs,
                   automated agents).
* ``entity_type`` / ``entity_id`` — generic reference to the affected
                   resource; deliberate non-FK so audit logs survive
                   entity deletion.
* ``diff``        — JSON patch or plain diff of the change (nullable).
* ``ip_address``  — captured from the HTTP request where available.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class AuditLog(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "audit_logs"

    # Actor — nullable for system/agent events
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Action description, e.g. "investigation.started", "fix.approved"
    action: Mapped[str] = mapped_column(String(128), nullable=False, index=True)

    # Generic entity pointer (survives the referenced entity being deleted)
    entity_type: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)

    # Human-readable description surfaced in the UI audit trail
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # JSON diff / before-after snapshot (stored as text; typed JSON in a later phase)
    diff: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Networking context
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # ------------------------------------------------------------------ #
    # Relationships
    # ------------------------------------------------------------------ #
    actor: Mapped[User | None] = relationship("User", back_populates="audit_logs")  # type: ignore[name-defined]

    def __repr__(self) -> str:
        return (
            f"<AuditLog id={self.id!s:.8} action={self.action!r} "
            f"entity_type={self.entity_type!r}>"
        )
