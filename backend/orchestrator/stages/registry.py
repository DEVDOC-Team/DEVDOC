"""Stage registry.

Manages registration, lookup, duplicate prevention, and listing of investigation
stages with explicit dependency injection.
"""

from __future__ import annotations

from orchestrator.contracts.stage import BaseStage
from orchestrator.core.errors import DuplicateStageError, StageNotFoundError


class StageRegistry:
    """Registry maintaining available investigation stages.

    Instances are explicitly constructed and injected into orchestrators to avoid
    global mutable state.
    """

    def __init__(self, stages: list[BaseStage] | None = None) -> None:
        self._stages: dict[str, BaseStage] = {}
        if stages:
            for s in stages:
                self.register(s)

    def register(self, stage: BaseStage) -> None:
        """Register a stage in the registry.

        Args:
            stage: The stage instance implementing BaseStage.

        Raises:
            DuplicateStageError: If a stage with the same identifier is already registered.
        """
        sid = stage.stage_id
        if not sid or not sid.strip():
            raise ValueError("Stage identifier must be a non-empty string")
        if sid in self._stages:
            raise DuplicateStageError(sid)
        self._stages[sid] = stage

    def get(self, stage_id: str) -> BaseStage:
        """Look up a registered stage by its identifier.

        Args:
            stage_id: Stage identifier string.

        Returns:
            The registered BaseStage instance.

        Raises:
            StageNotFoundError: If stage_id is not registered.
        """
        if stage_id not in self._stages:
            raise StageNotFoundError(stage_id)
        return self._stages[stage_id]

    def list(self) -> list[BaseStage]:
        """Return all registered stages in deterministic order of registration."""
        return list(self._stages.values())

    def contains(self, stage_id: str) -> bool:
        """Check if a stage identifier is currently registered."""
        return stage_id in self._stages

    def unregister(self, stage_id: str) -> None:
        """Remove a stage from the registry.

        Raises:
            StageNotFoundError: If stage_id is not found.
        """
        if stage_id not in self._stages:
            raise StageNotFoundError(stage_id)
        del self._stages[stage_id]

    def __len__(self) -> int:
        return len(self._stages)

    def __contains__(self, stage_id: str) -> bool:
        return stage_id in self._stages
