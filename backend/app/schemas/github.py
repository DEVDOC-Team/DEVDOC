"""GitHub Integration Schemas.

All schemas strictly enforce no credential or token leakage.
Request schemas enforce extra="forbid" for strong input validation.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# OAuth & Connection Status Schemas
# ---------------------------------------------------------------------------


class GitHubConnectResponse(BaseModel):
    """Returned when initiating GitHub OAuth flow."""

    authorization_url: str = Field(..., description="GitHub OAuth authorization redirect URL")
    state: str = Field(..., description="Cryptographically signed CSRF state parameter")

    model_config = ConfigDict(extra="forbid")


class GitHubConnectionResponse(BaseModel):
    """Safe connection status for the authenticated user.

    Never exposes access tokens or secrets.
    """

    connected: bool = Field(..., description="True if user has an active GitHub connection")
    github_user_id: str | None = Field(None, description="GitHub user ID")
    github_username: str | None = Field(None, description="GitHub login username")
    avatar_url: str | None = Field(None, description="GitHub avatar URL")
    scope: str | None = Field(None, description="Authorized OAuth scopes")
    created_at: datetime | None = Field(None, description="Connection creation timestamp")
    updated_at: datetime | None = Field(None, description="Connection update timestamp")

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class GitHubDisconnectResponse(BaseModel):
    """Response returned after disconnecting GitHub integration."""

    success: bool = True
    message: str = "GitHub connection removed successfully"

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Repository Exploration & Association Schemas
# ---------------------------------------------------------------------------


class GitHubRepositoryInfo(BaseModel):
    """Safe representation of a remote GitHub repository."""

    id: int = Field(..., description="GitHub repository ID")
    name: str = Field(..., description="Repository name")
    full_name: str = Field(..., description="Repository full name 'owner/repo'")
    owner: str = Field(..., description="Repository owner login")
    is_private: bool = Field(..., description="True if repository is private")
    html_url: str = Field(..., description="Web URL for repository")
    description: str | None = Field(None, description="Repository description")
    default_branch: str = Field("main", description="Default branch name")
    language: str | None = Field(None, description="Primary programming language")
    fork: bool = Field(False, description="True if repository is a fork")
    updated_at: datetime | None = Field(None, description="Last update timestamp on GitHub")

    model_config = ConfigDict(extra="forbid")


class GitHubRepositoriesListResponse(BaseModel):
    """Paginated list of repositories accessible to user's GitHub account."""

    items: list[GitHubRepositoryInfo]
    page: int
    per_page: int
    total: int | None = None

    model_config = ConfigDict(extra="forbid")



class ProjectRepositoryAttach(BaseModel):
    """Request payload to associate an authorized GitHub repository with a project."""

    full_name: str = Field(
        ...,
        pattern=r"^[A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+$",
        description="Repository full name in 'owner/repo' format",
    )

    @field_validator("full_name")
    @classmethod
    def validate_no_traversal(cls, v: str) -> str:
        if ".." in v or v.startswith((".", "/")) or v.endswith((".", "/")):
            raise ValueError("Repository full_name contains invalid traversal or dot characters")
        return v

    model_config = ConfigDict(extra="forbid")




class RepositoryResponse(BaseModel):
    """DEVDOC project repository association record."""

    id: uuid.UUID
    project_id: uuid.UUID
    provider: str
    full_name: str
    provider_repo_id: str | None = None
    clone_url: str | None = None
    default_branch: str = "main"
    description: str | None = None
    language: str | None = None
    is_active: bool = True
    last_synced_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class ProjectRepositoryDeleteResponse(BaseModel):
    """Response returned after disconnecting a repository from a project."""

    success: bool = True
    message: str = "Repository disconnected successfully from project"
    repository_id: uuid.UUID

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# GitHub Evidence / Investigation Schemas (for future investigation pipeline)
# ---------------------------------------------------------------------------


class GitHubBranch(BaseModel):
    name: str
    sha: str
    protected: bool = False

    model_config = ConfigDict(extra="forbid")


class GitHubCommit(BaseModel):
    sha: str
    message: str
    author_name: str | None = None
    author_email: str | None = None
    committed_at: datetime | None = None
    html_url: str | None = None

    model_config = ConfigDict(extra="forbid")


class GitHubPullRequest(BaseModel):
    id: int
    number: int
    title: str
    state: str
    user: str
    html_url: str
    created_at: datetime | None = None
    merged: bool = False

    model_config = ConfigDict(extra="forbid")


class GitHubIssue(BaseModel):
    id: int
    number: int
    title: str
    state: str
    user: str
    html_url: str
    created_at: datetime | None = None

    model_config = ConfigDict(extra="forbid")


class GitHubFileContent(BaseModel):
    name: str
    path: str
    sha: str
    size: int
    type: str
    content: str | None = None
    encoding: str | None = None

    model_config = ConfigDict(extra="forbid")


class GitHubWorkflowRun(BaseModel):
    id: int
    name: str | None = None
    head_branch: str | None = None
    head_sha: str | None = None
    status: str | None = None
    conclusion: str | None = None
    html_url: str | None = None
    created_at: datetime | None = None

    model_config = ConfigDict(extra="forbid")
