"""Provider-neutral external knowledge search for DEVDOC."""

from __future__ import annotations

from typing import TYPE_CHECKING

from orchestrator.knowledge.config import KnowledgeSearchConfig
from orchestrator.knowledge.models import (
    KnowledgeDocument,
    KnowledgeProvenance,
    KnowledgeSearchMetadata,
    KnowledgeSearchRequest,
    KnowledgeSearchResult,
    SearchIntent,
)
from orchestrator.knowledge.provider import (
    KnowledgeSearchProvider,
    KnowledgeSearchProviderError,
    KnowledgeSearchTransientError,
)
from orchestrator.knowledge.providers.fake import FakeKnowledgeSearchProvider
from orchestrator.knowledge.providers.tavily import TavilyKnowledgeSearchProvider
from orchestrator.knowledge.query_builder import KnowledgeQueryBuilder, KnowledgeQueryError
from orchestrator.knowledge.service import KnowledgeSearchError, KnowledgeSearchService

if TYPE_CHECKING:
    from app.core.config import Settings


def create_tavily_knowledge_search_service(config: Settings) -> KnowledgeSearchService:
    """Explicitly construct the process-scoped search service; performs no request."""
    from orchestrator.knowledge.factory import create_tavily_knowledge_search_service as create

    return create(config)


__all__ = [
    "FakeKnowledgeSearchProvider",
    "KnowledgeDocument",
    "KnowledgeProvenance",
    "KnowledgeQueryBuilder",
    "KnowledgeQueryError",
    "KnowledgeSearchConfig",
    "KnowledgeSearchError",
    "KnowledgeSearchMetadata",
    "KnowledgeSearchProvider",
    "KnowledgeSearchProviderError",
    "KnowledgeSearchRequest",
    "KnowledgeSearchResult",
    "KnowledgeSearchService",
    "KnowledgeSearchTransientError",
    "SearchIntent",
    "TavilyKnowledgeSearchProvider",
    "create_tavily_knowledge_search_service",
]
