"""Evidence model.

Evidence items are artefacts collected by the DEVDOC agent during an
Investigation: log excerpts, stack traces, metrics snapshots, config
diffs, GitHub commit diffs, CI logs, container logs, etc.

The ``raw_content`` is stored as text; large binary artefacts (e.g.
heap dumps) will be offloaded to object storage in a later phase with
only the URL stored here.

Phase 3 additions
-----------------
* ``source_metadata``  — structured metadata about where the evidence
                         came from (e.g. GitHub repo + SHA, container id,
                         log stream name).  Stored as text-JSON; typed
                         JSON column in a later phase.
                         Must NOT contain secrets or credentials.
* ``collected_at``     — when the evidence was actually collected (may
                         differ from ``created_at`` if backfilled).
* Composite index on ``(investigation_id, kind)`` — for filtering
  evidence by type within an investigation.
* ``CheckConstraint``  — relevance_score must be NULL or 0-100.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class EvidenceKind(str, enum.Enum):
    LOG_EXCERPT = "log_excerpt"
    STACK_TRACE = "stack_trace"
    METRIC_SNAPSHOT = "metric_snapshot"
    CONFIG_DIFF = "config_diff"
    COMMIT_DIFF = "commit_diff"
    CI_LOG = "ci_log"
    CONTAINER_LOG = "container_log"
    DOCUMENTATION = "documentation"
    OTHER = "other"


class Evidence(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "evidence"

    __table_args__ = (
        CheckConstraint(
            "relevance_score IS NULL OR (relevance_score >= 0 AND relevance_score <= 100)",
            name="ck_evidence_relevance_score_range",
        ),
        Index("ix_evidence_investigation_id_kind", "investigation_id", "kind"),
    )

    investigation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    kind: Mapped[EvidenceKind] = mapped_column(
        SAEnum(
            EvidenceKind,
            name="evidencekind",
            values_callable=lambda enum_type: [item.value for item in enum_type],
        ),
        nullable=False,
        index=True,
    )

    # Short label shown in UI
    label: Mapped[str] = mapped_column(String(512), nullable=False)

    # Raw text content — may be empty if artefact is in object storage
    raw_content: Mapped[str | None] = mapped_column(Text, nullable=True)

    # External pointer (S3/GCS URL, GitHub permalink, etc.)
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    # Structured source metadata (text-JSON; MUST NOT contain credentials)
    # Examples:
    #   GitHub:    {"repo": "acme/api", "sha": "abc123", "path": "src/main.py"}
    #   Container: {"container_id": "abc", "service": "api", "log_stream": "stdout"}
    #   CI:        {"workflow": "ci.yml", "run_id": "12345678", "job": "test"}
    source_metadata: Mapped[str | None] = mapped_column(Text, nullable=True)

    # When the evidence was actually collected (may differ from created_at)
    collected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relevance score assigned by the AI agent (0-100); constrained by CHECK
    relevance_score: Mapped[int | None] = mapped_column(nullable=True)

    # ------------------------------------------------------------------ #
    # Relationships
    # ------------------------------------------------------------------ #
    investigation: Mapped[Investigation] = relationship(  # type: ignore[name-defined]
        "Investigation", back_populates="evidence_items"
    )

    def __repr__(self) -> str:
        return f"<Evidence id={self.id!s:.8} kind={self.kind} label={self.label!r:.30}>"
