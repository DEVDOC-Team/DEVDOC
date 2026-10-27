"""Docker Investigation Agent.

Performs structured inspection of container statuses, restarts, health, image metadata,
and bounded log streams for operational incident investigations.
Enforces complete sandboxing: zero arbitrary shell execution, zero subprocesses,
strict identifier validation, and bounded timeouts.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import Any

from orchestrator.agents.docker_inspector import (
    DockerConnectionError,
    DockerError,
    DockerInspector,
    DockerNotFoundError,
    DockerSecurityError,
    DockerTimeoutError,
    FakeDockerInspector,
)
from orchestrator.contracts.agent import BaseAgent
from orchestrator.core.context import InvestigationContext
from orchestrator.core.result import AgentResult, ExecutionStatus
from orchestrator.core.sanitizer import sanitize_data

logger = logging.getLogger("devdoc.orchestrator.agents.docker")


class DockerAgent(BaseAgent):
    """Investigation agent inspecting container states, resource bounds, and logs.

    Capabilities:
    - container_listing: Discovers active and stopped containers
    - container_inspection: State, health, restart count, exit codes
    - container_logs: Bounded recent log stream retrieval
    - image_inspection: Container image tags and metadata
    """

    def __init__(self, inspector: DockerInspector | None = None) -> None:
        self.inspector = inspector if inspector is not None else FakeDockerInspector()

    @property
    def identifier(self) -> str:
        return "docker_agent"

    @property
    def name(self) -> str:
        return "Docker Investigation Agent"

    @property
    def capabilities(self) -> set[str]:
        return {
            "container_listing",
            "container_inspection",
            "container_logs",
            "image_inspection",
        }

    async def execute(self, context: InvestigationContext) -> AgentResult:
        """Execute Docker inspection according to context metadata."""
        start_time = time.perf_counter()
        started_at = datetime.now(UTC)

        metadata = context.execution_metadata
        target_container = (
            metadata.get("container_id")
            or metadata.get("container_name")
            or metadata.get("target_container")
        )
        target_container_ids = metadata.get("container_ids") or []
        tail_lines = int(metadata.get("tail_logs", 50))
        bounded_tail = max(1, min(tail_lines, 500))

        warnings: list[str] = []
        errors: list[str] = []
        collected_data: dict[str, Any] = {}

        try:
            # 1. Determine targets
            targets: list[str] = []
            if isinstance(target_container, str) and target_container.strip():
                targets.append(target_container.strip())
            if isinstance(target_container_ids, list):
                for cid in target_container_ids:
                    if isinstance(cid, str) and cid.strip() and cid.strip() not in targets:
                        targets.append(cid.strip())

            # 2. If specific containers are targeted, inspect them
            if targets:
                inspected_containers: list[dict[str, Any]] = []
                for cid in targets[:5]:  # Bounded to max 5 containers
                    container_info = await self.inspector.inspect_container(cid)

                    # Extract structured safe container summary
                    state = container_info.get("State", {})
                    config = container_info.get("Config", {})
                    host_config = container_info.get("HostConfig", {})

                    is_running = state.get("Running", False)
                    exit_code = state.get("ExitCode", 0)
                    oom_killed = state.get("OOMKilled", False)
                    restart_count = container_info.get("RestartCount", 0)

                    if not is_running and exit_code != 0:
                        warnings.append(
                            f"Container '{cid}' is in non-zero exit state (exit_code={exit_code}, oom_killed={oom_killed})"
                        )
                    if restart_count > 0:
                        warnings.append(f"Container '{cid}' has restarted {restart_count} times")

                    # Retrieve logs safely
                    logs_snippet = ""
                    try:
                        logs_snippet = await self.inspector.get_container_logs(cid, tail=bounded_tail)
                    except Exception as log_err:
                        warnings.append(f"Could not retrieve logs for container '{cid}': {log_err}")

                    inspected_containers.append({
                        "id": container_info.get("Id", cid),
                        "name": container_info.get("Name", cid),
                        "image": config.get("Image"),
                        "state": {
                            "status": state.get("Status"),
                            "running": is_running,
                            "paused": state.get("Paused"),
                            "restarting": state.get("Restarting"),
                            "oom_killed": oom_killed,
                            "dead": state.get("Dead"),
                            "exit_code": exit_code,
                            "error": state.get("Error"),
                            "started_at": state.get("StartedAt"),
                            "finished_at": state.get("FinishedAt"),
                        },
                        "restart_count": restart_count,
                        "network_mode": host_config.get("NetworkMode"),
                        "logs": logs_snippet,
                    })

                collected_data["containers"] = inspected_containers

            else:
                # No specific container targeted: list all containers on the host
                containers_list = await self.inspector.list_containers(all=True)
                summarized: list[dict[str, Any]] = []
                for c in containers_list:
                    state_obj = c.get("State", "")
                    state_str = state_obj.get("Status", "") if isinstance(state_obj, dict) else str(state_obj or "")
                    status_str = str(c.get("Status", ""))
                    cid = str(c.get("Id", ""))[:12]
                    names = c.get("Names", [])
                    summarized.append({
                        "id": cid,
                        "names": names,
                        "image": c.get("Image"),
                        "state": state_str,
                        "status": status_str,
                    })
                    if "exited" in status_str.lower() or "dead" in state_str.lower() or "exit" in state_str.lower():
                        warnings.append(f"Found non-running container '{cid}' ({status_str or state_str})")

                collected_data["containers"] = summarized

            sanitized_data = sanitize_data(collected_data)
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            completed_at = datetime.now(UTC)

            summary_meta = {
                "container_count": len(collected_data.get("containers", [])),
                "inspected_targets": targets,
                "warnings_count": len(warnings),
            }

            result = AgentResult(
                agent_id=self.identifier,
                status=ExecutionStatus.SUCCESS,
                investigation_id=context.investigation_id,
                execution_id=context.execution_id,
                source="docker",
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

        except DockerSecurityError as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            err_msg = f"Docker security violation: {exc}"
            logger.warning("DockerAgent security violation: %s", exc)
            errors.append(err_msg)
            return AgentResult(
                agent_id=self.identifier,
                status=ExecutionStatus.FAILED,
                investigation_id=context.investigation_id,
                execution_id=context.execution_id,
                source="docker",
                error_message=err_msg,
                errors=errors,
                warnings=warnings,
                output_metadata={"error": "security_violation"},
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_ms=duration_ms,
            )

        except DockerNotFoundError as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            err_msg = f"Docker resource not found: {exc}"
            errors.append(err_msg)
            return AgentResult(
                agent_id=self.identifier,
                status=ExecutionStatus.FAILED,
                investigation_id=context.investigation_id,
                execution_id=context.execution_id,
                source="docker",
                error_message=err_msg,
                errors=errors,
                warnings=warnings,
                output_metadata={"error": "resource_not_found"},
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_ms=duration_ms,
            )

        except DockerConnectionError as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            err_msg = f"Docker daemon unavailable: {exc}"
            errors.append(err_msg)
            return AgentResult(
                agent_id=self.identifier,
                status=ExecutionStatus.FAILED,
                investigation_id=context.investigation_id,
                execution_id=context.execution_id,
                source="docker",
                error_message=err_msg,
                errors=errors,
                warnings=warnings,
                output_metadata={"error": "docker_daemon_unavailable"},
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_ms=duration_ms,
            )

        except DockerTimeoutError as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            err_msg = f"Docker operation timed out: {exc}"
            errors.append(err_msg)
            return AgentResult(
                agent_id=self.identifier,
                status=ExecutionStatus.FAILED,
                investigation_id=context.investigation_id,
                execution_id=context.execution_id,
                source="docker",
                error_message=err_msg,
                errors=errors,
                warnings=warnings,
                output_metadata={"error": "timeout"},
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_ms=duration_ms,
            )

        except DockerError as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            err_msg = f"Docker operational error: {exc}"
            errors.append(err_msg)
            return AgentResult(
                agent_id=self.identifier,
                status=ExecutionStatus.FAILED,
                investigation_id=context.investigation_id,
                execution_id=context.execution_id,
                source="docker",
                error_message=err_msg,
                errors=errors,
                warnings=warnings,
                output_metadata={"error": "docker_error"},
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_ms=duration_ms,
            )

        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            err_msg = f"Unexpected failure in Docker inspection: {exc}"
            logger.exception("Docker agent unexpected error")
            errors.append(err_msg)
            return AgentResult(
                agent_id=self.identifier,
                status=ExecutionStatus.FAILED,
                investigation_id=context.investigation_id,
                execution_id=context.execution_id,
                source="docker",
                error_message=err_msg,
                errors=errors,
                warnings=warnings,
                output_metadata={"error": "unexpected_error"},
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_ms=duration_ms,
            )
