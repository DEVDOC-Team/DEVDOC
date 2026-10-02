"""Workflow execution contracts.

Defines failure policies and workflow definitions for structured, deterministic
investigation execution.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field

from orchestrator.core.errors import WorkflowValidationError


class FailurePolicy(str, enum.Enum):
    """Failure handling policy for investigation stage execution."""

    FAIL_FAST = "fail_fast"
    CONTINUE_ON_FAILURE = "continue_on_failure"


@dataclass
class WorkflowDefinition:
    """Declaration of an ordered sequence of stages and execution policies."""

    workflow_id: str
    name: str
    stage_ids: list[str] = field(default_factory=list)
    failure_policy: FailurePolicy = FailurePolicy.FAIL_FAST
    description: str = ""

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        """Validate workflow configuration.

        Raises:
            WorkflowValidationError: If workflow_id or stage_ids is invalid.
        """
        if not self.workflow_id or not self.workflow_id.strip():
            raise WorkflowValidationError(
                "workflow_id must be a non-empty string", workflow_id=self.workflow_id
            )
        if not self.name or not self.name.strip():
            raise WorkflowValidationError(
                "workflow name must be a non-empty string", workflow_id=self.workflow_id
            )
        if not self.stage_ids:
            raise WorkflowValidationError(
                f"Workflow '{self.workflow_id}' must define at least one stage",
                workflow_id=self.workflow_id,
            )
        # Check uniqueness of stages in workflow
        seen: set[str] = set()
        for sid in self.stage_ids:
            if not sid or not sid.strip():
                raise WorkflowValidationError(
                    f"Workflow '{self.workflow_id}' contains an empty stage identifier",
                    workflow_id=self.workflow_id,
                )
            if sid in seen:
                raise WorkflowValidationError(
                    f"Workflow '{self.workflow_id}' contains duplicate stage '{sid}'",
                    workflow_id=self.workflow_id,
                )
            seen.add(sid)
