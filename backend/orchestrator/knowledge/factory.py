"""Explicit construction of opt-in Tavily knowledge search."""

from __future__ import annotations

from app.core.config import Settings
from orchestrator.knowledge.config import KnowledgeSearchConfig
from orchestrator.knowledge.providers.tavily import TavilyKnowledgeSearchProvider
from orchestrator.knowledge.service import KnowledgeSearchService


def create_tavily_knowledge_search_service(config: Settings) -> KnowledgeSearchService:
    """Construct the search service only after an explicit enabled/key check."""
    if not config.knowledge_search_enabled:
        raise ValueError("Knowledge search is disabled; set KNOWLEDGE_SEARCH_ENABLED=true")
    if not config.tavily_api_key.get_secret_value():
        raise ValueError("TAVILY_API_KEY is required when knowledge search is enabled")

    search_config = KnowledgeSearchConfig(
        enabled=config.knowledge_search_enabled,
        timeout_seconds=config.knowledge_search_timeout_seconds,
        max_results=config.knowledge_search_max_results,
        max_query_length=config.knowledge_search_max_query_length,
        max_response_bytes=config.knowledge_search_max_response_bytes,
        max_retries=config.knowledge_search_max_retries,
        retry_backoff_seconds=config.knowledge_search_retry_backoff_seconds,
        search_depth=config.knowledge_search_depth,  # validated by Settings
        preferred_domains=config.knowledge_search_preferred_domains,
        allowed_domains=config.knowledge_search_allowed_domains,
        searches_per_investigation=config.knowledge_searches_per_investigation,
        searches_per_request=config.knowledge_searches_per_request,
        max_concurrent_searches=config.knowledge_search_max_concurrent,
        max_title_length=config.knowledge_search_max_title_length,
        max_content_length=config.knowledge_search_max_content_length,
        max_url_length=config.knowledge_search_max_url_length,
        cache_ttl_seconds=config.knowledge_search_cache_ttl_seconds,
        cache_max_entries=config.knowledge_search_cache_max_entries,
        usage_window_seconds=config.knowledge_search_usage_window_seconds,
        usage_max_entries=config.knowledge_search_usage_max_entries,
    )
    return KnowledgeSearchService(
        provider=TavilyKnowledgeSearchProvider(config.tavily_api_key),
        config=search_config,
    )
