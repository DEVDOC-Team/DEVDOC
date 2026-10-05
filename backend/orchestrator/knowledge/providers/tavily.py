"""Official Tavily Search REST API adapter."""

from __future__ import annotations

import json
from typing import Any

import httpx
from pydantic import SecretStr, ValidationError

from orchestrator.knowledge.config import KnowledgeSearchConfig
from orchestrator.knowledge.models import KnowledgeSearchRequest, ProviderSearchResponse
from orchestrator.knowledge.provider import (
    KnowledgeSearchProviderError,
    KnowledgeSearchTransientError,
)

_SEARCH_URL = "https://api.tavily.com/search"


class TavilyKnowledgeSearchProvider:
    """Calls the documented Tavily `/search` endpoint; never fetches result URLs."""

    def __init__(
        self,
        api_key: SecretStr,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        key = api_key.get_secret_value().strip()
        if not key:
            raise ValueError("Tavily API key is required to construct the provider")
        self._api_key = key
        self._transport = transport

    @property
    def provider_name(self) -> str:
        return "tavily"

    async def search(
        self,
        request: KnowledgeSearchRequest,
        config: KnowledgeSearchConfig,
    ) -> ProviderSearchResponse:
        domains = config.allowed_domains or config.preferred_domains
        payload: dict[str, Any] = {
            "api_key": self._api_key,
            "query": request.query,
            "search_depth": config.search_depth,
            "max_results": config.max_results,
            "include_answer": False,
            "include_raw_content": False,
            "include_published_date": True,
        }
        if domains:
            payload["include_domains"] = domains
            payload["include_domains_mode"] = "restrict" if config.allowed_domains else "prefer"

        try:
            async with (
                httpx.AsyncClient(
                    timeout=config.timeout_seconds,
                    transport=self._transport,
                ) as client,
                client.stream("POST", _SEARCH_URL, json=payload) as response,
            ):
                if response.status_code == 429 or response.status_code >= 500:
                    raise KnowledgeSearchTransientError(
                        f"Tavily returned retryable HTTP status {response.status_code}"
                    )
                if response.is_error:
                    raise KnowledgeSearchProviderError(
                        f"Tavily returned HTTP status {response.status_code}"
                    )
                content_length = response.headers.get("content-length")
                if (
                    content_length
                    and content_length.isdigit()
                    and int(content_length) > config.max_response_bytes
                ):
                    raise KnowledgeSearchProviderError(
                        "Tavily response exceeded the configured size limit"
                    )
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(body) + len(chunk) > config.max_response_bytes:
                        raise KnowledgeSearchProviderError(
                            "Tavily response exceeded the configured size limit"
                        )
                    body.extend(chunk)
        except (KnowledgeSearchTransientError, KnowledgeSearchProviderError):
            raise
        except httpx.TimeoutException:
            raise KnowledgeSearchTransientError("Tavily request timed out") from None
        except httpx.NetworkError:
            raise KnowledgeSearchTransientError("Tavily network request failed") from None

        try:
            payload_data = json.loads(body)
            if not isinstance(payload_data, dict):
                raise TypeError
            return ProviderSearchResponse.model_validate(
                {**payload_data, "response_size_bytes": len(body)}
            )
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValidationError):
            raise KnowledgeSearchProviderError(
                "Tavily returned a malformed search response"
            ) from None
