"""Build concise technical search queries from allow-listed investigation fields."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from orchestrator.core.context import InvestigationContext
from orchestrator.core.sanitizer import sanitize_string
from orchestrator.evidence.models import EvidenceCollection
from orchestrator.knowledge.config import KnowledgeSearchConfig
from orchestrator.knowledge.models import KnowledgeSearchRequest, SearchIntent

_INTENT_TERMS = {
    SearchIntent.DOCUMENTATION: "official documentation",
    SearchIntent.ERROR_REFERENCE: "error reference",
    SearchIntent.KNOWN_ISSUE: "known issue",
    SearchIntent.CONFIGURATION: "configuration documentation",
    SearchIntent.COMPATIBILITY: "compatibility release notes",
    SearchIntent.TROUBLESHOOTING: "troubleshooting",
    SearchIntent.GENERAL_TECHNICAL: "technical documentation",
}
_METADATA_FIELDS = (
    "incident_summary",
    "summary",
    "error",
    "error_message",
    "service_name",
    "service",
    "software_name",
    "software",
    "software_version",
    "version",
    "deployment",
    "observed_symptoms",
    "symptoms",
)
_EVIDENCE_FIELDS = ("service", "service_name", "software", "software_name", "version", "image")
_TOKEN_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])(?:eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})(?![A-Za-z0-9])"
)
_EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_URL_PATTERN = re.compile(r"\b(?:https?://|www\.)\S+", re.IGNORECASE)
_WHITESPACE_PATTERN = re.compile(r"\s+")
_WORD_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/+:-]{0,63}")


class KnowledgeQueryError(ValueError):
    """Raised when no safe, useful bounded query can be constructed."""


def sanitize_query_component(value: str) -> str:
    """Reuse DEVDOC redaction and drop personal, URL, and JWT material."""
    sanitized = sanitize_string(value)
    sanitized = _TOKEN_PATTERN.sub(" ", sanitized)
    sanitized = _EMAIL_PATTERN.sub(" ", sanitized)
    sanitized = _URL_PATTERN.sub(" ", sanitized)
    return _WHITESPACE_PATTERN.sub(" ", sanitized).strip()


class KnowledgeQueryBuilder:
    """Extracts a limited set of technical terms; never forwards raw context dumps."""

    def __init__(self, config: KnowledgeSearchConfig) -> None:
        self._config = config

    def build(
        self,
        context: InvestigationContext,
        evidence: EvidenceCollection,
        *,
        intent: SearchIntent = SearchIntent.TROUBLESHOOTING,
    ) -> KnowledgeSearchRequest:
        candidates: list[str] = [_INTENT_TERMS[intent]]
        for field in _METADATA_FIELDS:
            value = context.execution_metadata.get(field)
            candidates.extend(self._technical_terms(value))
        for item in evidence.items[:20]:
            candidates.extend(self._technical_terms(item.title))
            for key, value in item.data.items():
                if key in _EVIDENCE_FIELDS:
                    candidates.extend(self._technical_terms(value))

        words: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            for word in _WORD_PATTERN.findall(sanitize_query_component(candidate)):
                if (
                    len(word) >= 24
                    and any(char.isalpha() for char in word)
                    and any(char.isdigit() for char in word)
                ):
                    continue
                normalized = word.casefold()
                if normalized not in seen:
                    words.append(word)
                    seen.add(normalized)
        query = " ".join(words)[: self._config.max_query_length].strip()
        if not query or not any(word for word in words if word.casefold() not in {"official"}):
            raise KnowledgeQueryError("Investigation has no safe technical terms to search")
        return KnowledgeSearchRequest(
            project_id=context.project_id,
            investigation_id=context.investigation_id,
            execution_id=context.execution_id,
            intent=intent,
            query=query,
        )

    @staticmethod
    def _technical_terms(value: Any) -> Iterable[str]:
        if isinstance(value, str):
            candidate = sanitize_query_component(value)
            if candidate:
                yield candidate
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            yield str(value)
        elif isinstance(value, dict):
            for key in _EVIDENCE_FIELDS:
                if key in value:
                    yield from KnowledgeQueryBuilder._technical_terms(value[key])
