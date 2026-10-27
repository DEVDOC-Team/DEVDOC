"""Stage contract abstraction.

Defines the interface and lifecycle stages for investigation steps.
"""

from __future__ import annotations

import enum
from abc import ABC, abstractmethod

from orchestrator.core.context import InvestigationContext
from orchestrator.core.result import StageResult


class StageIdentifier(str, enum.Enum):
    """Canonical stage identifiers representing the DEVDOC investigation lifecycle."""

    INITIALIZE = "initialize"
    COLLECT = "collect"
    ANALYZE = "analyze"
    DIAGNOSE = "diagnose"
    PROPOSE = "propose"
    VERIFY = "verify"
    HUMAN_APPROVAL = "human_approval"
    COMPLETE = "complete"


class BaseStage(ABC):
    """Abstract base contract for an investigation stage.

    Every stage must provide:
    - stable unique identifier
    - human readable name
    - deterministic async execution contract
    - standard StageResult output
    """

    @property
    @abstractmethod
    def stage_id(self) -> str:
        """Stable unique identifier for this stage."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable display name for this stage."""
        ...

    @property
    def description(self) -> str:
        """Optional descriptive summary of this stage's purpose."""
        return ""

    @abstractmethod
    async def execute(self, context: InvestigationContext) -> StageResult:
        """Execute the stage with the provided context.

        Args:
            context: The active investigation context.

        Returns:
            StageResult indicating status, metadata, warnings, and error information.
        """
        ...
