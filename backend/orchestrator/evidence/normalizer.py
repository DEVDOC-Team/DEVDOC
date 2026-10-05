"""Evidence normalizer.

Converts diverse operational AgentResult payloads into a standardized collection
of typed Evidence items. Normalizes timestamps, correlation keys, provenance,
and applies string truncation and recursive credential sanitization.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from typing import Any

from orchestrator.core.context import InvestigationContext
from orchestrator.core.result import AgentResult, ExecutionStatus
from orchestrator.core.sanitizer import sanitize_data
from orchestrator.evidence.config import EvidenceLimitsConfig
from orchestrator.evidence.models import (
    Evidence,
    EvidenceProvenance,
    EvidenceQuality,
    EvidenceSource,
    EvidenceType,
    SourceReliability,
    TimestampType,
)
from orchestrator.evidence.timestamp import normalize_timestamp

logger = logging.getLogger("devdoc.orchestrator.evidence.normalizer")


class EvidenceNormalizer:
    """Normalizes raw operational AgentResult payloads into standardized Evidence items."""

    def __init__(self, limits: EvidenceLimitsConfig | None = None) -> None:
        self.limits = limits if limits is not None else EvidenceLimitsConfig()

    def _truncate_string(self, text: str, field_name: str, truncated_fields: list[str]) -> str:
        """Truncate strings exceeding max length, appending an explicit [TRUNCATED] marker."""
        if len(text) > self.limits.max_string_length:
            if field_name not in truncated_fields:
                truncated_fields.append(field_name)
            marker = "[TRUNCATED]"
            if self.limits.max_string_length <= len(marker):
                return marker[: self.limits.max_string_length]
            return text[: self.limits.max_string_length - len(marker)] + marker
        return text

    def _sanitize_and_bound_data(
        self, data: dict[str, Any], truncated_fields: list[str]
    ) -> dict[str, Any]:
        """Deeply sanitize credentials and truncate oversized text fields in payloads."""
        def _bound_recursive(obj: Any, path: str, depth: int = 0) -> Any:
            if depth >= 12:
                if path not in truncated_fields:
                    truncated_fields.append(path)
                return "[TRUNCATED]"
            if isinstance(obj, str):
                return self._truncate_string(obj, path, truncated_fields)
            if isinstance(obj, dict):
                bounded_entries: list[tuple[Any, Any]] = []
                truncated = False
                for index, entry in enumerate(obj.items()):
                    if index >= self.limits.max_source_records_per_agent:
                        truncated = True
                        break
                    bounded_entries.append(entry)
                if truncated and path not in truncated_fields:
                    truncated_fields.append(path)
                bounded_dict = {
                    k: _bound_recursive(v, f"{path}.{k}", depth + 1)
                    for k, v in bounded_entries
                }
                if truncated:
                    marker_key = "_devdoc_truncated_fields"
                    if marker_key not in bounded_dict:
                        bounded_dict[marker_key] = [path]
                return bounded_dict
            if isinstance(obj, list):
                bounded_items = obj[: self.limits.max_source_records_per_agent]
                if len(obj) > len(bounded_items) and path not in truncated_fields:
                    truncated_fields.append(path)
                bounded_list = [
                    _bound_recursive(item, f"{path}[{i}]", depth + 1)
                    for i, item in enumerate(bounded_items)
                ]
                if len(obj) > len(bounded_items):
                    bounded_list.append("[TRUNCATED]")
                return bounded_list
            return obj

        bounded_data = _bound_recursive(data, "data")
        sanitized = sanitize_data(bounded_data)
        if isinstance(sanitized, dict):
            return sanitized
        return {"value": sanitized}

    def normalize_agent_result(
        self,
        result: AgentResult,
        context: InvestigationContext,
    ) -> list[Evidence]:
        """Normalize an AgentResult into a list of typed Evidence items."""
        # Skip failed without data or skipped executions gracefully
        if result.status == ExecutionStatus.SKIPPED or (
            result.status == ExecutionStatus.FAILED and not result.data
        ):
            return []

        source = (result.source or result.agent_id.replace("_agent", "")).lower()
        collected_at = result.collected_at or result.completed_at or datetime.now(UTC)

        if source == "github" or result.agent_id == "github_agent":
            return self._normalize_github(result, context, collected_at)
        elif source == "docker" or result.agent_id == "docker_agent":
            return self._normalize_docker(result, context, collected_at)
        elif source == "monitoring" or result.agent_id == "monitoring_agent":
            return self._normalize_monitoring(result, context, collected_at)
        elif source == "external_knowledge" or result.agent_id == "knowledge_search_agent":
            return self._normalize_external_knowledge(result, context, collected_at)
        else:
            return self._normalize_generic(result, context, collected_at)

    def _normalize_external_knowledge(
        self,
        result: AgentResult,
        context: InvestigationContext,
        collected_at: datetime,
    ) -> list[Evidence]:
        """Normalize one untrusted web result while preserving source attribution."""
        data = result.data
        title = data.get("title")
        url = data.get("url")
        snippet = data.get("snippet")
        query = data.get("query")
        provider = data.get("provider")
        source_domain = data.get("source_domain")
        if not all(
            isinstance(value, str) and value.strip()
            for value in (title, url, snippet, query, provider, source_domain)
        ):
            return []
        if not url.startswith("https://"):
            return []

        safe_data = self._sanitize_and_bound_data(
            {
                "url": url,
                "provider": provider,
                "query": query,
                "snippet": snippet,
                "source_domain": source_domain,
                "trust_classification": "untrusted_external",
                "published_at": data.get("published_at"),
                "relevance_score": data.get("relevance_score"),
            },
            [],
        )
        url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()
        utc_collected_at = (
            collected_at.astimezone(UTC)
            if collected_at.tzinfo
            else collected_at.replace(tzinfo=UTC)
        )
        return [
            Evidence(
                investigation_id=context.investigation_id,
                execution_id=context.execution_id,
                source=EvidenceSource.EXTERNAL_KNOWLEDGE.value,
                source_type=EvidenceSource.EXTERNAL_KNOWLEDGE,
                evidence_type=EvidenceType.EXTERNAL_KNOWLEDGE,
                timestamp=utc_collected_at,
                timestamp_type=TimestampType.COLLECTION,
                title=title,
                summary=snippet,
                data=safe_data,
                provenance=EvidenceProvenance(
                    agent_id="knowledge_search_agent",
                    source=provider,
                    collected_at=utc_collected_at,
                    source_reference=url,
                    original_id=url,
                    metadata={
                        "query": query,
                        "source_domain": source_domain,
                        "trust_classification": "untrusted_external",
                    },
                ),
                quality=EvidenceQuality(
                    source_reliability=SourceReliability.MEDIUM,
                    timestamp_quality=TimestampType.COLLECTION,
                ),
                correlation_identifiers=[f"external_url:{url_hash}"],
                warnings=["External knowledge is untrusted, not observed incident fact"],
                dedup_key=f"external_knowledge:{url_hash}",
            )
        ]

    def _normalize_github(
        self,
        result: AgentResult,
        context: InvestigationContext,
        collected_at: datetime,
    ) -> list[Evidence]:
        """Normalize GitHub agent output into repository, commit, PR, issue, and workflow evidence."""
        items: list[Evidence] = []
        data = result.data or {}
        repo_meta = data.get("repository") or {}
        repo_name = repo_meta.get("full_name") or data.get("full_name")
        if not repo_name:
            owner = repo_meta.get("owner") or result.output_metadata.get("owner")
            name = repo_meta.get("name") or result.output_metadata.get("repo")
            repo_name = f"{owner}/{name}" if owner and name else "unknown/repository"

        common_correlation = [f"repo:{repo_name}"]

        # 1. Repository metadata
        if repo_meta:
            truncated: list[str] = []
            safe_data = self._sanitize_and_bound_data(repo_meta, truncated)
            items.append(
                Evidence(
                    investigation_id=context.investigation_id,
                    execution_id=context.execution_id,
                    source="github",
                    source_type=EvidenceSource.GITHUB,
                    evidence_type=EvidenceType.REPOSITORY,
                    timestamp=collected_at,
                    timestamp_type=TimestampType.COLLECTION,
                    title=f"Repository Metadata: {repo_name}",
                    summary=f"GitHub repository {repo_name} (default branch: {repo_meta.get('default_branch', 'main')})",
                    data=safe_data,
                    provenance=EvidenceProvenance(
                        agent_id=result.agent_id,
                        source="github",
                        collected_at=collected_at,
                        source_reference=repo_name,
                        original_id=str(repo_meta.get("id", repo_name)),
                    ),
                    quality=EvidenceQuality(
                        source_reliability=SourceReliability.AUTHORITATIVE,
                        timestamp_quality=TimestampType.COLLECTION,
                    ),
                    correlation_identifiers=list(common_correlation),
                    warnings=list(result.warnings),
                    dedup_key=f"github:repository:{repo_name}",
                )
            )

        # 2. Commits
        commits = data.get("commits", [])
        if isinstance(commits, list):
            for c in commits[: self.limits.max_source_records_per_agent]:
                if not isinstance(c, dict):
                    continue
                sha = str(c.get("sha", ""))
                msg = str(c.get("message", "")).splitlines()[0] if c.get("message") else "No message"
                author = c.get("author") or {}
                author_name = author.get("name") if isinstance(author, dict) else str(author)

                c_date = c.get("date") or (author.get("date") if isinstance(author, dict) else None)
                ts, ts_type, ts_warnings = normalize_timestamp(c_date, fallback=collected_at)

                truncated = []
                safe_data = self._sanitize_and_bound_data(c, truncated)
                corr = list(common_correlation)
                if sha:
                    corr.append(f"commit:{sha}")
                if author_name:
                    corr.append(f"author:{author_name}")

                items.append(
                    Evidence(
                        investigation_id=context.investigation_id,
                        execution_id=context.execution_id,
                        source="github",
                        source_type=EvidenceSource.GITHUB,
                        evidence_type=EvidenceType.COMMIT,
                        timestamp=ts,
                        timestamp_type=ts_type,
                        title=f"Commit {sha[:8]}: {msg[:70]}",
                        summary=f"Commit by {author_name or 'unknown'}: {msg}",
                        data=safe_data,
                        provenance=EvidenceProvenance(
                            agent_id=result.agent_id,
                            source="github",
                            collected_at=collected_at,
                            source_reference=f"{repo_name}@{sha}",
                            original_id=sha,
                        ),
                        quality=EvidenceQuality(
                            source_reliability=SourceReliability.AUTHORITATIVE,
                            timestamp_quality=ts_type,
                        ),
                        correlation_identifiers=corr,
                        warnings=ts_warnings,
                        dedup_key=f"github:commit:{repo_name}:{sha}",
                    )
                )

        # 3. Pull Requests
        prs = data.get("pull_requests", [])
        if isinstance(prs, list):
            for pr in prs[: self.limits.max_source_records_per_agent]:
                if not isinstance(pr, dict):
                    continue
                num = pr.get("number")
                title = str(pr.get("title", "Pull Request"))
                state = str(pr.get("state", "open"))
                pr_ts_raw = pr.get("updated_at") or pr.get("created_at")
                ts, ts_type, ts_warnings = normalize_timestamp(pr_ts_raw, fallback=collected_at)

                truncated = []
                safe_data = self._sanitize_and_bound_data(pr, truncated)
                corr = list(common_correlation)
                if num is not None:
                    corr.append(f"pr:{num}")

                items.append(
                    Evidence(
                        investigation_id=context.investigation_id,
                        execution_id=context.execution_id,
                        source="github",
                        source_type=EvidenceSource.GITHUB,
                        evidence_type=EvidenceType.PULL_REQUEST,
                        timestamp=ts,
                        timestamp_type=ts_type,
                        title=f"PR #{num}: {title[:70]}",
                        summary=f"Pull request #{num} ({state}): {title}",
                        data=safe_data,
                        provenance=EvidenceProvenance(
                            agent_id=result.agent_id,
                            source="github",
                            collected_at=collected_at,
                            source_reference=f"{repo_name}#PR{num}",
                            original_id=str(num),
                        ),
                        quality=EvidenceQuality(
                            source_reliability=SourceReliability.AUTHORITATIVE,
                            timestamp_quality=ts_type,
                        ),
                        correlation_identifiers=corr,
                        warnings=ts_warnings,
                        dedup_key=f"github:pr:{repo_name}:{num}",
                    )
                )

        # 4. Issues
        issues = data.get("issues", [])
        if isinstance(issues, list):
            for issue in issues[: self.limits.max_source_records_per_agent]:
                if not isinstance(issue, dict):
                    continue
                num = issue.get("number")
                title = str(issue.get("title", "Issue"))
                state = str(issue.get("state", "open"))
                iss_ts_raw = issue.get("updated_at") or issue.get("created_at")
                ts, ts_type, ts_warnings = normalize_timestamp(iss_ts_raw, fallback=collected_at)

                truncated = []
                safe_data = self._sanitize_and_bound_data(issue, truncated)
                corr = list(common_correlation)
                if num is not None:
                    corr.append(f"issue:{num}")

                items.append(
                    Evidence(
                        investigation_id=context.investigation_id,
                        execution_id=context.execution_id,
                        source="github",
                        source_type=EvidenceSource.GITHUB,
                        evidence_type=EvidenceType.ISSUE,
                        timestamp=ts,
                        timestamp_type=ts_type,
                        title=f"Issue #{num}: {title[:70]}",
                        summary=f"Issue #{num} ({state}): {title}",
                        data=safe_data,
                        provenance=EvidenceProvenance(
                            agent_id=result.agent_id,
                            source="github",
                            collected_at=collected_at,
                            source_reference=f"{repo_name}#Issue{num}",
                            original_id=str(num),
                        ),
                        quality=EvidenceQuality(
                            source_reliability=SourceReliability.AUTHORITATIVE,
                            timestamp_quality=ts_type,
                        ),
                        correlation_identifiers=corr,
                        warnings=ts_warnings,
                        dedup_key=f"github:issue:{repo_name}:{num}",
                    )
                )

        # 5. Workflow Runs
        wf_runs = data.get("workflow_runs", [])
        if isinstance(wf_runs, list):
            for run in wf_runs[: self.limits.max_source_records_per_agent]:
                if not isinstance(run, dict):
                    continue
                run_id = run.get("id")
                run_name = run.get("name") or "CI Workflow"
                conclusion = run.get("conclusion") or run.get("status") or "unknown"
                run_ts_raw = run.get("created_at") or run.get("run_started_at")
                ts, ts_type, ts_warnings = normalize_timestamp(run_ts_raw, fallback=collected_at)

                truncated = []
                safe_data = self._sanitize_and_bound_data(run, truncated)
                corr = list(common_correlation)
                if run_id is not None:
                    corr.append(f"workflow_run:{run_id}")
                corr.append(f"workflow:{run_name}")

                items.append(
                    Evidence(
                        investigation_id=context.investigation_id,
                        execution_id=context.execution_id,
                        source="github",
                        source_type=EvidenceSource.GITHUB,
                        evidence_type=EvidenceType.WORKFLOW_RUN,
                        timestamp=ts,
                        timestamp_type=ts_type,
                        title=f"Workflow '{run_name}': {conclusion}",
                        summary=f"GitHub Actions run {run_id} ({conclusion})",
                        data=safe_data,
                        provenance=EvidenceProvenance(
                            agent_id=result.agent_id,
                            source="github",
                            collected_at=collected_at,
                            source_reference=f"{repo_name}@wf/{run_id}",
                            original_id=str(run_id),
                        ),
                        quality=EvidenceQuality(
                            source_reliability=SourceReliability.AUTHORITATIVE,
                            timestamp_quality=ts_type,
                        ),
                        correlation_identifiers=corr,
                        warnings=ts_warnings,
                        dedup_key=f"github:workflow:{repo_name}:{run_id}",
                    )
                )

        # 6. Inspected Files
        files = data.get("files", {})
        if isinstance(files, dict):
            for fpath, finfo in list(files.items())[: self.limits.max_source_records_per_agent]:
                if not isinstance(finfo, dict):
                    continue
                fsha = finfo.get("sha", "")
                truncated = []
                safe_data = self._sanitize_and_bound_data(finfo, truncated)
                corr = list(common_correlation)
                corr.append(f"file:{fpath}")

                items.append(
                    Evidence(
                        investigation_id=context.investigation_id,
                        execution_id=context.execution_id,
                        source="github",
                        source_type=EvidenceSource.GITHUB,
                        evidence_type=EvidenceType.FILE_CONTENT,
                        timestamp=collected_at,
                        timestamp_type=TimestampType.COLLECTION,
                        title=f"File Content: {fpath}",
                        summary=f"Inspected file {fpath} (size: {finfo.get('size', 0)} bytes)",
                        data=safe_data,
                        provenance=EvidenceProvenance(
                            agent_id=result.agent_id,
                            source="github",
                            collected_at=collected_at,
                            source_reference=f"{repo_name}:{fpath}",
                            original_id=fsha or fpath,
                        ),
                        quality=EvidenceQuality(
                            source_reliability=SourceReliability.AUTHORITATIVE,
                            timestamp_quality=TimestampType.COLLECTION,
                        ),
                        correlation_identifiers=corr,
                        dedup_key=f"github:file:{repo_name}:{fpath}",
                    )
                )

        return items

    def _normalize_docker(
        self,
        result: AgentResult,
        context: InvestigationContext,
        collected_at: datetime,
    ) -> list[Evidence]:
        """Normalize Docker agent output into container states, logs, and images."""
        items: list[Evidence] = []
        data = result.data or {}
        containers = data.get("containers", [])
        if not isinstance(containers, list):
            return []

        for c in containers[: self.limits.max_source_records_per_agent]:
            if not isinstance(c, dict):
                continue
            cid = str(c.get("id", ""))
            names = c.get("names") or []
            if isinstance(names, list) and names:
                primary_name = str(names[0]).lstrip("/")
            else:
                primary_name = str(c.get("name", cid[:12])).lstrip("/")

            image = str(c.get("image", "unknown"))
            state_raw = c.get("state")
            state_dict = state_raw if isinstance(state_raw, dict) else {}
            status_text = (
                state_dict.get("status")
                or (str(state_raw) if state_raw else c.get("status", "unknown"))
            )

            # Determine timestamp
            event_ts_raw = state_dict.get("finished_at") or state_dict.get("started_at")
            ts, ts_type, ts_warnings = normalize_timestamp(event_ts_raw, fallback=collected_at)

            # Build correlation keys
            corr: list[str] = [f"container:{cid[:12]}", f"image:{image}"]
            if primary_name:
                corr.append(f"service:{primary_name}")
                corr.append(f"name:{primary_name}")

            # 1. Container state evidence
            truncated: list[str] = []
            safe_c = self._sanitize_and_bound_data(c, truncated)
            exit_code = state_dict.get("exit_code")
            oom_killed = state_dict.get("oom_killed")
            restarts = c.get("restart_count", 0)

            summary_notes = [f"Status: {status_text}"]
            if exit_code is not None and exit_code != 0:
                summary_notes.append(f"Exit code: {exit_code}")
            if oom_killed:
                summary_notes.append("OOMKilled: true")
            if restarts:
                summary_notes.append(f"Restarts: {restarts}")

            state_hash = hashlib.sha256(
                f"{status_text}:{exit_code}:{oom_killed}:{restarts}:{ts.isoformat()}".encode()
            ).hexdigest()[:12]

            items.append(
                Evidence(
                    investigation_id=context.investigation_id,
                    execution_id=context.execution_id,
                    source="docker",
                    source_type=EvidenceSource.DOCKER,
                    evidence_type=EvidenceType.CONTAINER_STATE,
                    timestamp=ts,
                    timestamp_type=ts_type,
                    title=f"Container {primary_name} ({cid[:12]}): {status_text}",
                    summary="; ".join(summary_notes),
                    data=safe_c,
                    provenance=EvidenceProvenance(
                        agent_id=result.agent_id,
                        source="docker",
                        collected_at=collected_at,
                        source_reference=f"docker://{cid}",
                        original_id=cid,
                    ),
                    quality=EvidenceQuality(
                        source_reliability=SourceReliability.HIGH,
                        timestamp_quality=ts_type,
                    ),
                    correlation_identifiers=corr,
                    warnings=ts_warnings,
                    dedup_key=f"docker:container_state:{cid}:{state_hash}",
                )
            )

            # 2. Container log snippet evidence (if logs were retrieved)
            logs = c.get("logs")
            if isinstance(logs, str) and logs.strip():
                log_truncated: list[str] = []
                safe_log = self._truncate_string(logs.strip(), "logs", log_truncated)
                log_hash = hashlib.sha256(safe_log.encode()).hexdigest()[:12]

                items.append(
                    Evidence(
                        investigation_id=context.investigation_id,
                        execution_id=context.execution_id,
                        source="docker",
                        source_type=EvidenceSource.DOCKER,
                        evidence_type=EvidenceType.CONTAINER_LOG,
                        timestamp=collected_at,
                        timestamp_type=TimestampType.COLLECTION,
                        title=f"Container Logs: {primary_name} ({cid[:12]})",
                        summary=f"Recent log output for container {primary_name} ({len(safe_log.splitlines())} lines)",
                        data={"container_id": cid, "name": primary_name, "logs": safe_log},
                        provenance=EvidenceProvenance(
                            agent_id=result.agent_id,
                            source="docker",
                            collected_at=collected_at,
                            source_reference=f"docker://{cid}/logs",
                            original_id=f"{cid}_logs",
                        ),
                        quality=EvidenceQuality(
                            source_reliability=SourceReliability.MEDIUM,
                            timestamp_quality=TimestampType.COLLECTION,
                        ),
                        correlation_identifiers=corr,
                        dedup_key=f"docker:container_log:{cid}:{log_hash}",
                    )
                )

        return items

    def _normalize_monitoring(
        self,
        result: AgentResult,
        context: InvestigationContext,
        collected_at: datetime,
    ) -> list[Evidence]:
        """Normalize Monitoring agent output into service health, metrics, and alerts."""
        items: list[Evidence] = []
        data = result.data or {}
        service_name = str(data.get("service") or result.output_metadata.get("service") or "default-service")
        common_correlation = [f"service:{service_name}"]

        # 1. Service Health
        health = data.get("health")
        if isinstance(health, dict):
            status_val = str(health.get("status", "unknown"))
            msg = health.get("message", "")
            h_ts_raw = health.get("checked_at")
            ts, ts_type, ts_warnings = normalize_timestamp(h_ts_raw, fallback=collected_at)

            truncated: list[str] = []
            safe_health = self._sanitize_and_bound_data(health, truncated)
            h_hash = hashlib.sha256(f"{status_val}:{ts.isoformat()}".encode()).hexdigest()[:12]

            items.append(
                Evidence(
                    investigation_id=context.investigation_id,
                    execution_id=context.execution_id,
                    source="monitoring",
                    source_type=EvidenceSource.MONITORING,
                    evidence_type=EvidenceType.SERVICE_HEALTH,
                    timestamp=ts,
                    timestamp_type=ts_type,
                    title=f"Service Health for '{service_name}': {status_val.upper()}",
                    summary=f"Service status is {status_val}. {msg}".strip(),
                    data=safe_health,
                    provenance=EvidenceProvenance(
                        agent_id=result.agent_id,
                        source="monitoring",
                        collected_at=collected_at,
                        source_reference=f"monitoring://{service_name}/health",
                        original_id=f"{service_name}_health",
                    ),
                    quality=EvidenceQuality(
                        source_reliability=SourceReliability.AUTHORITATIVE,
                        timestamp_quality=ts_type,
                    ),
                    correlation_identifiers=list(common_correlation),
                    warnings=ts_warnings,
                    dedup_key=f"monitoring:health:{service_name}:{h_hash}",
                )
            )

        # 2. Metrics
        metrics_container = data.get("metrics")
        if isinstance(metrics_container, dict):
            m_ts_raw = metrics_container.get("collected_at")
            ts, ts_type, ts_warnings = normalize_timestamp(m_ts_raw, fallback=collected_at)
            metrics_dict = metrics_container.get("metrics") or {}

            truncated = []
            safe_metrics = self._sanitize_and_bound_data(metrics_container, truncated)
            m_summary_parts: list[str] = []
            for k in ("cpu_percent", "memory_percent", "error_rate_percent", "latency_p99_ms"):
                if k in metrics_dict:
                    m_summary_parts.append(f"{k}={metrics_dict[k]}")

            m_hash = hashlib.sha256(f"{ts.isoformat()}:{sorted(metrics_dict.items())}".encode()).hexdigest()[:12]

            items.append(
                Evidence(
                    investigation_id=context.investigation_id,
                    execution_id=context.execution_id,
                    source="monitoring",
                    source_type=EvidenceSource.MONITORING,
                    evidence_type=EvidenceType.METRIC,
                    timestamp=ts,
                    timestamp_type=ts_type,
                    title=f"Telemetry Metrics for '{service_name}'",
                    summary="; ".join(m_summary_parts) if m_summary_parts else "Telemetry metrics",
                    data=safe_metrics,
                    provenance=EvidenceProvenance(
                        agent_id=result.agent_id,
                        source="monitoring",
                        collected_at=collected_at,
                        source_reference=f"monitoring://{service_name}/metrics",
                        original_id=f"{service_name}_metrics",
                    ),
                    quality=EvidenceQuality(
                        source_reliability=SourceReliability.HIGH,
                        timestamp_quality=ts_type,
                    ),
                    correlation_identifiers=list(common_correlation),
                    warnings=ts_warnings,
                    dedup_key=f"monitoring:metric:{service_name}:{m_hash}",
                )
            )

        # 3. Alerts
        alerts = data.get("alerts", [])
        if isinstance(alerts, list):
            for alert in alerts[: self.limits.max_source_records_per_agent]:
                if not isinstance(alert, dict):
                    continue
                aid = str(alert.get("alert_id") or alert.get("name") or "alert")
                aname = alert.get("name", aid)
                sev = str(alert.get("severity", "warning")).upper()
                msg = str(alert.get("message", aname))
                a_ts_raw = alert.get("triggered_at") or alert.get("timestamp")
                ts, ts_type, ts_warnings = normalize_timestamp(a_ts_raw, fallback=collected_at)

                truncated = []
                safe_alert = self._sanitize_and_bound_data(alert, truncated)
                corr = list(common_correlation)
                corr.append(f"alert:{aid}")

                items.append(
                    Evidence(
                        investigation_id=context.investigation_id,
                        execution_id=context.execution_id,
                        source="monitoring",
                        source_type=EvidenceSource.MONITORING,
                        evidence_type=EvidenceType.ALERT,
                        timestamp=ts,
                        timestamp_type=ts_type,
                        title=f"Alert [{sev}]: {aname}",
                        summary=msg[:120],
                        data=safe_alert,
                        provenance=EvidenceProvenance(
                            agent_id=result.agent_id,
                            source="monitoring",
                            collected_at=collected_at,
                            source_reference=f"monitoring://{service_name}/alert/{aid}",
                            original_id=aid,
                        ),
                        quality=EvidenceQuality(
                            source_reliability=SourceReliability.HIGH,
                            timestamp_quality=ts_type,
                        ),
                        correlation_identifiers=corr,
                        warnings=ts_warnings,
                        dedup_key=f"monitoring:alert:{service_name}:{aid}:{ts.isoformat()}",
                    )
                )

        return items

    def _normalize_generic(
        self,
        result: AgentResult,
        context: InvestigationContext,
        collected_at: datetime,
    ) -> list[Evidence]:
        """Normalize generic or mock agent outputs into fallback evidence items."""
        truncated: list[str] = []
        safe_data = self._sanitize_and_bound_data(result.data, truncated)
        data_hash = hashlib.sha256(json.dumps(safe_data, default=str, sort_keys=True).encode()).hexdigest()[:12]

        return [
            Evidence(
                investigation_id=context.investigation_id,
                execution_id=context.execution_id,
                source=result.source or result.agent_id,
                source_type=EvidenceSource.GENERIC,
                evidence_type=EvidenceType.GENERIC,
                timestamp=collected_at,
                timestamp_type=TimestampType.COLLECTION,
                title=f"Operational Evidence: {result.agent_id}",
                summary=f"Collected operational data from {result.agent_id}",
                data=safe_data,
                provenance=EvidenceProvenance(
                    agent_id=result.agent_id,
                    source=result.source or result.agent_id,
                    collected_at=collected_at,
                    source_reference=f"agent://{result.agent_id}",
                ),
                quality=EvidenceQuality(
                    source_reliability=SourceReliability.MEDIUM,
                    timestamp_quality=TimestampType.COLLECTION,
                ),
                correlation_identifiers=[f"agent:{result.agent_id}"],
                warnings=list(result.warnings),
                dedup_key=f"generic:{result.agent_id}:{data_hash}",
            )
        ]
