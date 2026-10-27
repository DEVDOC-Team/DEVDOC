"""Docker-backed sandbox provider with no host mounts or inherited environment."""

from __future__ import annotations

import asyncio
import io
import json
import re
import tarfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import gettempdir

from orchestrator.sandbox.models import (
    SandboxExecution,
    SandboxHandle,
    SandboxLimits,
    SandboxProviderError,
    SandboxTimeoutError,
    VerificationCommand,
)

_PINNED_IMAGE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/:+-]{0,254}@sha256:[0-9a-f]{64}$")
_SENSITIVE_ENV_KEY = re.compile(r"(?i)(token|password|secret|api[_-]?key|access[_-]?key|private[_-]?key|credential|auth)")

DEFAULT_PINNED_SANDBOX_IMAGE = (
    "python:3.13-alpine@sha256:bf12ecc0bea3f171d55145dd02c78b5eeb09f30ee2ac9cc2b4c9e4e8f5e30741"
)


def is_docker_available(
    image: str = DEFAULT_PINNED_SANDBOX_IMAGE, executable: str = "docker"
) -> bool:
    """Check if the Docker daemon is reachable and the pinned sandbox image is cached locally."""
    import shutil
    import subprocess

    if not shutil.which(executable):
        return False
    try:
        info_res = subprocess.run(
            [executable, "info"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        if info_res.returncode != 0:
            return False
        img_res = subprocess.run(
            [executable, "image", "inspect", image],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        return img_res.returncode == 0
    except Exception:
        return False


def create_default_docker_sandbox_provider(
    image: str = DEFAULT_PINNED_SANDBOX_IMAGE,
    executable: str = "docker",
) -> DockerSandboxProvider | None:
    """Instantiate DockerSandboxProvider if the Docker daemon and pinned image are available."""
    if is_docker_available(image=image, executable=executable):
        return DockerSandboxProvider(image=image, executable=executable)
    return None



class DockerSandboxError(SandboxProviderError):
    """A Docker operation failed; output is bounded and credential-free."""


class SandboxCommandTimeout(SandboxTimeoutError):
    """A command inside the sandbox exceeded its deadline."""


@dataclass(frozen=True)
class _CommandOutput:
    returncode: int
    stdout: str
    stderr: str
    truncated: bool


class DockerSandboxProvider:
    """Runs disposable sandboxes from an explicitly pinned, pre-pulled image."""

    def __init__(self, image: str, executable: str = "docker") -> None:
        if not _PINNED_IMAGE.fullmatch(image):
            raise ValueError("Sandbox image must be pinned by a sha256 digest")
        if not executable or Path(executable).name != executable:
            raise ValueError("Docker executable must be a command name")
        self.image = image
        self.executable = executable

    async def create(
        self,
        sandbox_id: str,
        workspace_path: str,
        limits: SandboxLimits,
    ) -> SandboxHandle:
        if not re.fullmatch(r"[0-9a-f-]{36}", sandbox_id):
            raise ValueError("Sandbox ID must be a UUID")
        source = Path(workspace_path).resolve(strict=True)
        temp_root = Path(gettempdir()).resolve()
        if not source.is_dir() or not source.is_relative_to(temp_root):
            raise ValueError("Sandbox workspace must be inside the system temporary directory")
        image_env = await self._run(
            ["image", "inspect", "--format", "{{json .Config.Env}}", self.image],
            timeout=15,
            output_limit=16_384,
        )
        if image_env.returncode or image_env.truncated:
            raise DockerSandboxError("Pinned sandbox image is unavailable locally")
        try:
            image_variables = json.loads(image_env.stdout)
        except json.JSONDecodeError as exc:
            raise DockerSandboxError("Sandbox image environment metadata is invalid") from exc
        if image_variables is None:
            image_variables = []
        if not isinstance(image_variables, list) or any(
            not isinstance(variable, str) or "=" not in variable for variable in image_variables
        ):
            raise DockerSandboxError("Sandbox image environment metadata is invalid")
        if any(_SENSITIVE_ENV_KEY.search(variable.split("=", 1)[0]) for variable in image_variables):
            raise DockerSandboxError("Sandbox image contains a credential-like environment variable")
        image_volumes = await self._run(
            ["image", "inspect", "--format", "{{json .Config.Volumes}}", self.image],
            timeout=15,
            output_limit=4096,
        )
        if image_volumes.returncode or image_volumes.truncated:
            raise DockerSandboxError("Pinned sandbox image volume metadata could not be inspected")
        try:
            declared_volumes = json.loads(image_volumes.stdout or "null")
        except json.JSONDecodeError as exc:
            raise DockerSandboxError("Sandbox image volume metadata is invalid") from exc
        if declared_volumes:
            raise DockerSandboxError("Sandbox images declaring persistent volumes are not allowed")

        name = f"devdoc-sandbox-{sandbox_id}"
        create_args = [
            "create",
            "--name",
            name,
            "--label",
            "devdoc.managed=true",
            "--label",
            f"devdoc.created_at={datetime.now(UTC).isoformat()}",
            "--network",
            "none",
            "--memory",
            f"{limits.memory_mb}m",
            "--cpus",
            str(limits.cpu_count),
            "--pids-limit",
            str(limits.process_limit),
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges:true",
            "--user",
            "65532:65532",
            "--env",
            "HOME=/tmp",
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,noexec,uid=65532,gid=65532,mode=1777,size=32m",
            "--tmpfs",
            (
                f"/workspace:rw,nosuid,nodev,uid=65532,gid=65532,mode=0700,"
                f"size={limits.workspace_mb}m"
            ),
            "--workdir",
            "/workspace",
            "--entrypoint",
            "sleep",
            self.image,
            "infinity",
        ]
        created = await self._run(create_args, timeout=20, output_limit=4096)
        container_id = created.stdout.strip()
        if created.returncode or not re.fullmatch(r"[0-9a-f]{12,64}", container_id):
            raise DockerSandboxError("Docker could not create the isolated sandbox")
        handle = SandboxHandle(sandbox_id=container_id)
        try:
            started = await self._run(["start", container_id], timeout=20, output_limit=4096)
            if started.returncode:
                raise DockerSandboxError("Docker could not start the isolated sandbox")
            tar_stream = io.BytesIO()
            with tarfile.open(fileobj=tar_stream, mode="w") as tar:
                for item in source.iterdir():
                    tar.add(item, arcname=item.name)
            tar_bytes = tar_stream.getvalue()

            copied = await self._run(
                ["exec", "-i", container_id, "tar", "-C", "/workspace", "-xf", "-"],
                input_bytes=tar_bytes,
                timeout=60,
                output_limit=4096,
            )
            if copied.returncode:
                raise DockerSandboxError(
                    f"Docker could not extract workspace into container: {copied.stderr.strip()[:200]}"
                )
        except SandboxProviderError:
            await self.cleanup(handle)
            raise
        except OSError:
            await self.cleanup(handle)
            raise
        except asyncio.CancelledError:
            await asyncio.shield(self.cleanup(handle))
            raise
        return handle

    async def execute(
        self,
        handle: SandboxHandle,
        command: VerificationCommand,
        limits: SandboxLimits,
    ) -> SandboxExecution:
        started = asyncio.get_running_loop().time()
        result = await self._run(
            ["exec", handle.sandbox_id, *command.argv],
            timeout=min(command.timeout_seconds, limits.execution_timeout_seconds),
            output_limit=limits.output_bytes,
        )
        return SandboxExecution(
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            duration_ms=(asyncio.get_running_loop().time() - started) * 1000,
            output_truncated=result.truncated,
        )

    async def cleanup(self, handle: SandboxHandle) -> None:
        if not re.fullmatch(r"[0-9a-f]{12,64}", handle.sandbox_id):
            raise ValueError("Invalid Docker container identifier")
        removed = await self._run(
            ["rm", "--force", "--volumes", handle.sandbox_id],
            timeout=30,
            output_limit=4096,
        )
        if removed.returncode and "no such container" not in removed.stderr.lower():
            raise DockerSandboxError("Docker could not remove the sandbox container")

    async def cleanup_orphans(self, max_age_seconds: int = 3600) -> int:
        """Remove only stale containers carrying this provider's ownership label."""
        if max_age_seconds < 60:
            raise ValueError("Orphan cleanup age must be at least 60 seconds")
        listed = await self._run(
            ["ps", "--all", "--quiet", "--filter", "label=devdoc.managed=true"],
            timeout=20,
            output_limit=16_384,
        )
        if listed.returncode:
            raise DockerSandboxError("Docker could not list managed sandbox containers")
        if listed.truncated:
            raise DockerSandboxError("Docker's managed-container list exceeded its output limit")
        cutoff = datetime.now(UTC) - timedelta(seconds=max_age_seconds)
        removed_count = 0
        for container_id in listed.stdout.splitlines():
            if not re.fullmatch(r"[0-9a-f]{12,64}", container_id):
                raise DockerSandboxError("Docker returned an invalid container identifier")
            inspected = await self._run(
                ["inspect", "--format", "{{.Created}}", container_id],
                timeout=15,
                output_limit=4096,
            )
            if inspected.returncode:
                raise DockerSandboxError("Docker could not inspect a managed sandbox")
            created = datetime.fromisoformat(inspected.stdout.strip().replace("Z", "+00:00"))
            if created.tzinfo is None:
                created = created.replace(tzinfo=UTC)
            if created < cutoff:
                await self.cleanup(SandboxHandle(sandbox_id=container_id))
                removed_count += 1
        return removed_count

    async def _run(
        self,
        args: list[str],
        *,
        timeout: int,
        output_limit: int,
        input_bytes: bytes | None = None,
    ) -> _CommandOutput:
        try:
            process = await asyncio.create_subprocess_exec(
                self.executable,
                *args,
                stdin=asyncio.subprocess.PIPE if input_bytes is not None else asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as exc:
            raise DockerSandboxError("Docker CLI could not be started") from exc

        stdin_task = None
        if input_bytes is not None and process.stdin is not None:
            async def _write_stdin() -> None:
                try:
                    process.stdin.write(input_bytes)
                    await process.stdin.drain()
                except (BrokenPipeError, ConnectionResetError):
                    pass
                finally:
                    process.stdin.close()
            stdin_task = asyncio.create_task(_write_stdin())

        async def collect(stream: asyncio.StreamReader) -> tuple[bytes, bool]:
            output = bytearray()
            truncated = False
            while chunk := await stream.read(64 * 1024):
                remaining = output_limit - len(output)
                if remaining > 0:
                    output.extend(chunk[:remaining])
                if len(chunk) > remaining:
                    truncated = True
            return bytes(output), truncated

        assert process.stdout is not None
        assert process.stderr is not None
        stdout_task = asyncio.create_task(collect(process.stdout))
        stderr_task = asyncio.create_task(collect(process.stderr))
        try:
            await asyncio.wait_for(process.wait(), timeout=timeout)
            if stdin_task is not None:
                await stdin_task
            (stdout, stdout_truncated), (stderr, stderr_truncated) = await asyncio.gather(
                stdout_task,
                stderr_task,
            )
        except TimeoutError as exc:
            process.kill()
            await process.wait()
            if stdin_task is not None:
                await asyncio.gather(stdin_task, return_exceptions=True)
            await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
            raise SandboxCommandTimeout("Docker operation exceeded its time limit") from exc
        except asyncio.CancelledError:
            process.kill()
            await process.wait()
            if stdin_task is not None:
                await asyncio.gather(stdin_task, return_exceptions=True)
            await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
            raise
        marker = "\nOUTPUT_TRUNCATED"
        return _CommandOutput(
            returncode=process.returncode or 0,
            stdout=stdout.decode("utf-8", errors="replace")
            + (marker if stdout_truncated else ""),
            stderr=stderr.decode("utf-8", errors="replace")
            + (marker if stderr_truncated else ""),
            truncated=stdout_truncated or stderr_truncated,
        )
