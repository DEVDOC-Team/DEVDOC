"""Phase 14 bounded cache adapter reusing the Phase 13 TTL/LRU implementation."""

from __future__ import annotations

from orchestrator.knowledge.models import KnowledgeSearchResult
from orchestrator.llm.cache import LLMCache


class KnowledgeSearchCache:
    """Typed wrapper preserving project/investigation-scoped cache keys."""

    def __init__(self, *, ttl_seconds: int, max_entries: int) -> None:
        self._cache: LLMCache[KnowledgeSearchResult] = LLMCache(
            ttl_seconds=ttl_seconds,
            max_entries=max_entries,
        )

    def get(self, key: str) -> KnowledgeSearchResult | None:
        return self._cache.get(key)

    def set(self, key: str, value: KnowledgeSearchResult) -> None:
        self._cache.set(key, value)
