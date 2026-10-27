"""Agent and LLM provider contracts.

Defines the contract for investigation agents and the abstract AI provider boundary.
Enforces non-production access, zero shell execution, and predictable contracts.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from orchestrator.core.context import InvestigationContext
from orchestrator.core.result import AgentResult


class BaseAgent(ABC):
    """Abstract base contract for an investigation agent.

    Guarantees:
    - Agents operate strictly within the provided InvestigationContext.
    - Agents never have direct shell access or production mutation permissions.
    - Agents return strongly typed AgentResult records.
    """

    @property
    @abstractmethod
    def identifier(self) -> str:
        """Stable unique identifier for this agent."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable display name for this agent."""
        ...

    @property
    def capabilities(self) -> set[str]:
        """Set of capability strings describing what this agent performs."""
        return set()

    @abstractmethod
    async def execute(self, context: InvestigationContext) -> AgentResult:
        """Execute agent analysis or task against the provided context.

        Args:
            context: Active investigation context.

        Returns:
            AgentResult containing status, output metadata, warnings, and errors.
        """
        ...


class LLMProvider(ABC):
    """Abstract boundary for future LLM integration (Phase 13: NVIDIA Nemotron + Nebius).

    Phase 10 MUST NOT instantiate or call any real LLM provider endpoints.
    This abstraction defines the provider boundary without consuming credits ($0 cost).
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Identifier of the LLM provider."""
        ...

    @abstractmethod
    async def complete(self, prompt: str, **kwargs: Any) -> str:
        """Generate a completion for the given prompt.

        Phase 10: Pure contract, no live API endpoints.
        """
        ...
