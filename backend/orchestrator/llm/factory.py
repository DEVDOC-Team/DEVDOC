"""Explicit construction helpers for opt-in Phase 13 Nebius reasoning."""

from __future__ import annotations

import hashlib
import threading
from pathlib import Path

from app.core.config import Settings
from orchestrator.llm.budget import LLMBudgetGuard
from orchestrator.llm.nebius import NebiusNemotronProvider
from orchestrator.llm.service import LLMService

_service_lock = threading.Lock()
_process_service: LLMService | None = None
_process_config_fingerprint: tuple[object, ...] | None = None


def create_nebius_llm_service(config: Settings) -> LLMService:
    """Build a service only when explicitly enabled and fully budget-configured."""
    global _process_service, _process_config_fingerprint

    if not config.llm_enabled:
        raise ValueError("LLM reasoning is disabled; set LLM_ENABLED=true to opt in")
    if not config.nebius_api_key.get_secret_value():
        raise ValueError("NEBIUS_API_KEY is required when LLM reasoning is enabled")
    if config.llm_input_cost_per_million_usd <= 0 or config.llm_output_cost_per_million_usd <= 0:
        raise ValueError("Set current positive Nebius token prices before enabling LLM reasoning")

    fingerprint = (
        hashlib.sha256(config.nebius_api_key.get_secret_value().encode()).digest(),
        config.nebius_base_url,
        config.nebius_model,
        config.llm_timeout_seconds,
        config.llm_max_attempts,
        config.llm_retry_backoff_seconds,
        config.llm_max_input_tokens,
        config.llm_max_output_tokens,
        config.llm_budget_usd,
        config.llm_budget_ledger_path,
        config.llm_input_cost_per_million_usd,
        config.llm_output_cost_per_million_usd,
        config.llm_cache_ttl_seconds,
        config.llm_cache_max_entries,
    )
    with _service_lock:
        if _process_service is not None:
            if fingerprint != _process_config_fingerprint:
                raise ValueError(
                    "The process LLM service is already configured; restart to change settings"
                )
            return _process_service

        provider = NebiusNemotronProvider(
            api_key=config.nebius_api_key,
            base_url=config.nebius_base_url,
        )
        ledger_path = Path(config.llm_budget_ledger_path)
        if not ledger_path.is_absolute():
            ledger_path = Path(__file__).resolve().parents[2] / ledger_path
        budget = LLMBudgetGuard(
            budget_usd=config.llm_budget_usd,
            input_cost_per_million_usd=config.llm_input_cost_per_million_usd,
            output_cost_per_million_usd=config.llm_output_cost_per_million_usd,
            ledger_path=ledger_path,
        )
        _process_service = LLMService(
            provider=provider,
            budget_guard=budget,
            model=config.nebius_model,
            timeout_seconds=config.llm_timeout_seconds,
            max_attempts=config.llm_max_attempts,
            retry_backoff_seconds=config.llm_retry_backoff_seconds,
            max_input_tokens=config.llm_max_input_tokens,
            max_output_tokens=config.llm_max_output_tokens,
            cache_ttl_seconds=config.llm_cache_ttl_seconds,
            cache_max_entries=config.llm_cache_max_entries,
        )
        _process_config_fingerprint = fingerprint
        return _process_service
