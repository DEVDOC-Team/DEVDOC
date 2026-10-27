"""Base agents and deterministic test agent implementations."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

from orchestrator.contracts.agent import BaseAgent
from orchestrator.core.context import InvestigationContext
from orchestrator.core.result import AgentResult, ExecutionStatus


class MockInvestigationAgent(BaseAgent):
    """Deterministic mock agent for testing orchestrator pipelines and contracts.

    Guarantees:
    - Zero external network requests.
    - Zero LLM credits or tokens used ($0 cost).
    - Zero production access or shell invocation.
    - Purely deterministic outputs configurable for testing success, failure, or errors.
    """

    def __init__(
        self,
        identifier: str = "mock_investigation_agent",
        name: str = "Mock Investigation Agent",
        capabilities: set[str] | None = None,
        should_fail: bool = False,
        error_message: str | None = None,
        output_metadata: dict[str, Any] | None = None,
        raise_exception: Exception | None = None,
    ) -> None:
        self._identifier = identifier
        self._name = name
        self._capabilities = capabilities or {"mock_analysis", "mock_telemetry"}
        self.should_fail = should_fail
        self.error_message = error_message or "Simulated mock agent failure"
        self.output_metadata = output_metadata or {"mock_status": "success", "finding": "simulated_finding"}
        self.raise_exception = raise_exception
        self.execution_count = 0
        self.last_context: InvestigationContext | None = None

    @property
    def identifier(self) -> str:
        return self._identifier

    @property
    def name(self) -> str:
        return self._name

    @property
    def capabilities(self) -> set[str]:
        return set(self._capabilities)

    async def execute(self, context: InvestigationContext) -> AgentResult:
        self.execution_count += 1
        self.last_context = context
        start_time = time.perf_counter()
        started_at = datetime.now(UTC)

        if self.raise_exception:
            raise self.raise_exception

        duration_ms = (time.perf_counter() - start_time) * 1000.0

        if self.should_fail:
            return AgentResult(
                agent_id=self.identifier,
                status=ExecutionStatus.FAILED,
                error_message=self.error_message,
                output_metadata={},
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_ms=duration_ms,
            )

        context.record_agent_output(self.identifier, self.output_metadata)
        return AgentResult(
            agent_id=self.identifier,
            status=ExecutionStatus.SUCCESS,
            output_metadata=self.output_metadata,
            started_at=started_at,
            completed_at=datetime.now(UTC),
            duration_ms=duration_ms,
        )
