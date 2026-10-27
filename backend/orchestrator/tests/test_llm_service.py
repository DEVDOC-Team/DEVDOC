"""Deterministic Phase 13 LLM tests; no test makes a live model request."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import Settings
from orchestrator.contracts.agent import BaseAgent
from orchestrator.core.context import InvestigationContext
from orchestrator.core.result import AgentResult, ExecutionStatus
from orchestrator.evidence.engine import EvidenceEngine
from orchestrator.llm import create_nebius_llm_service
from orchestrator.llm.budget import BudgetExceededError, LLMBudgetGuard
from orchestrator.llm.contracts import ProviderCompletion
from orchestrator.llm.nebius import NebiusNemotronProvider
from orchestrator.llm.provider import LLMTransientError
from orchestrator.llm.service import LLMService, LLMServiceError
from orchestrator.stages.investigation import AnalyzeStage, CollectEvidenceStage


class FakeLLMProvider:
    def __init__(self, contents: list[str]) -> None:
        self.contents = contents
        self.calls = 0

    async def complete(
        self,
        *,
        model: str,
        system_message: str,
        user_message: str,
        max_output_tokens: int,
        timeout_seconds: float,
    ) -> ProviderCompletion:
        self.calls += 1
        return ProviderCompletion(
            content=self.contents.pop(0),
            prompt_tokens=100,
            completion_tokens=30,
            request_id=f"request-{self.calls}",
            model=model,
        )


class EvidenceAgent(BaseAgent):
    @property
    def identifier(self) -> str:
        return "test_evidence_agent"

    @property
    def name(self) -> str:
        return "Test Evidence Agent"

    async def execute(self, context: InvestigationContext) -> AgentResult:
        return AgentResult(
            agent_id=self.identifier,
            source="custom",
            status=ExecutionStatus.SUCCESS,
            investigation_id=context.investigation_id,
            execution_id=context.execution_id,
            collected_at=datetime(2026, 10, 5, tzinfo=UTC),
            data={"service": "api", "finding": "latency increased"},
        )


def make_context() -> InvestigationContext:
    return InvestigationContext(
        investigation_id=uuid.uuid4(),
        incident_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
    )


def make_evidence():
    context = make_context()
    result = AgentResult(
        agent_id="fake-agent",
        source="custom",
        status=ExecutionStatus.SUCCESS,
        investigation_id=context.investigation_id,
        execution_id=context.execution_id,
        collected_at=datetime(2026, 10, 5, tzinfo=UTC),
        data={"service": "api", "finding": "latency increased"},
    )
    return context, EvidenceEngine().process([result], context)


def reasoning_json(evidence_id: uuid.UUID) -> str:
    return json.dumps(
        {
            "summary": "The API showed elevated latency.",
            "observations": [
                {
                    "text": "The monitoring record reports elevated latency.",
                    "evidence_ids": [str(evidence_id)],
                }
            ],
            "uncertainties": ["The available evidence does not establish cause."],
            "follow_up_questions": ["Did latency increase across all instances?"],
        }
    )


def make_budget(*, budget_usd: float = 25.0) -> LLMBudgetGuard:
    return LLMBudgetGuard(
        budget_usd=budget_usd,
        input_cost_per_million_usd=1.0,
        output_cost_per_million_usd=1.0,
    )


def make_service(
    provider: FakeLLMProvider,
    budget: LLMBudgetGuard | None = None,
) -> LLMService:
    return LLMService(
        provider=provider,
        budget_guard=budget or make_budget(),
        model="test/nemotron",
        max_attempts=1,
        retry_backoff_seconds=0,
        max_input_tokens=12_000,
        max_output_tokens=100,
    )


@pytest.mark.asyncio
async def test_reasoning_uses_structured_evidence_and_validates_references() -> None:
    _, evidence = make_evidence()
    provider = FakeLLMProvider([reasoning_json(evidence.items[0].evidence_id)])

    response = await make_service(provider).reason(evidence)

    assert response.reasoning.observations[0].evidence_ids == [evidence.items[0].evidence_id]
    assert response.metadata.provider == "nebius"
    assert response.metadata.input_tokens == 100
    assert response.metadata.output_tokens == 30
    assert response.metadata.request_id == "request-1"
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_cache_hit_makes_no_second_provider_call_or_charge() -> None:
    _, evidence = make_evidence()
    provider = FakeLLMProvider([reasoning_json(evidence.items[0].evidence_id)])
    budget = make_budget()
    service = make_service(provider, budget)

    first = await service.reason(evidence)
    spent_after_first = await budget.spent_usd()
    second = await service.reason(evidence)

    assert provider.calls == 1
    assert second.metadata.cache_hit is True
    assert second.metadata.estimated_cost_usd == 0
    assert await budget.spent_usd() == spent_after_first
    assert first.reasoning == second.reasoning


@pytest.mark.asyncio
async def test_response_cannot_reference_evidence_outside_the_request() -> None:
    _, evidence = make_evidence()
    provider = FakeLLMProvider([reasoning_json(uuid.uuid4())])

    with pytest.raises(LLMServiceError, match="outside the request"):
        await make_service(provider).reason(evidence)


@pytest.mark.asyncio
async def test_malformed_response_fails_validation_without_raw_output_in_error() -> None:
    _, evidence = make_evidence()
    provider = FakeLLMProvider(['{"summary":"missing required fields"}'])

    with pytest.raises(LLMServiceError, match="structured reasoning validation"):
        await make_service(provider).reason(evidence)


@pytest.mark.asyncio
async def test_empty_evidence_never_calls_provider() -> None:
    context = make_context()
    evidence = EvidenceEngine().process([], context)
    provider = FakeLLMProvider([])

    with pytest.raises(LLMServiceError, match="without evidence"):
        await make_service(provider).reason(evidence)
    assert provider.calls == 0


@pytest.mark.asyncio
async def test_budget_guard_rejects_request_before_provider_call() -> None:
    _, evidence = make_evidence()
    provider = FakeLLMProvider([reasoning_json(evidence.items[0].evidence_id)])
    budget = make_budget(budget_usd=0.000001)

    with pytest.raises(LLMServiceError, match="exceed"):
        await make_service(provider, budget).reason(evidence)
    assert provider.calls == 0


@pytest.mark.asyncio
async def test_retry_is_bounded_and_failed_attempt_is_charged() -> None:
    _, evidence = make_evidence()
    content = reasoning_json(evidence.items[0].evidence_id)

    class FlakyProvider(FakeLLMProvider):
        async def complete(
            self,
            *,
            model: str,
            system_message: str,
            user_message: str,
            max_output_tokens: int,
            timeout_seconds: float,
        ) -> ProviderCompletion:
            self.calls += 1
            if self.calls == 1:
                raise LLMTransientError("temporary")
            return ProviderCompletion(
                content=content,
                prompt_tokens=100,
                completion_tokens=30,
                request_id="retry-success",
                model="test/nemotron",
            )

    provider = FlakyProvider([])
    budget = make_budget()
    service = LLMService(
        provider=provider,
        budget_guard=budget,
        model="test/nemotron",
        max_attempts=2,
        retry_backoff_seconds=0,
        max_input_tokens=12_000,
        max_output_tokens=100,
    )

    response = await service.reason(evidence)

    assert response.metadata.attempts == 2
    assert provider.calls == 2
    assert await budget.spent_usd() == pytest.approx(response.metadata.estimated_cost_usd)
    assert response.metadata.estimated_cost_usd > 0.00013


@pytest.mark.asyncio
async def test_analyze_stage_skips_when_collection_has_no_evidence() -> None:
    context = make_context()
    context.evidence_collection = EvidenceEngine().process([], context)
    provider = FakeLLMProvider([])

    result = await AnalyzeStage(make_service(provider)).execute(context)

    assert result.status == ExecutionStatus.SUCCESS
    assert result.output_metadata["analysis_status"] == "skipped_no_evidence"
    assert provider.calls == 0


@pytest.mark.asyncio
async def test_collect_and_analyze_stages_pass_evidence_to_injected_service() -> None:
    context = make_context()
    collect = CollectEvidenceStage(agents=[EvidenceAgent()])
    collected = await collect.execute(context)
    assert context.evidence_collection is not None
    assert collected.evidence_collection is not None

    provider = FakeLLMProvider([reasoning_json(context.evidence_collection.items[0].evidence_id)])
    service = make_service(provider)
    analyzed = await AnalyzeStage(service).execute(context)

    assert analyzed.status == ExecutionStatus.SUCCESS
    assert analyzed.output_metadata["analysis_status"] == "completed"
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_unconfigured_analyze_stage_is_offline_by_default() -> None:
    context = make_context()
    stage = AnalyzeStage()

    result = await stage.execute(context)

    assert result.status == ExecutionStatus.SUCCESS
    assert result.output_metadata["analysis_status"] == "reasoning_disabled"


@pytest.mark.asyncio
async def test_nebius_provider_uses_openai_contract_and_keeps_key_out_of_errors() -> None:
    seen: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        assert request.headers["Authorization"] == "Bearer test-secret"
        assert json.loads(request.content)["response_format"] == {"type": "json_object"}
        return httpx.Response(
            200,
            json={
                "id": "nb-1",
                "model": "nvidia/test",
                "choices": [{"message": {"content": '{"summary":"ok"}'}}],
                "usage": {"prompt_tokens": 9, "completion_tokens": 4},
            },
        )

    provider = NebiusNemotronProvider(
        SecretStr("test-secret"),
        "https://api.studio.nebius.ai/v1",
        transport=httpx.MockTransport(handler),
    )
    completion = await provider.complete(
        model="nvidia/test",
        system_message="system",
        user_message="{}",
        max_output_tokens=50,
        timeout_seconds=1,
    )

    assert seen[0].url.path == "/v1/chat/completions"
    assert completion.request_id == "nb-1"
    assert completion.prompt_tokens == 9


def test_nebius_provider_rejects_insecure_url() -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        NebiusNemotronProvider(SecretStr("test-secret"), "http://localhost/v1")


def test_nebius_service_factory_fails_closed_without_explicit_opt_in() -> None:
    config = Settings(_env_file=None)
    with pytest.raises(ValueError, match="LLM_ENABLED"):
        create_nebius_llm_service(config)


def test_nebius_service_factory_requires_key_and_current_pricing() -> None:
    config = Settings(
        _env_file=None,
        llm_enabled=True,
    )
    with pytest.raises(ValueError, match="NEBIUS_API_KEY"):
        create_nebius_llm_service(config)

    config = Settings(
        _env_file=None,
        llm_enabled=True,
        nebius_api_key="test-key",
    )
    with pytest.raises(ValueError, match="current positive Nebius token prices"):
        create_nebius_llm_service(config)


@pytest.mark.asyncio
async def test_budget_guard_reservations_are_settled_once() -> None:
    budget = make_budget(budget_usd=0.001)
    reservation = await budget.reserve(input_tokens=100, output_tokens=100)
    assert await budget.remaining_usd() < 0.001

    await budget.settle(
        reservation,
        prompt_tokens=10,
        completion_tokens=20,
    )
    assert await budget.spent_usd() == pytest.approx(0.00003)
    with pytest.raises(ValueError, match="unknown or already settled"):
        await budget.settle(
            reservation,
            prompt_tokens=10,
            completion_tokens=20,
        )


@pytest.mark.asyncio
async def test_sqlite_budget_ledger_shares_reservations_and_spend(tmp_path) -> None:
    ledger_path = tmp_path / "llm-budget.sqlite3"
    first_guard = LLMBudgetGuard(
        budget_usd=0.00025,
        input_cost_per_million_usd=1,
        output_cost_per_million_usd=1,
        ledger_path=ledger_path,
    )
    reservation = await first_guard.reserve(input_tokens=100, output_tokens=100)
    restarted_guard = LLMBudgetGuard(
        budget_usd=0.00025,
        input_cost_per_million_usd=1,
        output_cost_per_million_usd=1,
        ledger_path=ledger_path,
    )

    assert await restarted_guard.remaining_usd() == pytest.approx(0.00005)
    with pytest.raises(BudgetExceededError):
        await restarted_guard.reserve(input_tokens=100, output_tokens=100)

    await first_guard.settle(
        reservation,
        prompt_tokens=10,
        completion_tokens=10,
    )
    assert await restarted_guard.spent_usd() == pytest.approx(0.00002)
    assert await restarted_guard.remaining_usd() == pytest.approx(0.00023)


def test_sqlite_budget_ledger_rejects_configuration_changes(tmp_path) -> None:
    ledger_path = tmp_path / "llm-budget.sqlite3"
    LLMBudgetGuard(
        budget_usd=1,
        input_cost_per_million_usd=1,
        output_cost_per_million_usd=1,
        ledger_path=ledger_path,
    )

    with pytest.raises(ValueError, match="different budget or token prices"):
        LLMBudgetGuard(
            budget_usd=2,
            input_cost_per_million_usd=1,
            output_cost_per_million_usd=1,
            ledger_path=ledger_path,
        )
