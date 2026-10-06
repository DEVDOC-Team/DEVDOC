"""Filesystem and command validation for sandbox workspaces."""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from pathlib import Path, PurePosixPath, PureWindowsPath

from orchestrator.fixes.models import FixChange

_IGNORED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".aws",
    ".azure",
    ".config",
    ".docker",
    ".gnupg",
    ".kube",
    ".ssh",
    ".terraform",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "dist",
    "build",
}
_SENSITIVE_NAMES = {
    "credentials",
    "id_rsa",
    "id_ed25519",
    "id_ecdsa",
    "id_dsa",
    "authorized_keys",
    "known_hosts",
    "docker.sock",
    "credentials.json",
    "service-account.json",
    ".netrc",
    ".npmrc",
    ".pypirc",
    ".envrc",
    ".vault-token",
}
_SENSITIVE_SUFFIXES = {".pem", ".key", ".p12", ".pfx"}
_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


class UnsafeSandboxInput(ValueError):
    """Raised when a workspace or proposed change crosses the sandbox boundary."""


class PatchApplicationError(ValueError):
    """A bounded unified patch could not be applied exactly as proposed."""


class SandboxPreparationCancelled(RuntimeError):
    """Workspace preparation was stopped by the caller's cancellation token."""


def _is_sensitive_name(name: str) -> bool:
    lowered = name.lower()
    return (
        lowered in _SENSITIVE_NAMES
        or lowered == ".env"
        or lowered.startswith(".env.")
        or Path(lowered).suffix in _SENSITIVE_SUFFIXES
    )


def prepare_workspace(
    source: str | Path,
    destination: str | Path,
    max_bytes: int,
    max_files: int = 10_000,
    is_cancelled: Callable[[], bool] | None = None,
) -> int:
    """Copy regular repository files to a disposable workspace, excluding secrets."""
    source_root = Path(source).resolve(strict=True)
    if not source_root.is_dir():
        raise UnsafeSandboxInput("Verification source must be a directory")
    destination_root = Path(destination).resolve()
    total_bytes = 0
    copied_files = 0

    for current, dirnames, filenames in os.walk(source_root, topdown=True, followlinks=False):
        if is_cancelled is not None and is_cancelled():
            raise SandboxPreparationCancelled("Workspace preparation cancelled")
        current_path = Path(current)
        relative = current_path.relative_to(source_root)
        filtered_dirs = []
        for name in dirnames:
            child = current_path / name
            if name in _IGNORED_DIRS or _is_sensitive_name(name):
                continue
            if child.is_symlink():
                continue
            filtered_dirs.append(name)
        dirnames[:] = filtered_dirs
        copied_files += len(filtered_dirs)
        if copied_files > max_files:
            raise UnsafeSandboxInput("Workspace exceeds configured entry-count limit")
        target_dir = destination_root / relative
        target_dir.mkdir(parents=True, exist_ok=True)

        for name in filenames:
            source_file = current_path / name
            if _is_sensitive_name(name) or source_file.is_symlink():
                continue
            resolved_file = source_file.resolve(strict=True)
            if not resolved_file.is_relative_to(source_root):
                continue
            if not resolved_file.is_file():
                continue
            copied_files += 1
            if copied_files > max_files:
                raise UnsafeSandboxInput("Workspace exceeds configured file-count limit")
            target_file = target_dir / name
            target_file.parent.mkdir(parents=True, exist_ok=True)
            with resolved_file.open("rb") as reader, target_file.open("wb") as writer:
                while chunk := reader.read(64 * 1024):
                    if is_cancelled is not None and is_cancelled():
                        raise SandboxPreparationCancelled("Workspace preparation cancelled")
                    total_bytes += len(chunk)
                    if total_bytes > max_bytes:
                        raise UnsafeSandboxInput("Workspace exceeds configured disk limit")
                    writer.write(chunk)
    return total_bytes


def normalize_workspace_path(workspace: Path, raw_path: str) -> Path:
    """Resolve a proposal target without allowing traversal or sensitive files."""
    if not raw_path or "\x00" in raw_path:
        raise UnsafeSandboxInput("Change target path is empty or invalid")
    windows_path = PureWindowsPath(raw_path)
    posix_path = PurePosixPath(raw_path.replace("\\", "/"))
    if windows_path.is_absolute() or windows_path.drive or posix_path.is_absolute():
        raise UnsafeSandboxInput("Absolute paths are not allowed in a proposed change")
    if any(part in {"", ".", ".."} for part in posix_path.parts):
        raise UnsafeSandboxInput("Path traversal is not allowed in a proposed change")
    if any(_is_sensitive_name(part) for part in posix_path.parts):
        raise UnsafeSandboxInput("Changes to credential and environment files are forbidden")
    target = workspace.joinpath(*posix_path.parts)
    resolved = target.resolve(strict=False)
    if not resolved.is_relative_to(workspace.resolve()):
        raise UnsafeSandboxInput("Proposed change escapes the sandbox workspace")
    parent = target.parent
    while parent != workspace and parent != parent.parent:
        if parent.is_symlink():
            raise UnsafeSandboxInput("Symlink targets are not allowed in proposed changes")
        parent = parent.parent
    if target.is_symlink():
        raise UnsafeSandboxInput("Symlink targets are not allowed in proposed changes")
    return target


