"""LLM provider abstraction and provider-level errors."""

from __future__ import annotations

from typing import Protocol

from orchestrator.llm.contracts import ProviderCompletion


class LLMProviderError(Exception):
    """Safe provider failure; messages must not include credentials or response bodies."""


class LLMTransientError(LLMProviderError):
    """Provider failure that may succeed on a bounded retry."""


class LLMProvider(Protocol):
    """Provider-neutral async completion interface."""

    async def complete(
        self,
        *,
        model: str,
        system_message: str,
        user_message: str,
        max_output_tokens: int,
        timeout_seconds: float,
    ) -> ProviderCompletion:
        """Return one completion without exposing provider-specific response shapes."""
