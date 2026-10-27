"""Bounded knowledge search, caching, usage control, and evidence integration."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from collections import OrderedDict
from datetime import UTC, datetime

from pydantic import ValidationError

from orchestrator.core.context import InvestigationContext
from orchestrator.core.result import AgentResult, ExecutionStatus
from orchestrator.evidence.engine import EvidenceEngine
from orchestrator.evidence.models import EvidenceCollection
from orchestrator.knowledge.cache import KnowledgeSearchCache
from orchestrator.knowledge.config import KnowledgeSearchConfig
from orchestrator.knowledge.models import (
    KnowledgeSearchMetadata,
    KnowledgeSearchRequest,
    KnowledgeSearchResult,
)
from orchestrator.knowledge.normalizer import (
    KnowledgeNormalizationError,
    KnowledgeResultNormalizer,
)
from orchestrator.knowledge.provider import (
    KnowledgeSearchProvider,
    KnowledgeSearchProviderError,
    KnowledgeSearchTransientError,
)
from orchestrator.knowledge.query_builder import (
    KnowledgeQueryBuilder,
    sanitize_query_component,
)

logger = logging.getLogger("devdoc.orchestrator.knowledge")


class KnowledgeSearchError(Exception):
    """Safe service error suitable for orchestrator stage reporting."""


class KnowledgeSearchService:
    """Executes controlled external searches and appends results via EvidenceEngine."""

    def __init__(
        self,
        *,
        provider: KnowledgeSearchProvider,
        config: KnowledgeSearchConfig,
        evidence_engine: EvidenceEngine | None = None,
    ) -> None:
        self._provider = provider
        self._config = config
        self._normalizer = KnowledgeResultNormalizer(config)
        self._evidence_engine = evidence_engine or EvidenceEngine()
        self._cache = KnowledgeSearchCache(
            ttl_seconds=config.cache_ttl_seconds,
            max_entries=config.cache_max_entries,
        )
        self._concurrency_limit = asyncio.Semaphore(config.max_concurrent_searches)
        self._usage_lock = asyncio.Lock()
        self._usage: OrderedDict[tuple[str, str], tuple[int, float]] = OrderedDict()

    @property
    def config(self) -> KnowledgeSearchConfig:
        return self._config

    async def search_investigation(
        self,
        context: InvestigationContext,
        evidence_collection: EvidenceCollection,
    ) -> tuple[KnowledgeSearchResult, EvidenceCollection]:
        """Build one bounded query from the current execution and append its results."""
        request = KnowledgeQueryBuilder(self._config).build(context, evidence_collection)
        return await self.search_and_enrich(request, context, evidence_collection)

    async def search(self, request: KnowledgeSearchRequest) -> KnowledgeSearchResult:
        """Perform one provider-neutral search under the configured controls."""
        if not self._config.enabled:
            raise KnowledgeSearchError("Knowledge search is disabled")
        safe_query = sanitize_query_component(request.query)
        if not safe_query or len(safe_query) > self._config.max_query_length:
            raise KnowledgeSearchError("Search query is empty or exceeds the configured limit")
        try:
            safe_request = KnowledgeSearchRequest(
                project_id=request.project_id,
                investigation_id=request.investigation_id,
                execution_id=request.execution_id,
                intent=request.intent,
                query=safe_query,
            )
        except ValidationError as exc:
            raise KnowledgeSearchError("Search request does not satisfy its contract") from exc

        cache_key = self._cache_key(safe_request)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached.model_copy(
                update={
                    "metadata": cached.metadata.model_copy(update={"cache_hit": True}),
                }
            )

        start_time = time.perf_counter()
        attempt_count = 0
        async with self._concurrency_limit:
            for attempt in range(1, self._config.max_retries + 2):
                attempt_count = attempt
                await self._reserve_usage(safe_request)
                try:
                    provider_response = await self._provider.search(
                        safe_request,
                        self._config,
                    )
                except KnowledgeSearchTransientError as exc:
                    if attempt > self._config.max_retries:
                        logger.warning(
                            "Knowledge search failed after bounded retries",
                            extra={
                                "provider": self._provider.provider_name,
                                "investigation_id": str(safe_request.investigation_id),
                                "query_hash": hashlib.sha256(safe_query.encode()).hexdigest(),
                                "attempts": attempt,
                                "status": "unavailable",
                            },
                        )
                        raise KnowledgeSearchError(
                            "Knowledge provider unavailable after retry limit"
                        ) from exc
                    await asyncio.sleep(self._config.retry_backoff_seconds * (2 ** (attempt - 1)))
                    continue
                except KnowledgeSearchProviderError as exc:
                    raise KnowledgeSearchError("Knowledge provider rejected the request") from exc
                break
            else:
                raise KnowledgeSearchError("Knowledge provider did not complete the request")

        searched_at = datetime.now(UTC)
        measured_response_size = sum(
            len(value.encode("utf-8"))
            for item in provider_response.results
            for value in (item.title, item.url, item.content)
        )
        response_size = max(
            provider_response.response_size_bytes,
            measured_response_size,
        )
        try:
            documents = self._normalizer.normalize(
                provider_response,
                safe_request,
                provider=self._provider.provider_name,
                retrieved_at=searched_at,
                response_size_bytes=response_size,
            )
        except KnowledgeNormalizationError as exc:
            raise KnowledgeSearchError(
                "Knowledge provider response exceeded validation limits"
            ) from exc
        except (ValidationError, TypeError, ValueError) as exc:
            raise KnowledgeSearchError(
                "Knowledge provider response could not be normalized"
            ) from exc

        result = KnowledgeSearchResult(
            query=safe_request.query,
            provider=self._provider.provider_name,
            results=documents,
            searched_at=searched_at,
            total_results=len(documents),
            metadata=KnowledgeSearchMetadata(
                duration_ms=(time.perf_counter() - start_time) * 1000,
                attempts=attempt_count,
                cache_hit=False,
                provider_response_time_seconds=provider_response.response_time,
            ),
        )
        self._cache.set(cache_key, result)
        logger.info(
            "Knowledge search completed",
            extra={
                "provider": self._provider.provider_name,
                "investigation_id": str(safe_request.investigation_id),
                "intent": safe_request.intent.value,
                "query_hash": hashlib.sha256(safe_query.encode()).hexdigest(),
                "result_count": result.total_results,
                "duration_ms": round(result.metadata.duration_ms, 2),
                "attempts": attempt_count,
                "cache_hit": False,
                "status": "success",
            },
        )
        return result

    async def search_many(
        self,
        requests: list[KnowledgeSearchRequest],
    ) -> list[KnowledgeSearchResult]:
        """Run an explicitly bounded batch; all requests must share one investigation."""
        if len(requests) > self._config.searches_per_request:
            raise KnowledgeSearchError("Search request exceeds the configured query count")
        if requests:
            first = requests[0]
            if any(
                (item.project_id, item.investigation_id, item.execution_id)
                != (first.project_id, first.investigation_id, first.execution_id)
                for item in requests
            ):
                raise KnowledgeSearchError("Search batch cannot cross investigation boundaries")
        return [await self.search(request) for request in requests]

    async def search_and_enrich(
        self,
        request: KnowledgeSearchRequest,
        context: InvestigationContext,
        evidence_collection: EvidenceCollection,
    ) -> tuple[KnowledgeSearchResult, EvidenceCollection]:
        """Search, normalize through Phase 12, then merge into the active evidence set."""
        if (
            request.project_id != context.project_id
            or request.investigation_id != context.investigation_id
            or request.execution_id != context.execution_id
            or evidence_collection.investigation_id != context.investigation_id
            or evidence_collection.execution_id != context.execution_id
        ):
            raise KnowledgeSearchError("Search request does not belong to the active investigation")
        result = await self.search(request)
        if not result.results:
            return result, evidence_collection

        agent_results = [
            AgentResult(
                agent_id="knowledge_search_agent",
                status=ExecutionStatus.SUCCESS,
                investigation_id=context.investigation_id,
                execution_id=context.execution_id,
                source="external_knowledge",
                collected_at=result.searched_at,
                data={
                    "title": document.title,
                    "url": document.url,
                    "snippet": document.snippet,
                    "query": document.provenance.search_query,
                    "provider": document.provenance.provider,
                    "source_domain": document.source_domain,
                    "published_at": document.published_at,
                    "relevance_score": document.relevance_score,
                },
            )
            for document in result.results
        ]
        additions = self._evidence_engine.process(agent_results, context)
        combined = self._evidence_engine.merge(evidence_collection, additions)
        context.evidence_collection = combined
        return result, combined

    async def _reserve_usage(self, request: KnowledgeSearchRequest) -> None:
        now = time.monotonic()
        key = (str(request.project_id), str(request.investigation_id))
        async with self._usage_lock:
            expired = [entry for entry, (_, expires_at) in self._usage.items() if expires_at <= now]
            for entry in expired:
                del self._usage[entry]
            count, expires_at = self._usage.get(
                key,
                (0, now + self._config.usage_window_seconds),
            )
            if count >= self._config.searches_per_investigation:
                raise KnowledgeSearchError(
                    "Investigation exceeded its configured knowledge search limit"
                )
            self._usage[key] = (count + 1, expires_at)
            self._usage.move_to_end(key)
            while len(self._usage) > self._config.usage_max_entries:
                self._usage.popitem(last=False)

    def _cache_key(self, request: KnowledgeSearchRequest) -> str:
        config_data = {
            "provider": self._provider.provider_name,
            "project_id": str(request.project_id),
            "investigation_id": str(request.investigation_id),
            "execution_id": str(request.execution_id),
            "intent": request.intent.value,
            "query": request.query,
            "depth": self._config.search_depth,
            "max_results": self._config.max_results,
            "preferred_domains": sorted(self._config.preferred_domains),
            "allowed_domains": sorted(self._config.allowed_domains),
        }
        serialized = json.dumps(config_data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
