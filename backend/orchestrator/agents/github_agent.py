"""GitHub Investigation Agent.

Performs structured repository inspection, commit history analysis, pull request triage,
issue tracking, and workflow inspection for investigations.
Reuses existing Phase 7 GitHubAPIClient. Enforces zero token leakage and bounded timeouts.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import UTC, datetime
from typing import Any

from app.core.github_client import (
    GitHubAPIClient,
    GitHubAPIError,
    GitHubAuthenticationError,
    GitHubNotFoundError,
    GitHubPermissionError,
    GitHubRateLimitError,
    GitHubTimeoutError,
    GitHubValidationError,
)
from orchestrator.contracts.agent import BaseAgent
from orchestrator.core.context import InvestigationContext
from orchestrator.core.result import AgentResult, ExecutionStatus
from orchestrator.core.sanitizer import sanitize_data

logger = logging.getLogger("devdoc.orchestrator.agents.github")

_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9_.\-]+$")


class GitHubAgent(BaseAgent):
    """Investigation agent inspecting GitHub repository state and operational telemetry.

    Capabilities:
    - repository_metadata: Repository name, visibility, default branch, language
    - branch_inspection: Active branches and commit refs
    - commit_history: Recent commits and changes
    - pull_requests: Open/recent PRs and their states
    - issue_tracking: Related operational issues
    - file_inspection: Inspected file contents (strictly bounded)
    - workflow_runs: GitHub Actions CI/CD run statuses
    """

    def __init__(
        self,
        client: GitHubAPIClient | None = None,
        access_token: str | None = None,
        default_timeout: float = 10.0,
    ) -> None:
        self.client = client
        self.access_token = access_token
        self.default_timeout = default_timeout

    @property
    def identifier(self) -> str:
        return "github_agent"

    @property
    def name(self) -> str:
        return "GitHub Investigation Agent"

    @property
    def capabilities(self) -> set[str]:
        return {
            "repository_metadata",
            "branch_inspection",
            "commit_history",
            "pull_requests",
            "issue_tracking",
            "file_inspection",
            "workflow_runs",
        }

    def _get_client(self) -> GitHubAPIClient:
        if self.client is not None:
            return self.client
        return GitHubAPIClient(
            access_token=self.access_token,
            timeout=self.default_timeout,
        )

    def _extract_repo_coords(self, metadata: dict[str, Any]) -> tuple[str, str] | None:
        """Extract and validate repository owner and name from metadata."""
        # Pattern 1: target_repo = "owner/repo" or github_repo = "owner/repo"
        repo_str = (
            metadata.get("github_repo")
            or metadata.get("target_repo")
            or metadata.get("repository")
        )
        if isinstance(repo_str, str) and "/" in repo_str:
            parts = repo_str.strip().split("/", 1)
            owner, repo = parts[0].strip(), parts[1].strip()
            if _IDENTIFIER_PATTERN.match(owner) and _IDENTIFIER_PATTERN.match(repo):
                return owner, repo

        # Pattern 2: separate owner and repo keys
        alt_owner = metadata.get("github_owner") or metadata.get("repo_owner")
        alt_repo = metadata.get("github_name") or metadata.get("repo_name")
        if (
            isinstance(alt_owner, str)
            and isinstance(alt_repo, str)
            and _IDENTIFIER_PATTERN.match(alt_owner.strip())
            and _IDENTIFIER_PATTERN.match(alt_repo.strip())
        ):
            return alt_owner.strip(), alt_repo.strip()

        return None


    async def execute(self, context: InvestigationContext) -> AgentResult:
        """Inspect the repository specified in the investigation context."""
        start_time = time.perf_counter()
        started_at = datetime.now(UTC)

        coords = self._extract_repo_coords(context.execution_metadata)
        if coords is None:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            warning_msg = "No valid repository coordinates found in investigation context metadata"
            logger.info("GitHubAgent skipped: %s", warning_msg)
            return AgentResult(
                agent_id=self.identifier,
                status=ExecutionStatus.SKIPPED,
                investigation_id=context.investigation_id,
                execution_id=context.execution_id,
                source="github",
                warnings=[warning_msg],
                output_metadata={"skipped_reason": "missing_repository_coordinates"},
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_ms=duration_ms,
            )

        owner, repo = coords
        client = self._get_client()
        warnings: list[str] = []
        errors: list[str] = []
        collected_data: dict[str, Any] = {
            "owner": owner,
            "repo": repo,
        }

        try:
            # 1. Repository metadata
            repo_info = await client.get_repository(owner, repo)
            collected_data["repository"] = {
                "name": repo_info.get("name"),
                "full_name": repo_info.get("full_name"),
                "private": repo_info.get("private"),
                "default_branch": repo_info.get("default_branch"),
                "description": repo_info.get("description"),
                "language": repo_info.get("language"),
                "open_issues_count": repo_info.get("open_issues_count"),
                "updated_at": repo_info.get("updated_at"),
            }

            # 2. Branches
            branches = await client.list_branches(owner, repo, per_page=10)
            collected_data["branches"] = [
                {"name": b.get("name"), "commit_sha": b.get("commit", {}).get("sha")}
                for b in branches
            ]

            # 3. Recent commits
            commits = await client.list_commits(owner, repo, per_page=10)
            collected_data["commits"] = [
                {
                    "sha": c.get("sha"),
                    "message": c.get("commit", {}).get("message", "").split("\n")[0],
                    "author": c.get("commit", {}).get("author", {}).get("name"),
                    "date": c.get("commit", {}).get("author", {}).get("date"),
                }
                for c in commits
            ]

            # 4. Pull requests
            prs = await client.list_pull_requests(owner, repo, state="all", per_page=10)
            collected_data["pull_requests"] = [
                {
                    "number": pr.get("number"),
                    "title": pr.get("title"),
                    "state": pr.get("state"),
                    "user": pr.get("user", {}).get("login"),
                    "created_at": pr.get("created_at"),
                    "merged_at": pr.get("merged_at"),
                }
                for pr in prs
            ]

            # 5. Issues
            issues = await client.list_issues(owner, repo, state="open", per_page=10)
            collected_data["issues"] = [
                {
                    "number": issue.get("number"),
                    "title": issue.get("title"),
                    "state": issue.get("state"),
                    "user": issue.get("user", {}).get("login"),
                    "created_at": issue.get("created_at"),
                }
                for issue in issues
            ]

            # 6. Workflow runs (GitHub Actions)
            try:
                workflows = await client.list_workflow_runs(owner, repo, per_page=5)
                runs = workflows.get("workflow_runs", []) if isinstance(workflows, dict) else []
                collected_data["workflow_runs"] = [
                    {
                        "id": run.get("id"),
                        "name": run.get("name"),
                        "status": run.get("status"),
                        "conclusion": run.get("conclusion"),
                        "event": run.get("event"),
                        "created_at": run.get("created_at"),
                    }
                    for run in runs
                ]
            except Exception as wf_exc:
                warning_msg = f"Failed to retrieve workflow runs: {wf_exc}"
                logger.debug(warning_msg)
                warnings.append(warning_msg)
                collected_data["workflow_runs"] = []

            # 7. File inspection (if specifically requested by context)
            requested_files = (
                context.execution_metadata.get("github_file_paths")
                or context.execution_metadata.get("inspect_files")
            )
            if isinstance(requested_files, list):
                collected_data["files"] = {}
                for fpath in requested_files[:5]:  # Bounded to max 5 files
                    if isinstance(fpath, str):
                        try:
                            file_content = await client.get_file_contents(owner, repo, fpath)
                            collected_data["files"][fpath] = {
                                "path": file_content.get("path"),
                                "size": file_content.get("size"),
                                "sha": file_content.get("sha"),
                                "encoding": file_content.get("encoding"),
                            }
                        except Exception as f_err:
                            warnings.append(f"Failed to inspect file '{fpath}': {f_err}")

            sanitized_data = sanitize_data(collected_data)
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            completed_at = datetime.now(UTC)

            summary_meta = {
                "owner": owner,
                "repo": repo,
                "branch_count": len(collected_data.get("branches", [])),
                "commit_count": len(collected_data.get("commits", [])),
                "pr_count": len(collected_data.get("pull_requests", [])),
                "issue_count": len(collected_data.get("issues", [])),
                "workflow_run_count": len(collected_data.get("workflow_runs", [])),
            }

            result = AgentResult(
                agent_id=self.identifier,
                status=ExecutionStatus.SUCCESS,
                investigation_id=context.investigation_id,
                execution_id=context.execution_id,
                source="github",
                data=sanitized_data,
                output_metadata=summary_meta,
                warnings=warnings,
                errors=[],
                collected_at=completed_at,
                started_at=started_at,
                completed_at=completed_at,
                duration_ms=duration_ms,
            )
            context.record_agent_output(self.identifier, summary_meta)
            return result

        except GitHubNotFoundError:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            err_msg = f"GitHub repository '{owner}/{repo}' not found"
            errors.append(err_msg)
            return AgentResult(
                agent_id=self.identifier,
                status=ExecutionStatus.FAILED,
                investigation_id=context.investigation_id,
                execution_id=context.execution_id,
                source="github",
                error_message=err_msg,
                errors=errors,
                warnings=warnings,
                output_metadata={"error": "repository_not_found"},
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_ms=duration_ms,
            )

        except GitHubPermissionError:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            err_msg = f"Permission denied for repository '{owner}/{repo}'"
            errors.append(err_msg)
            return AgentResult(
                agent_id=self.identifier,
                status=ExecutionStatus.FAILED,
                investigation_id=context.investigation_id,
                execution_id=context.execution_id,
                source="github",
                error_message=err_msg,
                errors=errors,
                warnings=warnings,
                output_metadata={"error": "permission_denied"},
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_ms=duration_ms,
            )

        except GitHubRateLimitError as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            err_msg = f"GitHub rate limit exceeded: reset at {exc.reset_at}"
            errors.append(err_msg)
            return AgentResult(
                agent_id=self.identifier,
                status=ExecutionStatus.FAILED,
                investigation_id=context.investigation_id,
                execution_id=context.execution_id,
                source="github",
                error_message=err_msg,
                errors=errors,
                warnings=warnings,
                output_metadata={"error": "rate_limited"},
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_ms=duration_ms,
            )

        except (GitHubTimeoutError, GitHubAuthenticationError, GitHubValidationError, GitHubAPIError) as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            err_msg = f"GitHub API error: {exc.message}"
            errors.append(err_msg)
            return AgentResult(
                agent_id=self.identifier,
                status=ExecutionStatus.FAILED,
                investigation_id=context.investigation_id,
                execution_id=context.execution_id,
                source="github",
                error_message=err_msg,
                errors=errors,
                warnings=warnings,
                output_metadata={"error": type(exc).__name__},
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_ms=duration_ms,
            )

        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            err_msg = f"Unexpected failure in GitHub inspection: {exc}"
            logger.exception("GitHub agent unexpected error")
            errors.append(err_msg)
            return AgentResult(
                agent_id=self.identifier,
                status=ExecutionStatus.FAILED,
                investigation_id=context.investigation_id,
                execution_id=context.execution_id,
                source="github",
                error_message=err_msg,
                errors=errors,
                warnings=warnings,
                output_metadata={"error": "unexpected_error"},
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_ms=duration_ms,
            )
