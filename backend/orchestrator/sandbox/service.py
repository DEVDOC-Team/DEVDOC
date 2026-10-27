"""Bounded orchestration of proposal application, verification, and cleanup."""

from __future__ import annotations

import asyncio
import tempfile
import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

from orchestrator.fixes.models import FixProposal
from orchestrator.sandbox.contracts import SandboxProvider
from orchestrator.sandbox.models import (
    SandboxExecution,
    SandboxHandle,
    SandboxLimits,
    SandboxProviderError,
    SandboxTimeoutError,
    SandboxVerificationResult,
    VerificationCommand,
    VerificationStatus,
    VerificationStepResult,
    VerificationStepStatus,
)
from orchestrator.sandbox.security import (
    PatchApplicationError,
    SandboxPreparationCancelled,
    UnsafeSandboxInput,
    apply_fix_change,
    prepare_workspace,
)


async def _execute_until_cancelled(
    provider: SandboxProvider,
    handle: SandboxHandle,
    command: VerificationCommand,
    limits: SandboxLimits,
    is_cancelled: Callable[[], bool],
) -> SandboxExecution | None:
    task = asyncio.create_task(
        provider.execute(
            handle,
            command,
            limits,
        )
    )
    try:
        while True:
            done, _ = await asyncio.wait({task}, timeout=0.1)
            if done:
                return task.result()
            if is_cancelled():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                return None
    except asyncio.CancelledError:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        raise


