"""GitHub REST API client abstraction.

Provides a clean, strongly-typed asynchronous client for interacting with the
GitHub REST API. Future investigation and evidence collection agents utilize
this abstraction to inspect repositories, branches, commits, PRs, issues,
source code, and GitHub Actions workflows.

Security Guarantees:
- Never logs access tokens or credentials.
- Bounded HTTP timeouts on all requests.
- Strict path parameter validation to prevent path traversal or SSRF.
- Explicit translation of GitHub error responses (401, 403, 404, 409, 422, 429, 5xx).
"""

from __future__ import annotations

import re
from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import logger

_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9_.\-]+$")
_PATH_TRAVERSAL_PATTERN = re.compile(r"(?:^|/)\.\.(?:/|$)")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class GitHubAPIError(Exception):
    """Base class for all GitHub API client errors."""

    def __init__(self, message: str, status_code: int | None = None, response_body: Any = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.response_body = response_body


class GitHubAuthenticationError(GitHubAPIError):
    """Raised when credentials are invalid, revoked, or expired (HTTP 401)."""


class GitHubPermissionError(GitHubAPIError):
    """Raised when the authenticated user lacks permissions for the resource (HTTP 403)."""


class GitHubRateLimitError(GitHubAPIError):
    """Raised when GitHub API rate limit has been exceeded (HTTP 403 / 429)."""

    def __init__(
        self,
        message: str = "GitHub API rate limit exceeded",
        status_code: int = 429,
        retry_after: int | None = None,
        reset_at: int | None = None,
    ) -> None:
        super().__init__(message, status_code=status_code)
        self.retry_after = retry_after
        self.reset_at = reset_at


class GitHubNotFoundError(GitHubAPIError):
    """Raised when requested repository or resource does not exist (HTTP 404)."""


class GitHubConflictError(GitHubAPIError):
    """Raised when an operation conflicts with existing GitHub state (HTTP 409)."""


class GitHubValidationError(GitHubAPIError):
    """Raised when GitHub rejects input parameters (HTTP 422)."""


class GitHubTimeoutError(GitHubAPIError):
    """Raised when an API request to GitHub times out."""


# ---------------------------------------------------------------------------
# Client Implementation
# ---------------------------------------------------------------------------


class GitHubAPIClient:
    """Production-grade asynchronous client for the GitHub REST API v3."""

    def __init__(
        self,
        access_token: str | None = None,
        base_url: str | None = None,
        timeout: float = 10.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.access_token = access_token
        self.base_url = (base_url or settings.github_api_base_url).rstrip("/")
        self.timeout = timeout
        self._external_client = client

    def _get_headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "DEVDOC-Platform",
        }
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers

    @staticmethod
    def _validate_repo_coords(owner: str, repo: str) -> None:
        if not _IDENTIFIER_PATTERN.match(owner) or not _IDENTIFIER_PATTERN.match(repo):
            raise GitHubValidationError(f"Invalid repository coordinates: {owner}/{repo}")

    @staticmethod
    def _validate_path(path: str) -> str:
        clean_path = path.strip().lstrip("/")
        if _PATH_TRAVERSAL_PATTERN.search(clean_path):
            raise GitHubValidationError(f"Invalid path with traversal elements: {path}")
        return clean_path

    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json: Any = None,
    ) -> Any:
        """Execute a validated HTTP request against GitHub REST API with safe error translation."""
        url = f"{self.base_url}/{path.lstrip('/')}"
        headers = self._get_headers()

        # Clean None parameters
        clean_params = {k: v for k, v in params.items() if v is not None} if params else None

        should_close = False
        client = self._external_client
        if client is None:
            client = httpx.AsyncClient(timeout=self.timeout)
            should_close = True

        try:
            response = await client.request(
                method=method,
                url=url,
                headers=headers,
                params=clean_params,
                json=json,
            )
        except httpx.TimeoutException as exc:
            logger.warning("GitHub API timeout on %s %s", method, path)
            raise GitHubTimeoutError("GitHub API request timed out", status_code=504) from exc
        except httpx.RequestError as exc:
            logger.warning("GitHub API network error on %s %s: %s", method, path, type(exc).__name__)
            raise GitHubAPIError(f"GitHub API network connection error: {exc}", status_code=502) from exc
        finally:
            if should_close:
                await client.aclose()

        status_code = response.status_code

        # Successful responses
        if 200 <= status_code < 300:
            if status_code == 204 or not response.content:
                return None
            return response.json()

        # Handle specific error status codes
        try:
            body = response.json()
        except Exception:
            body = response.text

        # Rate limit checks
        remaining = response.headers.get("x-ratelimit-remaining")
        reset_header = response.headers.get("x-ratelimit-reset")
        reset_at = int(reset_header) if reset_header and reset_header.isdigit() else None
        retry_after_hdr = response.headers.get("retry-after")
        retry_after = int(retry_after_hdr) if retry_after_hdr and retry_after_hdr.isdigit() else None

        if status_code in (403, 429) and (
            remaining == "0"
            or "rate limit" in str(body).lower()
            or status_code == 429
        ):
            logger.warning("GitHub rate limit reached: status %d, reset at %s", status_code, reset_at)
            raise GitHubRateLimitError(
                message="GitHub API rate limit exceeded",
                status_code=status_code,
                retry_after=retry_after,
                reset_at=reset_at,
            )

        if status_code == 401:
            logger.warning("GitHub authentication failed (401)")
            raise GitHubAuthenticationError(
                "GitHub authentication failed. Token may be expired or revoked.",
                status_code=401,
                response_body=body,
            )

        if status_code == 403:
            logger.warning("GitHub permission denied (403) on %s", path)
            raise GitHubPermissionError(
                "Forbidden: Insufficient permissions for GitHub resource",
                status_code=403,
                response_body=body,
            )

        if status_code == 404:
            raise GitHubNotFoundError(
                f"GitHub resource not found: {path}",
                status_code=404,
                response_body=body,
            )

        if status_code == 409:
            raise GitHubConflictError(
                "Conflict with existing GitHub resource",
                status_code=409,
                response_body=body,
            )

        if status_code == 422:
            raise GitHubValidationError(
                "GitHub validation failed for input parameters",
                status_code=422,
                response_body=body,
            )

        # 5xx or unhandled status
        logger.error("GitHub upstream error: %d on %s", status_code, path)
        raise GitHubAPIError(
            f"GitHub API upstream error ({status_code})",
            status_code=status_code,
            response_body=body,
        )

    # -----------------------------------------------------------------------
    # User Profile & Authorization
    # -----------------------------------------------------------------------

    async def get_authenticated_user(self) -> dict[str, Any]:
        """Retrieve profile of the authenticated GitHub user."""
        return await self._request("GET", "user")

    # -----------------------------------------------------------------------
    # Repositories
    # -----------------------------------------------------------------------

    async def list_user_repositories(
        self,
        page: int = 1,
        per_page: int = 30,
        sort: str = "updated",
        visibility: str = "all",
    ) -> list[dict[str, Any]]:
        """List repositories accessible to the authenticated user."""
        params = {
            "page": max(1, page),
            "per_page": min(max(1, per_page), 100),
            "sort": sort,
            "visibility": visibility,
        }
        res = await self._request("GET", "user/repos", params=params)
        return res if isinstance(res, list) else []

    async def get_repository(self, owner: str, repo: str) -> dict[str, Any]:
        """Retrieve repository metadata."""
        self._validate_repo_coords(owner, repo)
        return await self._request("GET", f"repos/{owner}/{repo}")

    # -----------------------------------------------------------------------
    # Branches
    # -----------------------------------------------------------------------

    async def list_branches(
        self,
        owner: str,
        repo: str,
        page: int = 1,
        per_page: int = 30,
    ) -> list[dict[str, Any]]:
        """List branches for a repository."""
        self._validate_repo_coords(owner, repo)
        params = {"page": max(1, page), "per_page": min(max(1, per_page), 100)}
        res = await self._request("GET", f"repos/{owner}/{repo}/branches", params=params)
        return res if isinstance(res, list) else []

    async def get_branch(self, owner: str, repo: str, branch: str) -> dict[str, Any]:
        """Retrieve details for a specific branch."""
        self._validate_repo_coords(owner, repo)
        return await self._request("GET", f"repos/{owner}/{repo}/branches/{branch}")

    # -----------------------------------------------------------------------
    # Commits
    # -----------------------------------------------------------------------

    async def list_commits(
        self,
        owner: str,
        repo: str,
        sha: str | None = None,
        page: int = 1,
        per_page: int = 30,
    ) -> list[dict[str, Any]]:
        """List commits on a repository branch or ref."""
        self._validate_repo_coords(owner, repo)
        params = {
            "page": max(1, page),
            "per_page": min(max(1, per_page), 100),
            "sha": sha,
        }
        res = await self._request("GET", f"repos/{owner}/{repo}/commits", params=params)
        return res if isinstance(res, list) else []

    async def get_commit(self, owner: str, repo: str, ref: str) -> dict[str, Any]:
        """Retrieve detailed metadata and diffs for a specific commit."""
        self._validate_repo_coords(owner, repo)
        return await self._request("GET", f"repos/{owner}/{repo}/commits/{ref}")

    # -----------------------------------------------------------------------
    # Pull Requests
    # -----------------------------------------------------------------------

    async def list_pull_requests(
        self,
        owner: str,
        repo: str,
        state: str = "open",
        page: int = 1,
        per_page: int = 30,
    ) -> list[dict[str, Any]]:
        """List pull requests for a repository."""
        self._validate_repo_coords(owner, repo)
        params = {
            "state": state,
            "page": max(1, page),
            "per_page": min(max(1, per_page), 100),
        }
        res = await self._request("GET", f"repos/{owner}/{repo}/pulls", params=params)
        return res if isinstance(res, list) else []

    async def get_pull_request(self, owner: str, repo: str, pull_number: int) -> dict[str, Any]:
        """Retrieve pull request details."""
        self._validate_repo_coords(owner, repo)
        return await self._request("GET", f"repos/{owner}/{repo}/pulls/{pull_number}")

    # -----------------------------------------------------------------------
    # Issues
    # -----------------------------------------------------------------------

    async def list_issues(
        self,
        owner: str,
        repo: str,
        state: str = "open",
        page: int = 1,
        per_page: int = 30,
    ) -> list[dict[str, Any]]:
        """List issues for a repository."""
        self._validate_repo_coords(owner, repo)
        params = {
            "state": state,
            "page": max(1, page),
            "per_page": min(max(1, per_page), 100),
        }
        res = await self._request("GET", f"repos/{owner}/{repo}/issues", params=params)
        return res if isinstance(res, list) else []

    async def get_issue(self, owner: str, repo: str, issue_number: int) -> dict[str, Any]:
        """Retrieve issue details."""
        self._validate_repo_coords(owner, repo)
        return await self._request("GET", f"repos/{owner}/{repo}/issues/{issue_number}")

    # -----------------------------------------------------------------------
    # Files & Repository Contents
    # -----------------------------------------------------------------------

    async def get_file_contents(
        self,
        owner: str,
        repo: str,
        path: str,
        ref: str | None = None,
    ) -> dict[str, Any]:
        """Retrieve file content metadata (Base64 encoded content from GitHub)."""
        self._validate_repo_coords(owner, repo)
        clean_path = self._validate_path(path)
        params = {"ref": ref} if ref else None
        res = await self._request("GET", f"repos/{owner}/{repo}/contents/{clean_path}", params=params)
        if isinstance(res, dict):
            return res
        raise GitHubValidationError(f"Expected single file content at path '{path}', got directory listing")

    async def get_directory_contents(
        self,
        owner: str,
        repo: str,
        path: str = "",
        ref: str | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve directory contents listing."""
        self._validate_repo_coords(owner, repo)
        clean_path = self._validate_path(path) if path else ""
        sub_path = f"/{clean_path}" if clean_path else ""
        params = {"ref": ref} if ref else None
        res = await self._request("GET", f"repos/{owner}/{repo}/contents{sub_path}", params=params)
        if isinstance(res, list):
            return res
        return [res]

    # -----------------------------------------------------------------------
    # GitHub Actions Workflows
    # -----------------------------------------------------------------------

    async def list_workflow_runs(
        self,
        owner: str,
        repo: str,
        page: int = 1,
        per_page: int = 30,
    ) -> dict[str, Any]:
        """List GitHub Actions workflow runs for a repository."""
        self._validate_repo_coords(owner, repo)
        params = {"page": max(1, page), "per_page": min(max(1, per_page), 100)}
        return await self._request("GET", f"repos/{owner}/{repo}/actions/runs", params=params)

    async def get_workflow_run(self, owner: str, repo: str, run_id: int) -> dict[str, Any]:
        """Retrieve a specific GitHub Actions workflow run."""
        self._validate_repo_coords(owner, repo)
        return await self._request("GET", f"repos/{owner}/{repo}/actions/runs/{run_id}")
