"""Orchestrator error definitions.

Defines the structured exception hierarchy for orchestration operations,
enforcing separation between validation failures, stage execution failures,
cancellation events, and programming bugs.
"""

from __future__ import annotations


class OrchestrationError(Exception):
    """Base exception for all DEVDOC orchestration errors."""

    def __init__(self, message: str, *args: object) -> None:
        super().__init__(message, *args)
        self.message = message


class ContextValidationError(OrchestrationError):
    """Raised when an InvestigationContext fails validation rules."""

    def __init__(self, message: str, invalid_field: str | None = None) -> None:
        super().__init__(message)
        self.invalid_field = invalid_field


class DuplicateStageError(OrchestrationError):
    """Raised when attempting to register a stage with an identifier that already exists."""

    def __init__(self, stage_id: str) -> None:
        super().__init__(f"Stage with identifier '{stage_id}' is already registered")
        self.stage_id = stage_id


class StageNotFoundError(OrchestrationError):
    """Raised when a requested stage identifier is not found in the registry."""

    def __init__(self, stage_id: str) -> None:
        super().__init__(f"Stage with identifier '{stage_id}' was not found in the registry")
        self.stage_id = stage_id


class StageExecutionError(OrchestrationError):
    """Raised when an unhandled exception or critical error occurs during stage execution."""

    def __init__(
        self, stage_id: str, message: str, cause: Exception | None = None
    ) -> None:
        super().__init__(f"Stage '{stage_id}' failed: {message}")
        self.stage_id = stage_id
        self.cause = cause


class AgentExecutionError(OrchestrationError):
    """Raised when an unhandled exception occurs during an agent's execution."""

    def __init__(
        self, agent_id: str, message: str, cause: Exception | None = None
    ) -> None:
        super().__init__(f"Agent '{agent_id}' failed: {message}")
        self.agent_id = agent_id
        self.cause = cause


class WorkflowValidationError(OrchestrationError):
    """Raised when a workflow configuration is invalid or cannot be executed."""

    def __init__(self, message: str, workflow_id: str | None = None) -> None:
        super().__init__(message)
        self.workflow_id = workflow_id


class InvestigationCancelledError(OrchestrationError):
    """Raised when an investigation is cancelled before or during stage execution."""

    def __init__(self, message: str = "Investigation execution was cancelled") -> None:
        super().__init__(message)
