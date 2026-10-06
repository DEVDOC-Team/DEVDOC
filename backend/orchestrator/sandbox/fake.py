"""Deterministic sandbox provider for tests and local contract validation."""

from __future__ import annotations

from orchestrator.sandbox.models import (
    SandboxExecution,
    SandboxHandle,
    SandboxLimits,
    SandboxProviderError,
    VerificationCommand,
)


class FakeSandboxProvider:
    def __init__(
        self,
        executions: list[SandboxExecution] | None = None,
        *,
        create_error: SandboxProviderError | None = None,
        cleanup_error: SandboxProviderError | None = None,
    ) -> None:
        self.executions = list(executions or [])
        self.create_error = create_error
        self.cleanup_error = cleanup_error
        self.created: list[str] = []
        self.commands: list[list[str]] = []
        self.cleaned: list[str] = []

    async def create(
        self,
        sandbox_id: str,
        workspace_path: str,
        limits: SandboxLimits,
    ) -> SandboxHandle:
        if self.create_error is not None:
            raise self.create_error
        self.created.append(sandbox_id)
        return SandboxHandle(sandbox_id=sandbox_id)

    async def execute(
        self,
        handle: SandboxHandle,
        command: VerificationCommand,
        limits: SandboxLimits,
    ) -> SandboxExecution:
        self.commands.append(command.argv)
        if self.executions:
            return self.executions.pop(0)
        return SandboxExecution(
            exit_code=0,
            stdout="",
            stderr="",
            duration_ms=0,
        )

    async def cleanup(self, handle: SandboxHandle) -> None:
        self.cleaned.append(handle.sandbox_id)
        if self.cleanup_error is not None:
            raise self.cleanup_error
