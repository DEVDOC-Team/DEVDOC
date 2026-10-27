"""Typed contracts and conservative resource limits for sandbox verification."""

from __future__ import annotations

import enum
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class VerificationStatus(str, enum.Enum):
    PASSED = "passed"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    UNSAFE = "unsafe"
    SETUP_FAILED = "setup_failed"


class VerificationStepStatus(str, enum.Enum):
    PASSED = "passed"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


class SandboxLimits(BaseModel):
    """Hard ceilings; callers may lower but cannot raise these values."""

    execution_timeout_seconds: int = Field(default=120, ge=1, le=600)
    memory_mb: int = Field(default=512, ge=64, le=2048)
    cpu_count: float = Field(default=1.0, gt=0, le=2)
    process_limit: int = Field(default=64, ge=8, le=256)
    workspace_mb: int = Field(default=256, ge=16, le=1024)
    workspace_files: int = Field(default=10_000, ge=100, le=50_000)
    output_bytes: int = Field(default=32_768, ge=1024, le=256_000)
    log_bytes: int = Field(default=262_144, ge=4096, le=1_000_000)


class VerificationCommand(BaseModel):
    """Trusted, explicitly configured argv for one proposal verification criterion.

    Commands never come from FixProposal text. The command is injected by the
    deployment/test configuration and is still validated before sandbox execution.
    """

    step_index: int = Field(ge=0, le=19)
    argv: list[str] = Field(min_length=1, max_length=32)
    timeout_seconds: int = Field(default=120, ge=1, le=600)

    @field_validator("argv")
    @classmethod
    def validate_argv(cls, argv: list[str]) -> list[str]:
        allowed = {"pytest", "python", "python3", "ruff", "mypy", "go", "cargo", "make"}
        executable = argv[0].rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        if executable not in allowed or argv[0] != executable:
            raise ValueError("Verification executable is not allowlisted")
        for argument in argv:
            if (
                not argument
                or len(argument) > 1024
                or re.search(r"[\r\n;&|<>`]", argument)
                or "$(" in argument
                or "${" in argument
            ):
                raise ValueError("Verification arguments contain unsafe syntax")
        if executable in {"python", "python3"}:
            if "-c" in argv:
                raise ValueError("Inline Python execution is not allowed")
            if "-m" in argv:
                module_index = argv.index("-m") + 1
                if module_index >= len(argv) or argv[module_index] not in {
                    "pytest",
                    "unittest",
                    "compileall",
                }:
                    raise ValueError("Python module is not allowlisted")
        return argv

    model_config = ConfigDict(extra="forbid", frozen=True)


class VerificationStepResult(BaseModel):
    step_id: str
    description: str
    status: VerificationStepStatus
    exit_code: int | None = None
    duration_ms: float = Field(ge=0)
    stdout: str = ""
    stderr: str = ""
    expected_result: str
    observed_result: str = ""
    failure_analysis: str | None = None
    warnings: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid", frozen=True)


class SandboxVerificationResult(BaseModel):
    verification_id: uuid.UUID
    investigation_id: uuid.UUID
    proposal_id: uuid.UUID
    status: VerificationStatus
    sandbox_id: str | None = None
    started_at: datetime
    completed_at: datetime
    applied_changes: list[str] = Field(default_factory=list)
    verification_steps: list[VerificationStepResult] = Field(default_factory=list)
    passed_steps: int = 0
    failed_steps: int = 0
    logs: str = ""
    artifacts: list[str] = Field(default_factory=list)
    risk_findings: list[str] = Field(default_factory=list)
    cleanup_status: Literal["complete", "failed", "not_started"]
    summary: str

    model_config = ConfigDict(extra="forbid", frozen=True)


class SandboxProviderError(RuntimeError):
    """A provider operation failed without exposing unbounded output or secrets."""


class SandboxTimeoutError(SandboxProviderError):
    """An operation exceeded its explicit deadline."""


@dataclass(frozen=True)
class SandboxHandle:
    sandbox_id: str


@dataclass(frozen=True)
class SandboxExecution:
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: float
    output_truncated: bool = False
