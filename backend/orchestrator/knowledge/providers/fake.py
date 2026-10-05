"""Deterministic fake knowledge provider for tests and local development."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable

from orchestrator.knowledge.config import KnowledgeSearchConfig
from orchestrator.knowledge.models import KnowledgeSearchRequest, ProviderSearchResponse


class FakeKnowledgeSearchProvider:
    """Returns configured responses/errors and never performs network access."""

    def __init__(
        self,
        responses: Iterable[ProviderSearchResponse | Exception] = (),
    ) -> None:
        self._responses = deque(responses)
        self.requests: list[KnowledgeSearchRequest] = []

    @property
    def provider_name(self) -> str:
        return "fake"

    async def search(
        self,
        request: KnowledgeSearchRequest,
        config: KnowledgeSearchConfig,
    ) -> ProviderSearchResponse:
        self.requests.append(request)
        if not self._responses:
            return ProviderSearchResponse(results=[])
        response = self._responses.popleft()
        if isinstance(response, Exception):
            raise response
        return response
