"""Nebius OpenAI-compatible adapter for NVIDIA Nemotron."""

from __future__ import annotations

import httpx
from pydantic import SecretStr

from orchestrator.llm.contracts import ProviderCompletion
from orchestrator.llm.provider import LLMProviderError, LLMTransientError


class NebiusNemotronProvider:
    """Calls Nemotron through Nebius Token Factory's OpenAI-compatible API."""

    def __init__(
        self,
        api_key: SecretStr,
        base_url: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        key = api_key.get_secret_value().strip()
        if not key:
            raise ValueError("A Nebius API key is required to construct the provider")
        if not base_url.startswith("https://"):
            raise ValueError("Nebius API base URL must use HTTPS")
        self._api_key = key
        self._endpoint = f"{base_url.rstrip('/')}/chat/completions"
        self._transport = transport

    async def complete(
        self,
        *,
        model: str,
        system_message: str,
        user_message: str,
        max_output_tokens: int,
        timeout_seconds: float,
    ) -> ProviderCompletion:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message},
            ],
            "max_tokens": max_output_tokens,
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        try:
            async with httpx.AsyncClient(
                timeout=timeout_seconds,
                transport=self._transport,
            ) as client:
                response = await client.post(
                    self._endpoint,
                    json=payload,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
        except httpx.TimeoutException:
            raise LLMTransientError("Nebius request timed out") from None
        except httpx.NetworkError:
            raise LLMTransientError("Nebius network request failed") from None

        if response.status_code == 429 or response.status_code >= 500:
            raise LLMTransientError(f"Nebius returned retryable HTTP status {response.status_code}")
        if response.is_error:
            raise LLMProviderError(f"Nebius returned HTTP status {response.status_code}")

        try:
            body = response.json()
            choice = body["choices"][0]
            content = choice["message"]["content"]
            usage = body.get("usage", {})
            if not isinstance(content, str) or not isinstance(usage, dict):
                raise TypeError
        except (ValueError, KeyError, IndexError, TypeError):
            raise LLMProviderError("Nebius returned an invalid completion response") from None

        returned_model = body.get("model")
        request_id = body.get("id")
        return ProviderCompletion(
            content=content,
            prompt_tokens=_optional_nonnegative_int(usage.get("prompt_tokens")),
            completion_tokens=_optional_nonnegative_int(usage.get("completion_tokens")),
            request_id=request_id if isinstance(request_id, str) else None,
            model=returned_model if isinstance(returned_model, str) else model,
        )


def _optional_nonnegative_int(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None
