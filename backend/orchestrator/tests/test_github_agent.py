"""Tests for GitHubAgent."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.core.github_client import (
    GitHubAPIClient,
    GitHubAPIError,
    GitHubAuthenticationError,
    GitHubNotFoundError,
    GitHubPermissionError,
    GitHubRateLimitError,
    GitHubTimeoutError,
)
from orchestrator.agents.github_agent import GitHubAgent
from orchestrator.core.context import InvestigationContext
from orchestrator.core.result import ExecutionStatus


class FakeGitHubClient(GitHubAPIClient):
    """Deterministic in-memory fake client for testing GitHubAgent without network calls."""

    def __init__(
        self,
        repo_data: dict[str, Any] | None = None,
        branches: list[dict[str, Any]] | None = None,
        commits: list[dict[str, Any]] | None = None,
        pull_requests: list[dict[str, Any]] | None = None,
        issues: list[dict[str, Any]] | None = None,
        workflows: dict[str, Any] | None = None,
        files: dict[str, dict[str, Any]] | None = None,
        should_fail: Exception | None = None,
    ) -> None:
        super().__init__(access_token="test_token")
        self.repo_data = repo_data or {
            "name": "devdoc",
            "full_name": "DEVDOC-Team/devdoc",
            "private": True,
            "default_branch": "main",
            "description": "AI investigation platform",
            "language": "Python",
            "open_issues_count": 5,
            "updated_at": "2026-10-02T12:00:00Z",
        }
        self.branches = branches or [
            {"name": "main", "commit": {"sha": "sha_main_123"}},
            {"name": "features", "commit": {"sha": "sha_feat_456"}},
        ]
        self.commits = commits or [
            {
                "sha": "c1a2b3c",
                "commit": {
                    "message": "fix: resolve memory leak in worker\n\nDetailed explanation",
                    "author": {"name": "Alice Developer", "date": "2026-10-02T11:00:00Z"},
                },
            }
        ]
        self.pull_requests = pull_requests or [
            {
                "number": 42,
                "title": "Feature: Phase 11 Agents",
                "state": "open",
                "user": {"login": "alice"},
                "created_at": "2026-10-02T10:00:00Z",
                "merged_at": None,
            }
        ]
        self.issues = issues or [
            {
                "number": 10,
                "title": "Bug: Service 502 error during deployment",
                "state": "open",
                "user": {"login": "bob"},
                "created_at": "2026-10-02T09:00:00Z",
            }
        ]
        self.workflows = workflows or {
            "workflow_runs": [
                {
                    "id": 9991,
                    "name": "CI",
                    "status": "completed",
                    "conclusion": "success",
                    "event": "push",
                    "created_at": "2026-10-02T11:30:00Z",
                }
            ]
        }
        self.files = files or {
            "Dockerfile": {"path": "Dockerfile", "size": 1552, "sha": "f123", "encoding": "base64"}
        }
        self.should_fail = should_fail

    async def get_repository(self, owner: str, repo: str) -> dict[str, Any]:
        if self.should_fail:
            raise self.should_fail
        return self.repo_data

    async def list_branches(self, owner: str, repo: str, page: int = 1, per_page: int = 30) -> list[dict[str, Any]]:
        if self.should_fail:
            raise self.should_fail
        return self.branches

    async def list_commits(
        self, owner: str, repo: str, sha: str | None = None, page: int = 1, per_page: int = 30
    ) -> list[dict[str, Any]]:
        if self.should_fail:
            raise self.should_fail
        return self.commits

    async def list_pull_requests(
        self, owner: str, repo: str, state: str = "open", page: int = 1, per_page: int = 30
    ) -> list[dict[str, Any]]:
        if self.should_fail:
            raise self.should_fail
        return self.pull_requests

    async def list_issues(
        self, owner: str, repo: str, state: str = "open", page: int = 1, per_page: int = 30
    ) -> list[dict[str, Any]]:
        if self.should_fail:
            raise self.should_fail
        return self.issues

    async def list_workflow_runs(
        self, owner: str, repo: str, page: int = 1, per_page: int = 30
    ) -> dict[str, Any]:
        if self.should_fail:
            raise self.should_fail
        return self.workflows

    async def get_file_contents(
        self, owner: str, repo: str, path: str, ref: str | None = None
    ) -> dict[str, Any]:
        if self.should_fail:
            raise self.should_fail
        if path in self.files:
            return self.files[path]
        raise GitHubNotFoundError(f"File '{path}' not found")


@pytest.fixture
def base_context() -> InvestigationContext:
    return InvestigationContext(
        investigation_id=uuid.uuid4(),
        incident_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        execution_metadata={"github_repo": "DEVDOC-Team/devdoc"},
    )


@pytest.mark.asyncio
async def test_github_agent_success(base_context: InvestigationContext) -> None:
    client = FakeGitHubClient()
    agent = GitHubAgent(client=client)

    result = await agent.execute(base_context)

    assert result.status == ExecutionStatus.SUCCESS
    assert result.is_successful
    assert result.source == "github"
    assert result.investigation_id == base_context.investigation_id
    assert result.execution_id == base_context.execution_id
    assert result.data["repository"]["name"] == "devdoc"
    assert len(result.data["branches"]) == 2
    assert len(result.data["commits"]) == 1
    assert len(result.data["pull_requests"]) == 1
    assert len(result.data["issues"]) == 1
    assert len(result.data["workflow_runs"]) == 1
    assert result.output_metadata["commit_count"] == 1
    assert base_context.agent_outputs["github_agent"]["commit_count"] == 1


@pytest.mark.asyncio
async def test_github_agent_file_inspection(base_context: InvestigationContext) -> None:
    base_context.execution_metadata["github_file_paths"] = ["Dockerfile"]
    client = FakeGitHubClient()
    agent = GitHubAgent(client=client)

    result = await agent.execute(base_context)

    assert result.status == ExecutionStatus.SUCCESS
    assert "files" in result.data
    assert "Dockerfile" in result.data["files"]
    assert result.data["files"]["Dockerfile"]["path"] == "Dockerfile"


@pytest.mark.asyncio
async def test_github_agent_skipped_when_no_repo(base_context: InvestigationContext) -> None:
    base_context.execution_metadata.clear()
    agent = GitHubAgent(client=FakeGitHubClient())

    result = await agent.execute(base_context)

    assert result.status == ExecutionStatus.SKIPPED
    assert "No valid repository coordinates found" in result.warnings[0]


@pytest.mark.asyncio
async def test_github_agent_separate_coords(base_context: InvestigationContext) -> None:
    base_context.execution_metadata = {
        "github_owner": "DEVDOC-Team",
        "github_name": "devdoc",
    }
    agent = GitHubAgent(client=FakeGitHubClient())
    result = await agent.execute(base_context)
    assert result.status == ExecutionStatus.SUCCESS
    assert result.data["owner"] == "DEVDOC-Team"
    assert result.data["repo"] == "devdoc"


@pytest.mark.asyncio
async def test_github_agent_not_found(base_context: InvestigationContext) -> None:
    client = FakeGitHubClient(should_fail=GitHubNotFoundError("Repository not found", status_code=404))
    agent = GitHubAgent(client=client)

    result = await agent.execute(base_context)

    assert result.status == ExecutionStatus.FAILED
    assert "not found" in (result.error_message or "").lower()
    assert result.output_metadata["error"] == "repository_not_found"


@pytest.mark.asyncio
async def test_github_agent_permission_denied(base_context: InvestigationContext) -> None:
    client = FakeGitHubClient(should_fail=GitHubPermissionError("Forbidden", status_code=403))
    agent = GitHubAgent(client=client)

    result = await agent.execute(base_context)

    assert result.status == ExecutionStatus.FAILED
    assert "permission denied" in (result.error_message or "").lower()
    assert result.output_metadata["error"] == "permission_denied"


@pytest.mark.asyncio
async def test_github_agent_rate_limited(base_context: InvestigationContext) -> None:
    client = FakeGitHubClient(
        should_fail=GitHubRateLimitError("Rate limit exceeded", status_code=429, reset_at=1770000000)
    )
    agent = GitHubAgent(client=client)

    result = await agent.execute(base_context)

    assert result.status == ExecutionStatus.FAILED
    assert "rate limit exceeded" in (result.error_message or "").lower()
    assert result.output_metadata["error"] == "rate_limited"


@pytest.mark.asyncio
async def test_github_agent_timeout(base_context: InvestigationContext) -> None:
    client = FakeGitHubClient(should_fail=GitHubTimeoutError("Request timed out", status_code=504))
    agent = GitHubAgent(client=client)

    result = await agent.execute(base_context)

    assert result.status == ExecutionStatus.FAILED
    assert "timed out" in (result.error_message or "").lower()


@pytest.mark.asyncio
async def test_github_agent_auth_failure(base_context: InvestigationContext) -> None:
    client = FakeGitHubClient(should_fail=GitHubAuthenticationError("Bad credentials", status_code=401))
    agent = GitHubAgent(client=client)

    result = await agent.execute(base_context)

    assert result.status == ExecutionStatus.FAILED
    assert "Bad credentials" in (result.error_message or "")


@pytest.mark.asyncio
async def test_github_agent_api_error(base_context: InvestigationContext) -> None:
    client = FakeGitHubClient(should_fail=GitHubAPIError("Server error 500", status_code=500))
    agent = GitHubAgent(client=client)

    result = await agent.execute(base_context)

    assert result.status == ExecutionStatus.FAILED
    assert "Server error 500" in (result.error_message or "")


@pytest.mark.asyncio
async def test_github_agent_redacts_tokens(base_context: InvestigationContext) -> None:
    leaky_client = FakeGitHubClient(
        commits=[
            {
                "sha": "c123",
                "commit": {
                    "message": "fix: updated token to ghp_1234567890abcdefghijklmnopqrstuvwxyzAB in config",
                    "author": {"name": "Bob", "date": "2026-10-02T12:00:00Z"},
                },
            }
        ]
    )
    agent = GitHubAgent(client=leaky_client)

    result = await agent.execute(base_context)

    assert result.status == ExecutionStatus.SUCCESS
    commit_msg = result.data["commits"][0]["message"]
    assert "ghp_" not in commit_msg
    assert "[REDACTED]" in commit_msg
