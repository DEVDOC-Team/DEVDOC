"""Deterministic Phase 17 sandbox tests; no Docker daemon or network is used."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from orchestrator.core.context import InvestigationContext
from orchestrator.fixes.models import (
    FixChange,
    FixProposal,
    FixProposalStatus,
    FixRisk,
    FixRiskCategory,
    FixRiskSeverity,
    FixRollbackStep,
    FixVerificationStep,
)
from orchestrator.llm.contracts import LLMObservability
from orchestrator.sandbox.docker import DockerSandboxProvider
from orchestrator.sandbox.fake import FakeSandboxProvider
from orchestrator.sandbox.models import (
    SandboxExecution,
    SandboxHandle,
    SandboxLimits,
    SandboxProviderError,
    SandboxTimeoutError,
    VerificationCommand,
    VerificationStatus,
)
from orchestrator.sandbox.security import UnsafeSandboxInput, apply_fix_change
from orchestrator.sandbox.service import SandboxVerificationService
from orchestrator.stages.investigation import VerifyStage


def make_proposal(
    *,
    expected_result: str = "CHECKS_OK",
    changes: list[FixChange] | None = None,
) -> FixProposal:
    return FixProposal(
        proposal_id=uuid.uuid4(),
        investigation_id=uuid.uuid4(),
        execution_id=uuid.uuid4(),
        root_cause_reference=uuid.uuid4(),
        status=FixProposalStatus.REQUIRES_HUMAN_REVIEW,
        summary="Correct the validated setting.",
        rationale="The observed evidence supports the proposed change.",
        affected_components=["api"],
        change_type="configuration_change",
        changes=changes
        or [
            FixChange(
                target="application setting",
                target_path="app/settings.py",
                operation="replace setting",
                proposed_state="enabled = True\n",
                reason="Restore the expected service setting.",
                evidence_references=[uuid.uuid4()],
            )
        ],
        prerequisites=[],
        risks=[
            FixRisk(
                category=FixRiskCategory.COMPATIBILITY,
                severity=FixRiskSeverity.LOW,
                description="The setting may be rejected.",
                mitigation="Validate in the sandbox.",
            )
        ],
        verification_plan=[
            FixVerificationStep(
                description="Run the configured checks.",
                expected_result=expected_result,
                evidence_required=["validation output"],
            )
        ],
        rollback_plan=[
            FixRollbackStep(
                description="Restore the original setting.",
                trigger="Sandbox validation fails.",
                expected_result="The original setting is restored.",
            )
        ],
        evidence_references=[uuid.uuid4()],
        external_knowledge_references=[],
        confidence=0.8,
        change_scope="One application setting.",
        generated_at=datetime.now(UTC),
        model_metadata=LLMObservability(
            model="test-model",
            duration_ms=0,
            attempts=0,
            input_tokens=0,
            output_tokens=0,
            estimated_cost_usd=0,
            budget_remaining_usd=1,
        ),
    )


def make_command() -> VerificationCommand:
    return VerificationCommand(step_index=0, argv=["pytest", "-q"])


@pytest.mark.asyncio
async def test_verification_applies_change_in_copy_and_cleans_up(tmp_path) -> None:
    source = tmp_path / "repository"
    source.mkdir()
    (source / "app").mkdir()
    (source / "app" / "settings.py").write_text("enabled = False\n", encoding="utf-8")
    (source / ".env").write_text("PRODUCTION_TOKEN=must-not-copy", encoding="utf-8")
    class InspectingProvider(FakeSandboxProvider):
        workspace: Path
        copied_setting: str
        copied_env_exists: bool

        async def create(
            self,
            sandbox_id: str,
            workspace_path: str,
            limits: SandboxLimits,
        ) -> SandboxHandle:
            self.workspace = Path(workspace_path)
            return await super().create(sandbox_id, workspace_path, limits)

        async def execute(
            self,
            handle: SandboxHandle,
            command: VerificationCommand,
            limits: SandboxLimits,
        ) -> SandboxExecution:
            self.copied_setting = (self.workspace / "app" / "settings.py").read_text(
                encoding="utf-8"
            )
            self.copied_env_exists = (self.workspace / ".env").exists()
            return await super().execute(handle, command, limits)

    provider = InspectingProvider(
        [
            SandboxExecution(
                exit_code=0,
                stdout="CHECKS_OK",
                stderr="",
                duration_ms=5,
            )
        ]
    )

    result = await SandboxVerificationService(provider).verify(
        make_proposal(),
        workspace_path=source,
        commands=[make_command()],
    )

    assert result.status == VerificationStatus.PASSED
    assert result.cleanup_status == "complete"
    assert result.passed_steps == 1
    assert provider.cleaned == provider.created
    assert (source / "app" / "settings.py").read_text(encoding="utf-8") == "enabled = False\n"
    assert provider.copied_setting == "enabled = True\n"
    assert provider.copied_env_exists is False


@pytest.mark.asyncio
async def test_success_exit_without_expected_observation_is_inconclusive(tmp_path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    provider = FakeSandboxProvider(
        [SandboxExecution(exit_code=0, stdout="Completed", stderr="", duration_ms=2)]
    )

    result = await SandboxVerificationService(provider).verify(
        make_proposal(),
        workspace_path=source,
        commands=[make_command()],
    )

    assert result.status == VerificationStatus.INCONCLUSIVE
    assert result.failed_steps == 0
    assert provider.cleaned == provider.created


@pytest.mark.asyncio
async def test_nonzero_exit_fails_and_still_cleans_up(tmp_path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    provider = FakeSandboxProvider(
        [SandboxExecution(exit_code=2, stdout="CHECKS_OK", stderr="assertion failed", duration_ms=4)]
    )

    result = await SandboxVerificationService(provider).verify(
        make_proposal(),
        workspace_path=source,
        commands=[make_command()],
    )

    assert result.status == VerificationStatus.FAILED
    assert result.failed_steps == 1
    assert provider.cleaned == provider.created


@pytest.mark.asyncio
async def test_missing_authorized_source_is_inconclusive_without_provider_calls() -> None:
    provider = FakeSandboxProvider()
    result = await SandboxVerificationService(provider).verify(
        make_proposal(),
        workspace_path=None,
        commands=[make_command()],
    )
    assert result.status == VerificationStatus.INCONCLUSIVE
    assert provider.created == []


@pytest.mark.asyncio
async def test_unsafe_target_is_rejected_before_sandbox_creation(tmp_path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    proposal = make_proposal(
        changes=[
            FixChange(
                target="environment",
                target_path="../.env",
                operation="replace",
                proposed_state="TOKEN=value",
                reason="unsafe",
                evidence_references=[uuid.uuid4()],
            )
        ]
    )
    provider = FakeSandboxProvider()

    result = await SandboxVerificationService(provider).verify(
        proposal,
        workspace_path=source,
        commands=[make_command()],
    )

    assert result.status == VerificationStatus.UNSAFE
    assert provider.created == []


def test_patch_applier_verifies_context_and_confines_target(tmp_path) -> None:
    target = tmp_path / "service.py"
    target.write_text("status = 'broken'\n", encoding="utf-8")
    change = FixChange(
        target="service",
        target_path="service.py",
        operation="fix status",
        proposed_diff=(
            "--- a/service.py\n"
            "+++ b/service.py\n"
            "@@ -1 +1 @@\n"
            "-status = 'broken'\n"
            "+status = 'healthy'\n"
        ),
        reason="restore the service status",
        evidence_references=[uuid.uuid4()],
    )
    assert apply_fix_change(tmp_path, change) == "service.py"
    assert target.read_text(encoding="utf-8") == "status = 'healthy'\n"


def test_patch_rejects_mismatched_hunk_and_unsafe_commands() -> None:
    with pytest.raises(UnsafeSandboxInput):
        apply_fix_change(
            Path("."),
            FixChange(
                target="outside",
                target_path="../outside.py",
                operation="write",
                proposed_state="bad",
                reason="unsafe",
                evidence_references=[uuid.uuid4()],
            ),
        )
    with pytest.raises(ValidationError):
        VerificationCommand(step_index=0, argv=["python", "-c", "print('unsafe')"])


@pytest.mark.asyncio
async def test_patch_failure_has_structured_failure_code(tmp_path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "service.py").write_text("state = 'healthy'\n", encoding="utf-8")
    proposal = make_proposal(
        changes=[
            FixChange(
                target="service",
                target_path="service.py",
                operation="change state",
                proposed_diff=(
                    "--- a/service.py\n"
                    "+++ b/service.py\n"
                    "@@ -1 +1 @@\n"
                    "-state = 'broken'\n"
                    "+state = 'healthy'\n"
                ),
                reason="test mismatch",
                evidence_references=[uuid.uuid4()],
            )
        ]
    )
    provider = FakeSandboxProvider()

    result = await SandboxVerificationService(provider).verify(
        proposal,
        workspace_path=source,
        commands=[make_command()],
    )

    assert result.status == VerificationStatus.FAILED
    assert "PATCH_APPLICATION_FAILED" in result.risk_findings
    assert provider.created == []


@pytest.mark.asyncio
async def test_context_cancellation_stops_running_step_and_cleans_up(tmp_path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    started = asyncio.Event()

    class BlockingProvider(FakeSandboxProvider):
        async def execute(self, handle, command, limits):
            started.set()
            await asyncio.Event().wait()

    provider = BlockingProvider()
    cancelled = False
    task = asyncio.create_task(
        SandboxVerificationService(provider).verify(
            make_proposal(),
            workspace_path=source,
            commands=[make_command()],
            is_cancelled=lambda: cancelled,
        )
    )
    await asyncio.wait_for(started.wait(), timeout=2)
    cancelled = True
    result = await asyncio.wait_for(task, timeout=2)

    assert result.status == VerificationStatus.CANCELLED
    assert result.cleanup_status == "complete"
    assert provider.cleaned == provider.created


def test_docker_provider_requires_pinned_image_and_uses_isolated_flags(
    tmp_path,
    monkeypatch,
) -> None:
    with pytest.raises(ValueError):
        DockerSandboxProvider("python:3.13")
    provider = DockerSandboxProvider(f"python@sha256:{'a' * 64}")
    calls: list[list[str]] = []
    outputs = [
        SimpleNamespace(returncode=0, stdout="[]", stderr="", truncated=False),
        SimpleNamespace(returncode=0, stdout="null", stderr="", truncated=False),
        SimpleNamespace(returncode=0, stdout="a" * 64, stderr="", truncated=False),
        SimpleNamespace(returncode=0, stdout="", stderr="", truncated=False),
        SimpleNamespace(returncode=0, stdout="", stderr="", truncated=False),
        SimpleNamespace(returncode=0, stdout="", stderr="", truncated=False),
    ]

    async def fake_run(args, **_kwargs):
        calls.append(args)
        return outputs.pop(0)

    monkeypatch.setattr(provider, "_run", fake_run)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    handle = asyncio.run(
        provider.create(
            str(uuid.uuid4()),
            str(workspace),
            SandboxVerificationService(FakeSandboxProvider()).limits,
        )
    )
    asyncio.run(provider.cleanup(handle))

    create_args = calls[2]
    assert create_args[create_args.index("--network") + 1] == "none"
    assert "--read-only" in create_args
    assert "--privileged" not in create_args
    assert "--env-file" not in create_args
    assert "--mount" not in create_args
    assert "--pids-limit" in create_args
    assert create_args[create_args.index("--entrypoint") + 1] == "sleep"
    assert calls[-1][1:3] == ["--force", "--volumes"]


def test_docker_provider_rejects_images_with_credentials_or_declared_volumes(
    tmp_path,
    monkeypatch,
) -> None:
    provider = DockerSandboxProvider(f"python@sha256:{'a' * 64}")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    calls: list[list[str]] = []

    async def fake_run(args, **_kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout='["API_TOKEN=embedded"]', stderr="", truncated=False)

    monkeypatch.setattr(provider, "_run", fake_run)
    with pytest.raises(SandboxProviderError, match="credential-like"):
        asyncio.run(
            provider.create(
                str(uuid.uuid4()),
                str(workspace),
                SandboxVerificationService(FakeSandboxProvider()).limits,
            )
        )
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_provider_setup_failure_is_typed_and_does_not_leak_error_text(tmp_path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    provider = FakeSandboxProvider(create_error=SandboxProviderError("private runtime detail"))
    result = await SandboxVerificationService(provider).verify(
        make_proposal(),
        workspace_path=source,
        commands=[make_command()],
    )
    assert result.status == VerificationStatus.SETUP_FAILED
    assert "private runtime detail" not in result.summary
    assert result.cleanup_status == "not_started"


@pytest.mark.asyncio
async def test_timeout_is_recorded_and_container_cleaned(tmp_path) -> None:
    source = tmp_path / "source"
    source.mkdir()

    class TimeoutProvider(FakeSandboxProvider):
        async def execute(self, handle, command, limits):
            raise SandboxTimeoutError("deadline")

    provider = TimeoutProvider()
    result = await SandboxVerificationService(provider).verify(
        make_proposal(),
        workspace_path=source,
        commands=[make_command()],
    )
    assert result.status == VerificationStatus.TIMEOUT
    assert result.verification_steps[0].status.value == "timeout"
    assert provider.cleaned == provider.created


@pytest.mark.asyncio
async def test_verify_stage_uses_injected_provider_and_exposes_typed_result(tmp_path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    provider = FakeSandboxProvider(
        [SandboxExecution(exit_code=0, stdout="CHECKS_OK", stderr="", duration_ms=1)]
    )

    async def resolve_workspace(_context, _proposal):
        return source

    stage = VerifyStage(
        SandboxVerificationService(provider),
        resolve_workspace,
        [make_command()],
    )
    context = InvestigationContext(
        investigation_id=uuid.uuid4(),
        incident_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
    )
    context.fix_proposal = make_proposal()

    stage_result = await stage.execute(context)

    assert stage_result.status.value == "success"
    assert stage_result.output_metadata["verification_status"] == "passed"
    assert context.sandbox_verification_result is not None


@pytest.mark.asyncio
async def test_unconfigured_verify_stage_does_not_attempt_execution() -> None:
    provider = FakeSandboxProvider()
    stage = VerifyStage()
    context = InvestigationContext(
        investigation_id=uuid.uuid4(),
        incident_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
    )
    context.fix_proposal = make_proposal()

    result = await stage.execute(context)

    assert result.status.value == "skipped"
    assert result.output_metadata["verification_status"] == "inconclusive"
    assert provider.created == []
