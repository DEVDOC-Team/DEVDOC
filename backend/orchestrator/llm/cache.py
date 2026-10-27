"""Small bounded in-memory TTL cache for deterministic LLM requests."""

from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass


@dataclass
class _CacheEntry[T]:
    value: T
    expires_at: float


class LLMCache[T]:
    """LRU cache bounded by entry count and TTL; no prompts are persisted to disk."""

    def __init__(self, *, ttl_seconds: int, max_entries: int) -> None:
        if ttl_seconds < 0 or max_entries < 0:
            raise ValueError("Cache TTL and maximum entries must be non-negative")
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._entries: OrderedDict[str, _CacheEntry[T]] = OrderedDict()

    def get(self, key: str) -> T | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        if entry.expires_at <= time.monotonic():
            del self._entries[key]
            return None
        self._entries.move_to_end(key)
        return entry.value

    def set(self, key: str, value: T) -> None:
        if self._ttl_seconds == 0 or self._max_entries == 0:
            return
        self._entries[key] = _CacheEntry(value, time.monotonic() + self._ttl_seconds)
        self._entries.move_to_end(key)
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)
