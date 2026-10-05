"""Provider-neutral knowledge search abstraction and safe failure types."""

from __future__ import annotations

from typing import Protocol

from orchestrator.knowledge.config import KnowledgeSearchConfig
from orchestrator.knowledge.models import KnowledgeSearchRequest, ProviderSearchResponse


class KnowledgeSearchProviderError(Exception):
    """Non-retryable provider failure with no credentials or body content."""


class KnowledgeSearchTransientError(KnowledgeSearchProviderError):
    """Timeout, network failure, or retryable provider response."""


class KnowledgeSearchProvider(Protocol):
    """Replaceable async external-search provider interface."""

    @property
    def provider_name(self) -> str:
        """Stable provider identifier suitable for safe result provenance."""

    async def search(
        self,
        request: KnowledgeSearchRequest,
        config: KnowledgeSearchConfig,
    ) -> ProviderSearchResponse:
        """Search the public web and return a bounded provider response."""
