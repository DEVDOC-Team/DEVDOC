"""Provider-abstracted, budget-guarded LLM reasoning for DEVDOC."""

from __future__ import annotations

from typing import TYPE_CHECKING

from orchestrator.llm.budget import BudgetExceededError, LLMBudgetGuard
from orchestrator.llm.contracts import (
    EvidenceSet,
    LLMEvidence,
    LLMObservability,
    ProviderCompletion,
    ReasoningObservation,
    ReasoningResponse,
    StructuredReasoning,
)
from orchestrator.llm.nebius import NebiusNemotronProvider
from orchestrator.llm.provider import LLMProvider, LLMProviderError, LLMTransientError
from orchestrator.llm.service import LLMService, LLMServiceError

if TYPE_CHECKING:
    from app.core.config import Settings


def create_nebius_llm_service(config: Settings) -> LLMService:
    """Explicitly construct the process-scoped Nebius service; performs no request."""
    from orchestrator.llm.factory import create_nebius_llm_service as create_service

    return create_service(config)


__all__ = [
    "BudgetExceededError",
    "EvidenceSet",
    "LLMBudgetGuard",
    "LLMEvidence",
    "LLMObservability",
    "LLMProvider",
    "LLMProviderError",
    "LLMService",
    "LLMServiceError",
    "LLMTransientError",
    "NebiusNemotronProvider",
    "ProviderCompletion",
    "ReasoningObservation",
    "ReasoningResponse",
    "StructuredReasoning",
    "create_nebius_llm_service",
]
