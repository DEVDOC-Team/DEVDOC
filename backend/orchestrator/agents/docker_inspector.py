"""Docker Inspector Interface and Implementations.

Provides a strictly sandboxed, narrow abstraction for inspecting Docker containers,
images, and logs. Guarantees zero arbitrary shell execution, no subprocess invocations,
and bounded timeouts.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Any

import httpx

_DOCKER_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_.\-]+$")


class DockerError(Exception):
    """Base exception for all Docker inspection operations."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class DockerConnectionError(DockerError):
    """Raised when the Docker daemon is unreachable or unavailable."""


class DockerNotFoundError(DockerError):
    """Raised when a specified container or image does not exist."""


class DockerTimeoutError(DockerError):
    """Raised when a Docker API operation times out."""


class DockerSecurityError(DockerError):
    """Raised when an identifier or parameter violates strict sandboxing rules."""


def validate_docker_identifier(identifier: str, param_name: str = "identifier") -> str:
    """Validate that a container or image ID/name contains only safe alphanumeric characters.

    Prevents path traversal, shell injection, or URL manipulation.

    Raises:
        DockerSecurityError: If the identifier contains invalid characters or exceeds 128 chars.
    """
    clean = identifier.strip()
    if not clean or len(clean) > 128 or not _DOCKER_ID_PATTERN.match(clean):
        raise DockerSecurityError(
            f"Invalid {param_name} '{identifier}': Must contain only alphanumeric, '-', '_', '.' characters (max 128)"
        )
    return clean


class DockerInspector(ABC):
    """Abstract narrow contract for inspecting Docker engine resources."""

    @abstractmethod
    async def list_containers(self, all: bool = True) -> list[dict[str, Any]]:
        """List containers on the host."""
        ...

    @abstractmethod
    async def inspect_container(self, container_id: str) -> dict[str, Any]:
        """Inspect configuration, status, and state of a container."""
        ...

    @abstractmethod
    async def get_container_logs(self, container_id: str, tail: int = 100) -> str:
        """Retrieve bounded recent logs from a container."""
        ...

    @abstractmethod
    async def inspect_image(self, image_id: str) -> dict[str, Any]:
        """Inspect metadata for a Docker image."""
        ...

    @abstractmethod
    async def ping(self) -> bool:
        """Check whether the Docker engine is reachable."""
        ...


class FakeDockerInspector(DockerInspector):
    """Deterministic in-memory fake inspector for isolated unit tests and CI.

    Guarantees:
    - 0 network calls
    - 0 shell commands
    - Deterministic responses and configurable failure modes
    """

    def __init__(
        self,
        containers: list[dict[str, Any]] | None = None,
        images: dict[str, dict[str, Any]] | None = None,
        logs: dict[str, str] | None = None,
        should_fail_connection: bool = False,
        should_timeout: bool = False,
    ) -> None:
        self.containers: dict[str, dict[str, Any]] = {}
        if containers:
            for c in containers:
                cid = c.get("Id") or c.get("id") or "mock_container"
                self.containers[cid] = c
                # Also index by name
                for name in c.get("Names", []):
                    clean_name = name.lstrip("/")
                    self.containers[clean_name] = c

        self.images: dict[str, dict[str, Any]] = images or {}
        self.logs: dict[str, str] = logs or {}
        self.should_fail_connection = should_fail_connection
        self.should_timeout = should_timeout

    async def ping(self) -> bool:
        if self.should_fail_connection:
            raise DockerConnectionError("Docker daemon unreachable at unix:///var/run/docker.sock")
        if self.should_timeout:
            raise DockerTimeoutError("Docker ping timed out")
        return True

    async def list_containers(self, all: bool = True) -> list[dict[str, Any]]:
        await self.ping()
        seen: set[str] = set()
        res: list[dict[str, Any]] = []
        for c in self.containers.values():
            cid = c.get("Id") or c.get("id")
            if cid and cid not in seen:
                seen.add(cid)
                res.append(c)
        return res

    async def inspect_container(self, container_id: str) -> dict[str, Any]:
        validate_docker_identifier(container_id, "container_id")
        await self.ping()
        if container_id in self.containers:
            return self.containers[container_id]
        raise DockerNotFoundError(f"Container '{container_id}' not found")

    async def get_container_logs(self, container_id: str, tail: int = 100) -> str:
        validate_docker_identifier(container_id, "container_id")
        await self.ping()
        if container_id not in self.containers and container_id not in self.logs:
            raise DockerNotFoundError(f"Container '{container_id}' not found for logs")
        raw_logs = self.logs.get(container_id, "Standard output log stream\nApplication running normally.")
        lines = raw_logs.splitlines()
        bounded_tail = max(1, min(tail, 500))
        return "\n".join(lines[-bounded_tail:])

    async def inspect_image(self, image_id: str) -> dict[str, Any]:
        validate_docker_identifier(image_id, "image_id")
        await self.ping()
        if image_id in self.images:
            return self.images[image_id]
        return {
            "Id": image_id,
            "RepoTags": [f"{image_id}:latest"],
            "Created": "2026-01-01T00:00:00Z",
            "Size": 1024000,
        }


