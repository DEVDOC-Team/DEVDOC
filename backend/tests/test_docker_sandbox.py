"""Tests for Docker sandbox provider security boundaries and live verification."""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

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
from orchestrator.sandbox.docker import DockerSandboxError, DockerSandboxProvider
from orchestrator.sandbox.models import (
    SandboxLimits,
    VerificationCommand,
    VerificationStatus,
    VerificationStepStatus,
)
from orchestrator.sandbox.service import SandboxVerificationService

PINNED_PYTHON_IMAGE = (
    "python:3.13-alpine@sha256:bf12ecc0bea3f171d55145dd02c78b5eeb09f30ee2ac9cc2b4c9e4e8f5e30741"
)


def _docker_available() -> bool:
    if not shutil.which("docker"):
        return False
    import subprocess
    try:
        res = subprocess.run(
            ["docker", "info"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        if res.returncode != 0:
            return False
        # Ensure test image is locally cached so tests do not fail on image download timeouts
        img = subprocess.run(
            ["docker", "image", "inspect", PINNED_PYTHON_IMAGE],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        return img.returncode == 0
    except Exception:
        return False


def test_docker_provider_rejects_unpinned_image():
    with pytest.raises(ValueError, match="sha256 digest"):
        DockerSandboxProvider(image="alpine:latest")


def test_docker_provider_rejects_malformed_executable():
    with pytest.raises(ValueError, match="command name"):
        DockerSandboxProvider(
            image=PINNED_PYTHON_IMAGE,
            executable="/bin/docker",
        )


def test_verification_command_allowlist():
    # Allowlisted commands
    cmd = VerificationCommand(step_index=0, argv=["pytest", "-k", "test_foo"])
    assert cmd.argv == ["pytest", "-k", "test_foo"]

    cmd2 = VerificationCommand(step_index=1, argv=["python", "verify.py"])
    assert cmd2.argv == ["python", "verify.py"]

    # Disallowed command
    with pytest.raises(ValueError, match="not allowlisted"):
        VerificationCommand(step_index=2, argv=["curl", "http://malicious.com"])

    # Disallowed python -c
    with pytest.raises(ValueError, match="Inline Python execution is not allowed"):
        VerificationCommand(step_index=3, argv=["python", "-c", "import os"])

    # Unsafe shell injection syntax
    with pytest.raises(ValueError, match="unsafe syntax"):
        VerificationCommand(step_index=4, argv=["python", "foo.py; rm -rf /"])


@pytest.mark.asyncio
@pytest.mark.skipif(not _docker_available(), reason="Docker daemon not available")
async def test_live_docker_sandbox_execution():
    provider = DockerSandboxProvider(image=PINNED_PYTHON_IMAGE)
    limits = SandboxLimits(
        workspace_mb=64,
        memory_mb=128,
        cpu_count=1.0,
        process_limit=32,
        execution_timeout_seconds=10,
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        workspace = Path(temp_dir) / "workspace"
        workspace.mkdir()
        test_script = workspace / "test_verification.py"
        test_script.write_text(
            "import os, sys\n"
            "assert os.path.exists('/workspace/test_verification.py')\n"
            "print('SANDBOX_ISOLATED_VERIFICATION_SUCCESS')\n"
            "sys.exit(0)\n"
        )

        sandbox_id = str(uuid.uuid4())
        handle = await provider.create(sandbox_id, str(workspace), limits)
        try:
            cmd = VerificationCommand(
                step_index=0,
                argv=["python", "test_verification.py"],
                timeout_seconds=5,
            )
            result = await provider.execute(handle, cmd, limits)
            assert result.exit_code == 0
            assert "SANDBOX_ISOLATED_VERIFICATION_SUCCESS" in result.stdout
            assert not result.output_truncated
        finally:
            await provider.cleanup(handle)


@pytest.mark.asyncio
@pytest.mark.skipif(not _docker_available(), reason="Docker daemon not available")
async def test_live_docker_sandbox_nonzero_exit():
    provider = DockerSandboxProvider(image=PINNED_PYTHON_IMAGE)
    limits = SandboxLimits(
        workspace_mb=64,
        memory_mb=128,
        cpu_count=1.0,
        process_limit=32,
        execution_timeout_seconds=10,
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        workspace = Path(temp_dir) / "workspace"
        workspace.mkdir()
        fail_script = workspace / "fail_verification.py"
        fail_script.write_text(
            "import sys\n"
            "sys.stderr.write('AssertionError: expected status 200 got 500\\n')\n"
            "sys.exit(1)\n"
        )

        sandbox_id = str(uuid.uuid4())
        handle = await provider.create(sandbox_id, str(workspace), limits)
        try:
            cmd = VerificationCommand(
                step_index=0,
                argv=["python", "fail_verification.py"],
                timeout_seconds=5,
            )
            result = await provider.execute(handle, cmd, limits)
            assert result.exit_code == 1
            assert "AssertionError" in result.stderr
        finally:
            await provider.cleanup(handle)


@pytest.mark.asyncio
@pytest.mark.skipif(not _docker_available(), reason="Docker daemon not available")
async def test_live_docker_sandbox_network_isolation():
    provider = DockerSandboxProvider(image=PINNED_PYTHON_IMAGE)
    limits = SandboxLimits(
        workspace_mb=64,
        memory_mb=128,
        cpu_count=1.0,
        process_limit=32,
        execution_timeout_seconds=10,
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        workspace = Path(temp_dir) / "workspace"
        workspace.mkdir()
        net_script = workspace / "test_network.py"
        net_script.write_text(
            "import urllib.request, sys\n"
            "try:\n"
            "    urllib.request.urlopen('http://1.1.1.1', timeout=2)\n"
            "    print('NETWORK_ACCESSIBLE')\n"
            "    sys.exit(1)\n"
            "except Exception as e:\n"
            "    print(f'NETWORK_BLOCKED:{type(e).__name__}')\n"
            "    sys.exit(0)\n"
        )

        sandbox_id = str(uuid.uuid4())
        handle = await provider.create(sandbox_id, str(workspace), limits)
        try:
            cmd = VerificationCommand(
                step_index=0,
                argv=["python", "test_network.py"],
                timeout_seconds=5,
            )
            result = await provider.execute(handle, cmd, limits)
            assert result.exit_code == 0
            assert "NETWORK_BLOCKED" in result.stdout
        finally:
            await provider.cleanup(handle)


@pytest.mark.asyncio
@pytest.mark.skipif(not _docker_available(), reason="Docker daemon not available")
async def test_live_docker_sandbox_service_verification():
    provider = DockerSandboxProvider(image=PINNED_PYTHON_IMAGE)
    limits = SandboxLimits(
        workspace_mb=64,
        memory_mb=128,
        cpu_count=1.0,
        process_limit=32,
        execution_timeout_seconds=15,
    )
    service = SandboxVerificationService(provider=provider, limits=limits)

    with tempfile.TemporaryDirectory() as temp_dir:
        source_dir = Path(temp_dir) / "source"
        source_dir.mkdir()
        (source_dir / "target.py").write_text("VALUE = 1\n")
        (source_dir / "test_target.py").write_text(
            "from target import VALUE\n"
            "assert VALUE == 2, f'Expected 2, got {VALUE}'\n"
            "print('VERIFICATION_SUCCEEDED')\n"
        )

        inv_id = uuid.uuid4()
        prop_id = uuid.uuid4()
        evidence_id = uuid.uuid4()

        proposal = FixProposal(
            proposal_id=prop_id,
            investigation_id=inv_id,
            execution_id=uuid.uuid4(),
            root_cause_reference=uuid.uuid4(),
            status=FixProposalStatus.REQUIRES_HUMAN_REVIEW,
            summary="Update VALUE to 2",
            rationale="Test proposal for live Docker sandbox verification",
            affected_components=["target"],
            change_type="code_change",
            changes=[
                FixChange(
                    target="target.py",
                    target_path="target.py",
                    operation="modify",
                    current_state="VALUE = 1\n",
                    proposed_state="VALUE = 2\n",
                    reason="Fix target value",
                    evidence_references=[evidence_id],
                )
            ],
            prerequisites=[],
            risks=[
                FixRisk(
                    category=FixRiskCategory.PERFORMANCE,
                    severity=FixRiskSeverity.LOW,
                    description="None",
                    mitigation="None",
                )
            ],
            verification_plan=[
                FixVerificationStep(
                    description="Run target test",
                    expected_result="VERIFICATION_SUCCEEDED",
                    evidence_required=["test_target.py"],
                )
            ],
            rollback_plan=[
                FixRollbackStep(
                    description="Revert target.py",
                    trigger="Test failure",
                    expected_result="VALUE restored to 1",
                )
            ],
            evidence_references=[evidence_id],
            external_knowledge_references=[],
            confidence=0.95,
            change_scope="backend",
            generated_at=datetime.now(UTC),
            model_metadata=LLMObservability(
                provider="mock",
                model="mock",
                attempts=1,
                duration_ms=10.0,
                input_tokens=100,
                output_tokens=50,
                estimated_cost_usd=0.001,
                budget_remaining_usd=1.999,
            ),
        )

        commands = [
            VerificationCommand(
                step_index=0,
                argv=["python", "test_target.py"],
                timeout_seconds=10,
            )
        ]

        result = await service.verify(
            proposal,
            workspace_path=source_dir,
            commands=commands,
        )

        assert result.status == VerificationStatus.PASSED
        assert len(result.verification_steps) == 1
        assert result.verification_steps[0].status == VerificationStepStatus.PASSED
        assert "VERIFICATION_SUCCEEDED" in result.verification_steps[0].observed_result
        assert result.cleanup_status == "complete"