def apply_fix_change(workspace: Path, change: FixChange, max_patch_bytes: int = 1_000_000) -> str:
    """Apply a Phase 16 data-only change inside a disposable workspace."""
    if change.target_path is None:
        raise UnsafeSandboxInput("FixProposal change must include a validated target_path")
    target = normalize_workspace_path(workspace, change.target_path)
    if change.proposed_diff is not None:
        if len(change.proposed_diff.encode("utf-8")) > max_patch_bytes:
            raise UnsafeSandboxInput("Proposed patch exceeds configured size limit")
        _apply_unified_diff(target, change.proposed_diff)
    elif change.proposed_state is not None:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(change.proposed_state, encoding="utf-8")
    else:
        raise UnsafeSandboxInput("FixProposal change has no supported patch or proposed state")
    return target.relative_to(workspace).as_posix()


def _apply_unified_diff(target: Path, patch: str) -> None:
    lines = patch.splitlines(keepends=True)
    if any(line.startswith(("GIT binary patch", "Binary files ")) for line in lines):
        raise PatchApplicationError("Binary patches are not supported")
    header_old: str | None = None
    header_new: str | None = None
    hunks: list[tuple[int, int, list[str]]] = []
    active_hunk: list[str] | None = None
    old_start = 0
    old_count = 0
    new_count = 0
    consumed_old = 0
    consumed_new = 0
    for line in lines:
        if line.startswith("--- "):
            if header_old is not None:
                raise PatchApplicationError("Multi-file patches are not supported")
            header_old = line[4:].strip().split("\t", 1)[0]
        elif line.startswith("+++ "):
            header_new = line[4:].strip().split("\t", 1)[0]
        elif line.startswith("@@ "):
            if active_hunk is not None:
                if consumed_old != old_count or consumed_new != new_count:
                    raise PatchApplicationError("Patch hunk line count is invalid")
                hunks.append((old_start, old_count, active_hunk))
            match = _HUNK.match(line.rstrip("\r\n"))
            if match is None:
                raise PatchApplicationError("Malformed unified patch hunk")
            old_start = int(match.group(1))
            old_count = int(match.group(2) or "1")
            new_count = int(match.group(4) or "1")
            active_hunk = []
            consumed_old = 0
            consumed_new = 0
        elif active_hunk is not None:
            if line.startswith("\\ No newline"):
                continue
            if not line or line[0] not in " +-":
                raise PatchApplicationError("Malformed unified patch line")
            active_hunk.append(line)
            if line[0] in " -":
                consumed_old += 1
            if line[0] in " +":
                consumed_new += 1
    if active_hunk is not None:
        if consumed_old != old_count or consumed_new != new_count:
            raise PatchApplicationError("Patch hunk line count is invalid")
        hunks.append((old_start, old_count, active_hunk))
    if header_new is None or not hunks:
        raise PatchApplicationError("Patch must contain one file header and at least one hunk")

    def strip_prefix(path: str) -> str:
        if path == "/dev/null":
            return path
        return path[2:] if path.startswith(("a/", "b/")) else path

    if header_old is None:
        raise PatchApplicationError("Patch is missing its old-file header")
    old_path = strip_prefix(header_old)
    new_path = strip_prefix(header_new)
    target_name = target.as_posix()
    # Header paths are relative to the workspace, as required by the FixChange target.
    if new_path != target_name and not target_name.endswith(f"/{new_path}"):
        raise PatchApplicationError("Patch target does not match FixProposal target_path")
    if old_path != "/dev/null" and old_path != new_path:
        raise PatchApplicationError("File renames and cross-file patches are not supported")
    original = target.read_text(encoding="utf-8").splitlines(keepends=True) if target.exists() else []
    if old_path != "/dev/null" and not target.is_file():
        raise PatchApplicationError("Patch target does not exist in the sandbox workspace")
    output: list[str] = []
    cursor = 0
    for start, _count, hunk_lines in hunks:
        hunk_index = max(start - 1, 0)
        if hunk_index < cursor or hunk_index > len(original):
            raise PatchApplicationError("Patch hunk is outside the target file")
        output.extend(original[cursor:hunk_index])
        cursor = hunk_index
        for line in hunk_lines:
            prefix, content = line[0], line[1:]
            if prefix == " ":
                if cursor >= len(original) or original[cursor].rstrip("\r\n") != content.rstrip("\r\n"):
                    raise PatchApplicationError("Patch context does not match target file")
                output.append(original[cursor])
                cursor += 1
            elif prefix == "-":
                if cursor >= len(original) or original[cursor].rstrip("\r\n") != content.rstrip("\r\n"):
                    raise PatchApplicationError("Patch removal does not match target file")
                cursor += 1
            else:
                output.append(content)
    output.extend(original[cursor:])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("".join(output), encoding="utf-8")