class SandboxVerificationService:
    def __init__(
        self,
        provider: SandboxProvider,
        *,
        limits: SandboxLimits | None = None,
    ) -> None:
        self.provider = provider
        self.limits = limits or SandboxLimits()

    async def verify(
        self,
        proposal: FixProposal,
        *,
        workspace_path: str | Path | None,
        commands: Sequence[VerificationCommand],
        is_cancelled: Callable[[], bool] | None = None,
    ) -> SandboxVerificationResult:
        started_at = datetime.now(UTC)
        verification_id = uuid.uuid4()
        sandbox_id = str(uuid.uuid4())
        steps: list[VerificationStepResult] = []
        applied_changes: list[str] = []
        risks: list[str] = []
        logs = ""
        handle = None
        cleanup_status = "not_started"
        status = VerificationStatus.INCONCLUSIVE
        summary = "Verification prerequisites are incomplete"

        def cancelled() -> bool:
            return is_cancelled is not None and is_cancelled()

        if proposal.investigation_id.int == 0:
            risks.append("INVALID_INVESTIGATION_ID")
            status = VerificationStatus.UNSAFE
            summary = "FixProposal is missing a valid investigation identifier"
        elif workspace_path is None:
            risks.append("SOURCE_WORKSPACE_UNAVAILABLE")
            summary = "No authorized source workspace was provided"
        elif not commands or len(commands) != len(proposal.verification_plan):
            risks.append("VERIFICATION_COMMANDS_INCOMPLETE")
            summary = "Trusted commands must map one-to-one to proposal verification criteria"
        elif [command.step_index for command in commands] != list(range(len(commands))):
            risks.append("VERIFICATION_COMMAND_ORDER_INVALID")
            status = VerificationStatus.UNSAFE
            summary = "Verification commands are not mapped to criteria in order"
        elif cancelled():
            status = VerificationStatus.CANCELLED
            summary = "Verification was cancelled before setup"
        else:
            try:
                with tempfile.TemporaryDirectory(prefix="devdoc-sandbox-") as temporary:
                    workspace = Path(temporary) / "workspace"
                    workspace.mkdir()
                    await asyncio.to_thread(
                        prepare_workspace,
                        workspace_path,
                        workspace,
                        self.limits.workspace_mb * 1024 * 1024,
                        self.limits.workspace_files,
                        cancelled,
                    )
                    for change in proposal.changes:
                        applied_changes.append(
                            await asyncio.to_thread(apply_fix_change, workspace, change)
                        )
                    if cancelled():
                        status = VerificationStatus.CANCELLED
                        summary = "Verification was cancelled before sandbox creation"
                    else:
                        handle = await self.provider.create(
                            sandbox_id,
                            str(workspace),
                            self.limits,
                        )
                        cleanup_status = "failed"
                        status = VerificationStatus.PASSED
                        log_remaining = self.limits.log_bytes
                        for index, (criterion, command) in enumerate(
                            zip(proposal.verification_plan, commands, strict=True)
                        ):
                            if cancelled():
                                status = VerificationStatus.CANCELLED
                                summary = "Verification was cancelled"
                                break
                            started = asyncio.get_running_loop().time()
                            try:
                                execution = await _execute_until_cancelled(
                                    self.provider,
                                    handle,
                                    command,
                                    self.limits,
                                    cancelled,
                                )
                                if execution is None:
                                    status = VerificationStatus.CANCELLED
                                    summary = "Verification was cancelled"
                                    break
                            except SandboxTimeoutError:
                                steps.append(
                                    VerificationStepResult(
                                        step_id=f"step-{index + 1}",
                                        description=criterion.description,
                                        status=VerificationStepStatus.TIMEOUT,
                                        duration_ms=(
                                            asyncio.get_running_loop().time() - started
                                        )
                                        * 1000,
                                        expected_result=criterion.expected_result,
                                        observed_result="Execution deadline exceeded",
                                        failure_analysis=(
                                            "Verification was inconclusive because the step timed out."
                                        ),
                                        warnings=["EXECUTION_TIMEOUT"],
                                    )
                                )
                                status = VerificationStatus.TIMEOUT
                                summary = "A verification step exceeded its time limit"
                                break
                            except SandboxProviderError:
                                risks.append("SANDBOX_STEP_EXECUTION_FAILED")
                                status = VerificationStatus.SETUP_FAILED
                                summary = "The sandbox provider could not execute a verification step"
                                break

                            stdout = execution.stdout
                            stderr = execution.stderr
                            combined = f"{stdout}\n{stderr}"
                            truncated = execution.output_truncated
                            if len(combined.encode("utf-8")) > log_remaining:
                                encoded = combined.encode("utf-8")[:log_remaining]
                                combined = encoded.decode("utf-8", errors="ignore")
                                truncated = True
                            log_remaining = max(0, log_remaining - len(combined.encode("utf-8")))
                            if truncated:
                                risks.append("OUTPUT_TRUNCATED")
                            logs += combined
                            expected_seen = (
                                criterion.expected_result.casefold()
                                in f"{stdout}\n{stderr}".casefold()
                            )
                            if execution.exit_code != 0:
                                step_status = VerificationStepStatus.FAILED
                                status = VerificationStatus.FAILED
                            elif expected_seen:
                                step_status = VerificationStepStatus.PASSED
                            else:
                                step_status = VerificationStepStatus.INCONCLUSIVE
                                status = VerificationStatus.INCONCLUSIVE
                            steps.append(
                                VerificationStepResult(
                                    step_id=f"step-{index + 1}",
                                    description=criterion.description,
                                    status=step_status,
                                    exit_code=execution.exit_code,
                                    duration_ms=execution.duration_ms,
                                    stdout=stdout[: self.limits.output_bytes],
                                    stderr=stderr[: self.limits.output_bytes],
                                    expected_result=criterion.expected_result,
                                    observed_result=combined[:4096],
                                    failure_analysis=(
                                        "The command exited non-zero; causal relation to the "
                                        "proposed fix is not inferred."
                                        if execution.exit_code != 0
                                        else None
                                    ),
                                    warnings=["OUTPUT_TRUNCATED"] if truncated else [],
                                )
                            )
                            if status == VerificationStatus.FAILED:
                                summary = f"Verification failed at step {index + 1}"
                                break
                            if status == VerificationStatus.INCONCLUSIVE:
                                summary = (
                                    f"Expected result was not observable at step {index + 1}"
                                )
                                break
                        if status == VerificationStatus.PASSED:
                            summary = "All required verification results were observed"
            except SandboxPreparationCancelled:
                status = VerificationStatus.CANCELLED
                summary = "Verification was cancelled while preparing its workspace"
            except PatchApplicationError:
                risks.append("PATCH_APPLICATION_FAILED")
                status = VerificationStatus.FAILED
                summary = "The proposed patch could not be applied exactly in the workspace"
            except UnsafeSandboxInput as exc:
                risks.append(str(exc)[:512])
                status = VerificationStatus.UNSAFE
                summary = "The proposal or source workspace violates sandbox safety rules"
            except (OSError, ValueError) as exc:
                risks.append(f"WORKSPACE_PREPARATION_FAILED: {type(exc).__name__}")
                status = VerificationStatus.SETUP_FAILED
                summary = "The isolated verification workspace could not be prepared"
            except TimeoutError:
                status = VerificationStatus.SETUP_FAILED
                risks.append("SANDBOX_SETUP_TIMEOUT")
                summary = "Sandbox setup exceeded its time limit"
            except asyncio.CancelledError:
                status = VerificationStatus.CANCELLED
                summary = "Verification was cancelled"
            except SandboxProviderError:
                status = VerificationStatus.SETUP_FAILED
                risks.append("SANDBOX_SETUP_FAILED")
                summary = "Sandbox setup failed"
            finally:
                if handle is not None:
                    try:
                        await asyncio.shield(self.provider.cleanup(handle))
                    except SandboxProviderError:
                        cleanup_status = "failed"
                        risks.append("SANDBOX_CLEANUP_FAILED")
                        if status in {VerificationStatus.PASSED, VerificationStatus.INCONCLUSIVE}:
                            status = VerificationStatus.SETUP_FAILED
                            summary = "Sandbox cleanup failed"
                    else:
                        cleanup_status = "complete"

        completed_at = datetime.now(UTC)
        return SandboxVerificationResult(
            verification_id=verification_id,
            investigation_id=proposal.investigation_id,
            proposal_id=proposal.proposal_id,
            status=status,
            sandbox_id=handle.sandbox_id if handle is not None else None,
            started_at=started_at,
            completed_at=completed_at,
            applied_changes=applied_changes,
            verification_steps=steps,
            passed_steps=sum(step.status == VerificationStepStatus.PASSED for step in steps),
            failed_steps=sum(step.status == VerificationStepStatus.FAILED for step in steps),
            logs=logs,
            risk_findings=list(dict.fromkeys(risks)),
            cleanup_status=cleanup_status,
            summary=summary,
        )
