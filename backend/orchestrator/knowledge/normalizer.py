"""Validate and bound external search responses before evidence processing."""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from pydantic import ValidationError

from orchestrator.core.sanitizer import is_sensitive_key, sanitize_string
from orchestrator.knowledge.config import KnowledgeSearchConfig
from orchestrator.knowledge.models import (
    KnowledgeDocument,
    KnowledgeProvenance,
    KnowledgeSearchRequest,
    ProviderSearchItem,
    ProviderSearchResponse,
)

_WHITESPACE = re.compile(r"\s+")


class KnowledgeNormalizationError(ValueError):
    """Provider content cannot safely be normalized for DEVDOC."""


def canonicalize_https_url(url: str, *, max_length: int) -> tuple[str, str]:
    """Validate an external HTTPS URL and return canonical URL and hostname."""
    candidate = url.strip()
    if not candidate or len(candidate) > max_length:
        raise KnowledgeNormalizationError("Search result URL is empty or too long")
    try:
        parsed = urlsplit(candidate)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        raise KnowledgeNormalizationError("Search result contained an invalid URL") from None
    if (
        parsed.scheme.lower() != "https"
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
        or parsed.netloc.endswith(":")
    ):
        raise KnowledgeNormalizationError("Search result URL must be a safe HTTPS URL")

    normalized_host = hostname.rstrip(".").lower()
    if not normalized_host or normalized_host == "localhost" or normalized_host.endswith(".local"):
        raise KnowledgeNormalizationError("Search result URL uses a non-public hostname")
    try:
        ip_address = ipaddress.ip_address(normalized_host)
    except ValueError:
        ip_address = None
    if ip_address is not None and (
        ip_address.is_private
        or ip_address.is_loopback
        or ip_address.is_link_local
        or ip_address.is_reserved
        or ip_address.is_multicast
    ):
        raise KnowledgeNormalizationError("Search result URL uses a non-public IP address")

    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
    if any(is_sensitive_key(key) for key, _ in query_pairs):
        raise KnowledgeNormalizationError("Search result URL contains sensitive parameters")
    if sanitize_string(candidate) != candidate:
        raise KnowledgeNormalizationError("Search result URL contains credential-like data")

    canonical = urlunsplit(("https", normalized_host, parsed.path or "/", parsed.query, ""))
    return canonical, normalized_host


class KnowledgeResultNormalizer:
    """Normalizes provider content without fetching any result URL."""

    def __init__(self, config: KnowledgeSearchConfig) -> None:
        self._config = config

    def normalize(
        self,
        response: ProviderSearchResponse,
        request: KnowledgeSearchRequest,
        *,
        provider: str,
        retrieved_at,
        response_size_bytes: int,
    ) -> list[KnowledgeDocument]:
        if response_size_bytes > self._config.max_response_bytes:
            raise KnowledgeNormalizationError("Search response exceeded the configured size limit")

        documents: list[KnowledgeDocument] = []
        seen_urls: set[str] = set()
        for result in response.results[: self._config.max_results]:
            raw_size = sum(
                len(value.encode("utf-8")) for value in (result.title, result.url, result.content)
            )
            if raw_size > self._config.max_response_bytes:
                continue
            try:
                document = self._normalize_item(
                    result,
                    request,
                    provider=provider,
                    retrieved_at=retrieved_at,
                )
            except (KnowledgeNormalizationError, ValidationError):
                continue
            canonical_url, _ = canonicalize_https_url(
                document.url,
                max_length=self._config.max_url_length,
            )
            if canonical_url in seen_urls:
                continue
            seen_urls.add(canonical_url)
            documents.append(document)
        return documents

    def _normalize_item(
        self,
        item: ProviderSearchItem,
        request: KnowledgeSearchRequest,
        *,
        provider: str,
        retrieved_at,
    ) -> KnowledgeDocument:
        _, hostname = canonicalize_https_url(
            item.url,
            max_length=self._config.max_url_length,
        )
        allowed = self._config.allowed_domains
        if allowed and not any(
            hostname == domain or hostname.endswith(f".{domain}") for domain in allowed
        ):
            raise KnowledgeNormalizationError("Search result host is outside allowed domains")

        title = self._clean_text(item.title, self._config.max_title_length)
        snippet = self._clean_text(item.content, self._config.max_content_length)
        if not title or not snippet:
            raise KnowledgeNormalizationError("Search result must include a title and snippet")
        published_at = item.published_date
        if published_at is not None:
            published_at = self._clean_text(published_at, 128) or None
        score = item.score if item.score is not None and 0 <= item.score <= 1 else None
        return KnowledgeDocument(
            title=title,
            url=item.url.strip(),
            snippet=snippet,
            source_domain=hostname,
            published_at=published_at,
            relevance_score=score,
            provenance=KnowledgeProvenance(
                original_url=item.url.strip(),
                source_domain=hostname,
                provider=provider,
                search_query=request.query,
                retrieved_at=retrieved_at,
            ),
        )

    @staticmethod
    def _clean_text(value: str, limit: int) -> str:
        cleaned = sanitize_string(_WHITESPACE.sub(" ", value)).strip()
        if len(cleaned) > limit:
            cleaned = cleaned[:limit].rsplit(" ", 1)[0].strip()
        return cleaned
