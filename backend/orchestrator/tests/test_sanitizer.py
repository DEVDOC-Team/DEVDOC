"""Tests for operational data sanitizer."""

from __future__ import annotations

from orchestrator.core.sanitizer import (
    is_sensitive_key,
    sanitize_data,
    sanitize_string,
)


def test_is_sensitive_key() -> None:
    assert is_sensitive_key("token")
    assert is_sensitive_key("auth_token")
    assert is_sensitive_key("api_key")
    assert is_sensitive_key("password")
    assert is_sensitive_key("client_secret")
    assert is_sensitive_key("bearer")
    assert is_sensitive_key("private_key")
    assert not is_sensitive_key("repository_name")
    assert not is_sensitive_key("container_status")
    assert not is_sensitive_key("cpu_percent")


def test_sanitize_string_tokens() -> None:
    ghp = "ghp_1234567890abcdefghijklmnopqrstuvwxyzAB"
    assert sanitize_string(f"Error using {ghp} token") == "Error using [REDACTED] token"

    pat = "github_pat_11AAAAAAA0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789ab"
    assert sanitize_string(f"Header: {pat}") == "Header: [REDACTED]"

    bearer = "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    assert sanitize_string(f"Auth: {bearer}") == "Auth: [REDACTED]"


def test_sanitize_dict_keys_and_values() -> None:
    data = {
        "repo": "devdoc/backend",
        "api_key": "secret_key_123",
        "password": "supersecretpassword",
        "nested": {
            "token": "ghp_1234567890abcdefghijklmnopqrstuvwxyzAB",
            "safe_metric": 42.0,
        },
        "tags": ["prod", "auth_token=super_secret"],
    }

    sanitized = sanitize_data(data)
    assert sanitized["repo"] == "devdoc/backend"
    assert "api_key" not in sanitized
    assert "password" not in sanitized
    assert sanitized["nested"]["safe_metric"] == 42.0
    assert "token" not in sanitized["nested"]
    assert "[REDACTED]" in sanitized["tags"][1]
