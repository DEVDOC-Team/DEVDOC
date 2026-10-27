"""Validated limits for provider-neutral external knowledge search."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

SearchDepth = Literal["basic", "advanced", "fast", "ultra-fast"]


@dataclass(frozen=True)
class KnowledgeSearchConfig:
    """Runtime controls for bounded Tavily search and result ingestion."""

    enabled: bool = False
    timeout_seconds: float = 8.0
    max_results: int = 5
    max_query_length: int = 400
    max_response_bytes: int = 250_000
    max_retries: int = 1
    retry_backoff_seconds: float = 0.25
    search_depth: SearchDepth = "basic"
    preferred_domains: list[str] = field(default_factory=list)
    allowed_domains: list[str] = field(default_factory=list)
    searches_per_investigation: int = 2
    searches_per_request: int = 1
    max_concurrent_searches: int = 2
    max_title_length: int = 512
    max_content_length: int = 2_000
    max_url_length: int = 2_048
    cache_ttl_seconds: int = 600
    cache_max_entries: int = 128
    usage_window_seconds: int = 86_400
    usage_max_entries: int = 10_000

    def __post_init__(self) -> None:
        if not 0 < self.timeout_seconds <= 30:
            raise ValueError("timeout_seconds must be greater than zero and at most 30")
        if not 1 <= self.max_results <= 10:
            raise ValueError("max_results must be between 1 and 10")
        if not 64 <= self.max_query_length <= 1_000:
            raise ValueError("max_query_length must be between 64 and 1000")
        if not 1_024 <= self.max_response_bytes <= 2_000_000:
            raise ValueError("max_response_bytes must be between 1024 and 2000000")
        if not 0 <= self.max_retries <= 2:
            raise ValueError("max_retries must be between 0 and 2")
        if not 0 <= self.retry_backoff_seconds <= 2:
            raise ValueError("retry_backoff_seconds must be between 0 and 2")
        if self.search_depth not in {"basic", "advanced", "fast", "ultra-fast"}:
            raise ValueError("search_depth is not supported by Tavily")
        if not 1 <= self.searches_per_investigation <= 10:
            raise ValueError("searches_per_investigation must be between 1 and 10")
        if not 1 <= self.searches_per_request <= 3:
            raise ValueError("searches_per_request must be between 1 and 3")
        if not 1 <= self.max_concurrent_searches <= 10:
            raise ValueError("max_concurrent_searches must be between 1 and 10")
        if not 32 <= self.max_title_length <= 2_048:
            raise ValueError("max_title_length must be between 32 and 2048")
        if not 100 <= self.max_content_length <= 8_000:
            raise ValueError("max_content_length must be between 100 and 8000")
        if not 128 <= self.max_url_length <= 4_096:
            raise ValueError("max_url_length must be between 128 and 4096")
        if not 0 <= self.cache_ttl_seconds <= 86_400:
            raise ValueError("cache_ttl_seconds must be between 0 and 86400")
        if not 0 <= self.cache_max_entries <= 10_000:
            raise ValueError("cache_max_entries must be between 0 and 10000")
        if not 60 <= self.usage_window_seconds <= 604_800:
            raise ValueError("usage_window_seconds must be between 60 and 604800")
        if not 100 <= self.usage_max_entries <= 100_000:
            raise ValueError("usage_max_entries must be between 100 and 100000")
        if len(self.preferred_domains) > 50 or len(self.allowed_domains) > 50:
            raise ValueError("At most 50 search domains may be configured")
        for domain in (*self.preferred_domains, *self.allowed_domains):
            if not _is_domain(domain):
                raise ValueError("Search domains must be bare DNS domain names")


_DOMAIN_PATTERN = re.compile(
    r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
)


def _is_domain(value: str) -> bool:
    return len(value) <= 253 and _DOMAIN_PATTERN.fullmatch(value.lower().rstrip(".")) is not None
