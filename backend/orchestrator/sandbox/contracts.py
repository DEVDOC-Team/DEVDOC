"""Provider abstraction for disposable execution sandboxes."""

from __future__ import annotations

from typing import Protocol

from orchestrator.sandbox.models import (
    SandboxExecution,
    SandboxHandle,
    SandboxLimits,
    VerificationCommand,
)


class SandboxProvider(Protocol):
    async def create(
        self,
        sandbox_id: str,
        workspace_path: str,
        limits: SandboxLimits,
    ) -> SandboxHandle: ...

    async def execute(
        self,
        handle: SandboxHandle,
        command: VerificationCommand,
        limits: SandboxLimits,
    ) -> SandboxExecution: ...

    async def cleanup(self, handle: SandboxHandle) -> None: ...