class DockerHTTPInspector(DockerInspector):
    """Narrow HTTP client connecting to the Docker Engine REST API without shell execution."""

    def __init__(
        self,
        base_url: str = "http://localhost:2375",
        timeout: float = 5.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._external_client = client

    def _get_client(self) -> httpx.AsyncClient:
        if self._external_client is not None:
            return self._external_client
        return httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout)

    async def ping(self) -> bool:
        client = self._get_client()
        should_close = self._external_client is None
        try:
            res = await client.get("/_ping")
            return res.status_code == 200
        except httpx.TimeoutException as exc:
            raise DockerTimeoutError("Docker daemon ping timed out") from exc
        except httpx.RequestError as exc:
            raise DockerConnectionError(f"Cannot connect to Docker daemon at {self.base_url}: {exc}") from exc
        finally:
            if should_close:
                await client.aclose()

    async def list_containers(self, all: bool = True) -> list[dict[str, Any]]:
        client = self._get_client()
        should_close = self._external_client is None
        try:
            res = await client.get("/containers/json", params={"all": 1 if all else 0})
            if res.status_code == 200:
                data = res.json()
                return data if isinstance(data, list) else []
            raise DockerError(f"Failed to list containers (status {res.status_code})")
        except httpx.TimeoutException as exc:
            raise DockerTimeoutError("Docker list containers timed out") from exc
        except httpx.RequestError as exc:
            raise DockerConnectionError(f"Docker connection error: {exc}") from exc
        finally:
            if should_close:
                await client.aclose()

    async def inspect_container(self, container_id: str) -> dict[str, Any]:
        valid_id = validate_docker_identifier(container_id, "container_id")
        client = self._get_client()
        should_close = self._external_client is None
        try:
            res = await client.get(f"/containers/{valid_id}/json")
            if res.status_code == 200:
                data = res.json()
                return data if isinstance(data, dict) else {}
            if res.status_code == 404:
                raise DockerNotFoundError(f"Container '{container_id}' not found")
            raise DockerError(f"Docker inspect container failed with status {res.status_code}")
        except httpx.TimeoutException as exc:
            raise DockerTimeoutError(f"Docker inspect container '{container_id}' timed out") from exc
        except httpx.RequestError as exc:
            raise DockerConnectionError(f"Docker connection error: {exc}") from exc
        finally:
            if should_close:
                await client.aclose()

    async def get_container_logs(self, container_id: str, tail: int = 100) -> str:
        valid_id = validate_docker_identifier(container_id, "container_id")
        bounded_tail = max(1, min(tail, 500))
        client = self._get_client()
        should_close = self._external_client is None
        try:
            params = {
                "stdout": 1,
                "stderr": 1,
                "tail": bounded_tail,
                "timestamps": 1,
            }
            res = await client.get(f"/containers/{valid_id}/logs", params=params)
            if res.status_code == 200:
                return res.text
            if res.status_code == 404:
                raise DockerNotFoundError(f"Container '{container_id}' not found for logs")
            raise DockerError(f"Docker get logs failed with status {res.status_code}")
        except httpx.TimeoutException as exc:
            raise DockerTimeoutError(f"Docker get logs for '{container_id}' timed out") from exc
        except httpx.RequestError as exc:
            raise DockerConnectionError(f"Docker connection error: {exc}") from exc
        finally:
            if should_close:
                await client.aclose()

    async def inspect_image(self, image_id: str) -> dict[str, Any]:
        valid_id = validate_docker_identifier(image_id, "image_id")
        client = self._get_client()
        should_close = self._external_client is None
        try:
            res = await client.get(f"/images/{valid_id}/json")
            if res.status_code == 200:
                data = res.json()
                return data if isinstance(data, dict) else {}
            if res.status_code == 404:
                raise DockerNotFoundError(f"Image '{image_id}' not found")
            raise DockerError(f"Docker inspect image failed with status {res.status_code}")
        except httpx.TimeoutException as exc:
            raise DockerTimeoutError(f"Docker inspect image '{image_id}' timed out") from exc
        except httpx.RequestError as exc:
            raise DockerConnectionError(f"Docker connection error: {exc}") from exc
        finally:
            if should_close:
                await client.aclose()
