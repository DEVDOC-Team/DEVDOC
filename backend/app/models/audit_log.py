"""AuditLog model.

Every significant action in DEVDOC is recorded as an immutable audit
log entry.  Rows are append-only — never updated or deleted by the
application (database-level constraints will enforce this in the RLS
phase via a restrictive UPDATE/DELETE policy).

Design notes
------------
* ``actor_id``    — nullable to allow system-generated events (cron jobs,
                    automated agents).
* ``entity_type`` / ``entity_id`` — generic reference to the affected
                    resource; deliberate non-FK so audit logs survive
                    entity deletion.
* ``diff``        — JSON patch or plain diff of the change (nullable).
* ``ip_address``  — captured from the HTTP request where available.

Phase 3 additions
-----------------
* ``project_id``   — optional FK to the relevant Project; NULL for
                     system-level events (login, user creation).
                     Non-cascading SET NULL so audit logs survive project
                     deletion.
* ``outcome``      — did the action succeed or fail?  Useful for
                     security monitoring without joining to the entity.
* ``session_id``   — opaque session identifier (not a JWT; just an ID
                     to group related audit events in one user session).
* Composite index on ``(project_id, action)`` — for project audit trail
  views.
* Composite index on ``(actor_id, created_at)`` — for user activity
  timelines.
"""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Index, String, Text, event
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class AuditOutcome(str, enum.Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"


class AuditLog(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "audit_logs"

    __table_args__ = (
        Index("ix_audit_logs_project_id_action", "project_id", "action"),
        Index("ix_audit_logs_actor_id_created_at", "actor_id", "created_at"),
        Index("ix_audit_logs_entity_type_entity_id", "entity_type", "entity_id"),
    )

    # Actor — nullable for system/agent events
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Project context — nullable for system-level events; SET NULL on delete
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"),
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
    # MUST NOT contain secrets, tokens, or credentials.
    diff: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Outcome of the action
    outcome: Mapped[AuditOutcome | None] = mapped_column(
        SAEnum(AuditOutcome, name="auditoutcome"),
        nullable=True,
        index=True,
    )

    # Opaque session ID for grouping related events (not a JWT)
    session_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)

    # Networking context
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # ------------------------------------------------------------------ #
    # Relationships
    # ------------------------------------------------------------------ #
    actor: Mapped[User | None] = relationship("User", back_populates="audit_logs")  # type: ignore[name-defined]
    # project relationship is intentionally read-only (no back_populates)
    # to keep audit logs lightweight and avoid circular cascade concerns.
    project: Mapped[Project | None] = relationship(  # type: ignore[name-defined]
        "Project", foreign_keys=[project_id]
    )

    def __repr__(self) -> str:
        return (
            f"<AuditLog id={self.id!s:.8} action={self.action!r} "
            f"outcome={self.outcome!r}>"
        )


@event.listens_for(AuditLog, "before_update")
def _prevent_audit_update(_mapper: object, _connection: object, _target: AuditLog) -> None:
    raise ValueError("Audit records are immutable")


@event.listens_for(AuditLog, "before_delete")
def _prevent_audit_delete(_mapper: object, _connection: object, _target: AuditLog) -> None:
    raise ValueError("Audit records are immutable")
