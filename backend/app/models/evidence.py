"""Evidence model.

Evidence items are artefacts collected by the DEVDOC agent during an
Investigation: log excerpts, stack traces, metrics snapshots, config
diffs, GitHub commit diffs, etc.

The ``raw_content`` is stored as text; large binary artefacts (e.g.
heap dumps) will be offloaded to object storage in a later phase with
only the URL stored here.
"""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, String, Text
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

    investigation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    kind: Mapped[EvidenceKind] = mapped_column(
        SAEnum(EvidenceKind, name="evidencekind"),
        nullable=False,
        index=True,
    )

    # Short label shown in UI
    label: Mapped[str] = mapped_column(String(512), nullable=False)

    # Raw text content — may be empty if artefact is in object storage
    raw_content: Mapped[str | None] = mapped_column(Text, nullable=True)

    # External pointer (S3/GCS URL, GitHub permalink, etc.)
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    # Relevance score assigned by the AI agent (0-100)
    relevance_score: Mapped[int | None] = mapped_column(nullable=True)

    # ------------------------------------------------------------------ #
    # Relationships
    # ------------------------------------------------------------------ #
    investigation: Mapped[Investigation] = relationship(  # type: ignore[name-defined]
        "Investigation", back_populates="evidence_items"
    )

    def __repr__(self) -> str:
        return f"<Evidence id={self.id!s:.8} kind={self.kind} label={self.label!r:.30}>"
