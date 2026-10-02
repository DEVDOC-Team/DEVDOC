"""Execution result types.

Provides strongly typed results for agents, stages, and full orchestrator runs.
Enforces non-leakage of raw secrets or uncontrolled dumps.
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


class ExecutionStatus(str, enum.Enum):
    """Lifecycle status for an agent, stage, or orchestrator execution."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


@dataclass
class AgentResult:
    """Strongly typed output of an individual agent execution."""

    agent_id: str
    status: ExecutionStatus
    output_metadata: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: float = 0.0
    investigation_id: uuid.UUID | None = None
    execution_id: uuid.UUID | None = None
    source: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    collected_at: datetime | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def is_successful(self) -> bool:
        return self.status == ExecutionStatus.SUCCESS

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "status": self.status.value,
            "investigation_id": str(self.investigation_id) if self.investigation_id else None,
            "execution_id": str(self.execution_id) if self.execution_id else None,
            "source": self.source,
            "data": self.data,
            "output_metadata": self.output_metadata,
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "error_message": self.error_message,
            "collected_at": self.collected_at.isoformat() if self.collected_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_ms": self.duration_ms,
        }



@dataclass
class StageResult:
    """Strongly typed output of an individual investigation stage."""

    stage_id: str
    status: ExecutionStatus
    output_metadata: dict[str, Any] = field(default_factory=dict)
    agent_results: list[AgentResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: float = 0.0

    @property
    def is_successful(self) -> bool:
        return self.status == ExecutionStatus.SUCCESS

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage_id": self.stage_id,
            "status": self.status.value,
            "output_metadata": self.output_metadata,
            "agent_results": [a.to_dict() for a in self.agent_results],
            "warnings": list(self.warnings),
            "error_message": self.error_message,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_ms": self.duration_ms,
        }


@dataclass
class OrchestrationResult:
    """Strongly typed output of a full investigation workflow execution."""

    execution_id: uuid.UUID
    investigation_id: uuid.UUID
    incident_id: uuid.UUID
    project_id: uuid.UUID
    workflow_id: str
    status: ExecutionStatus
    stage_results: list[StageResult] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: float = 0.0

    @property
    def is_successful(self) -> bool:
        return self.status == ExecutionStatus.SUCCESS

    def get_stage_result(self, stage_id: str) -> StageResult | None:
        """Retrieve the result of a specific stage by ID."""
        for result in self.stage_results:
            if result.stage_id == stage_id:
                return result
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_id": str(self.execution_id),
            "investigation_id": str(self.investigation_id),
            "incident_id": str(self.incident_id),
            "project_id": str(self.project_id),
            "workflow_id": self.workflow_id,
            "status": self.status.value,
            "stage_results": [s.to_dict() for s in self.stage_results],
            "metadata": self.metadata,
            "warnings": list(self.warnings),
            "error_message": self.error_message,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_ms": self.duration_ms,
        }
