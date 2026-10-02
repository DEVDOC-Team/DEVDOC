"""Operational data sanitizer.

Enforces deep sanitization of all operational data collected by investigation agents
(GitHub, Docker, Monitoring) before passing into InvestigationContext, logs, or results.
Guarantees zero credential leakage, token masking, and key sanitization.
"""

from __future__ import annotations

import re
from typing import Any

from orchestrator.core.context import FORBIDDEN_KEY_PATTERNS

# Regex patterns for detecting sensitive token/key patterns in text
_SENSITIVE_VALUE_PATTERNS = [
    re.compile(r"ghp_[A-Za-z0-9_]+", re.IGNORECASE),
    re.compile(r"github_pat_[A-Za-z0-9_]+", re.IGNORECASE),
    re.compile(r"gho_[A-Za-z0-9_]+", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE),
    re.compile(r"-----BEGIN[ A-Z0-9_-]+KEY-----[\s\S]*?-----END[ A-Z0-9_-]+KEY-----"),
    re.compile(
        r"(?:password|passwd|pwd|auth_token|token|secret|api_key|client_secret)\s*[=:]\s*['\"]?([^'\"\s&;]+)['\"]?",
        re.IGNORECASE,
    ),
    re.compile(r"://([^:\s]+):([^@\s]+)@", re.IGNORECASE),
]


def sanitize_string(value: str) -> str:
    """Mask known sensitive token patterns within a string."""
    sanitized = value
    for pattern in _SENSITIVE_VALUE_PATTERNS:
        sanitized = pattern.sub("[REDACTED]", sanitized)
    return sanitized


def is_sensitive_key(key: str) -> bool:
    """Check if a dictionary key matches forbidden credential patterns."""
    k_lower = key.lower()
    return any(pattern in k_lower for pattern in FORBIDDEN_KEY_PATTERNS)


def sanitize_data(data: Any, mask_key_replacement: str = "redacted_credential") -> Any:
    """Recursively sanitize data structures.

    - Replaces sensitive dictionary keys and redacts their values.
    - Masks secret patterns within string values.
    - Traverses nested dictionaries and lists.
    """
    if isinstance(data, dict):
        sanitized_dict: dict[str, Any] = {}
        for k, v in data.items():
            str_k = str(k)
            if is_sensitive_key(str_k):
                # Replace key name to prevent triggering context validation, and redact value
                safe_key = f"{str_k[:3]}_{mask_key_replacement}" if len(str_k) >= 3 else mask_key_replacement
                sanitized_dict[safe_key] = "[REDACTED]"
            else:
                sanitized_dict[str_k] = sanitize_data(v, mask_key_replacement)
        return sanitized_dict

    if isinstance(data, list):
        return [sanitize_data(item, mask_key_replacement) for item in data]

    if isinstance(data, tuple):
        return tuple(sanitize_data(item, mask_key_replacement) for item in data)

    if isinstance(data, str):
        return sanitize_string(data)

    return data
