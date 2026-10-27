"""Tests for Phase 12 multi-modal evidence processing."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import pytest

from orchestrator.core.context import InvestigationContext
from orchestrator.core.result import AgentResult, ExecutionStatus
from orchestrator.evidence.config import EvidenceEngineConfig, EvidenceLimitsConfig
from orchestrator.evidence.engine import EvidenceEngine
from orchestrator.stages.investigation import CollectEvidenceStage


def make_context() -> InvestigationContext:
    return InvestigationContext(
        investigation_id=uuid.uuid4(),
        incident_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
    )


def test_engine_normalizes_sources_and_builds_timeline_and_graph() -> None:
    context = make_context()
    results = [
        AgentResult(
            agent_id="github_agent",
            source="github",
            status=ExecutionStatus.SUCCESS,
            investigation_id=context.investigation_id,
            execution_id=context.execution_id,
            collected_at=datetime(2026, 10, 5, 10, 10, tzinfo=UTC),
            data={
                "repository": {"full_name": "acme/api", "default_branch": "main"},
                "commits": [
                    {
                        "sha": "abc123",
                        "message": "Fix service",
                        "author": {"name": "Dev", "date": "2026-10-05T10:00:00Z"},
                    }
                ],
            },
        ),
        AgentResult(
            agent_id="docker_agent",
            source="docker",
            status=ExecutionStatus.SUCCESS,
            investigation_id=context.investigation_id,
            execution_id=context.execution_id,
            collected_at=datetime(2026, 10, 5, 10, 11, tzinfo=UTC),
            data={
                "containers": [
                    {
                        "id": "container-123456",
                        "names": ["/api"],
                        "image": "api:v1",
                        "state": {"status": "exited", "finished_at": "2026-10-05T10:05:00Z"},
                        "logs": "request failed",
                    }
                ]
            },
        ),
        AgentResult(
            agent_id="monitoring_agent",
            source="monitoring",
            status=ExecutionStatus.SUCCESS,
            investigation_id=context.investigation_id,
            execution_id=context.execution_id,
            collected_at=datetime(2026, 10, 5, 10, 12, tzinfo=UTC),
            data={
                "service": "api",
                "health": {
                    "status": "degraded",
                    "message": "High latency",
                    "checked_at": "2026-10-05T10:06:00Z",
                },
                "metrics": {
                    "collected_at": "2026-10-05T10:07:00Z",
                    "metrics": {"latency_p99_ms": 900},
                },
                "alerts": [
                    {
                        "alert_id": "latency-1",
                        "name": "High latency",
                        "triggered_at": "2026-10-05T10:08:00Z",
                    }
                ],
            },
        ),
    ]

    collection = EvidenceEngine().process(results, context)

    assert collection.summary.counts_by_source == {
        "docker": 2,
        "github": 2,
        "monitoring": 3,
    }
    assert collection.summary.total_evidence_count == 7
    assert [event.timestamp for event in collection.timeline] == sorted(
        event.timestamp for event in collection.timeline
    )
    assert any(
        relationship.shared_identifier == "service:api" for relationship in collection.correlations
    )
    assert collection.summary.correlation_count == len(collection.correlations)
    assert collection.to_dict()["evidence_count"] == 7


def test_engine_deduplicates_and_records_duplicate_count() -> None:
    context = make_context()
    data = {"finding": "same observation"}
    results = [
        AgentResult(
            agent_id="observer", source="custom", status=ExecutionStatus.SUCCESS, data=data
        ),
        AgentResult(
            agent_id="observer", source="custom", status=ExecutionStatus.SUCCESS, data=data
        ),
    ]

    collection = EvidenceEngine().process(results, context)

    assert collection.summary.total_evidence_count == 1
    assert collection.summary.duplicate_count == 1
    assert collection.items[0].provenance.metadata["duplicate_occurrences"] == 2


def test_engine_rejects_cross_execution_results() -> None:
    context = make_context()
    result = AgentResult(
        agent_id="foreign_agent",
        status=ExecutionStatus.SUCCESS,
        investigation_id=uuid.uuid4(),
        execution_id=context.execution_id,
        data={"finding": "must not cross investigation boundaries"},
    )

    collection = EvidenceEngine().process([result], context)

    assert collection.items == []
    assert collection.summary.validation_failure_count == 1
    assert "mismatched execution identifiers" in collection.warnings[0]


def test_engine_enforces_item_limit() -> None:
    context = make_context()
    config = EvidenceEngineConfig(
        limits=EvidenceLimitsConfig(
            max_evidence_items=1,
            max_correlation_relationships=1,
        )
    )
    results = [
        AgentResult(
            agent_id=f"observer-{index}",
            source="custom",
            status=ExecutionStatus.SUCCESS,
            data={"service": "api", "finding": str(index)},
        )
        for index in range(3)
    ]

    collection = EvidenceEngine(config).process(results, context)

    assert len(collection.items) == 1
    assert collection.summary.total_evidence_count == 1
    assert any("item limit" in warning for warning in collection.warnings)


def test_engine_enforces_relationship_limit() -> None:
    context = make_context()
    config = EvidenceEngineConfig(
        limits=EvidenceLimitsConfig(
            max_evidence_items=10,
            max_correlation_relationships=1,
        )
    )
    collected_at = datetime(2026, 10, 5, 10, 0, tzinfo=UTC)
    results = [
        AgentResult(
            agent_id=f"observer-{index}",
            source="custom",
            status=ExecutionStatus.SUCCESS,
            collected_at=collected_at,
            data={"finding": str(index)},
        )
        for index in range(3)
    ]

    collection = EvidenceEngine(config).process(results, context)

    assert len(collection.correlations) == 1
    assert any("relationship limit" in warning for warning in collection.warnings)


def test_engine_enforces_aggregate_collection_size() -> None:
    context = make_context()
    config = EvidenceEngineConfig(
        limits=EvidenceLimitsConfig(
            max_evidence_items=10,
            max_collection_bytes=1_000,
        )
    )
    results = [
        AgentResult(
            agent_id=f"observer-{index}",
            source="custom",
            status=ExecutionStatus.SUCCESS,
            data={"finding": "x" * 100},
        )
        for index in range(3)
    ]

    collection = EvidenceEngine(config).process(results, context)

    assert len(collection.items) < len(results)
    assert collection.metadata["collection_payload_bytes"] <= 1_000
    assert any("collection size limit" in warning for warning in collection.warnings)


def test_engine_redacts_free_text_and_marks_bounded_payloads() -> None:
    context = make_context()
    config = EvidenceEngineConfig(
        limits=EvidenceLimitsConfig(
            max_source_records_per_agent=2,
            max_string_length=64,
        )
    )
    result = AgentResult(
        agent_id="observer",
        source="custom",
        status=ExecutionStatus.SUCCESS,
        data={
            "message": "token=ghp_1234567890abcdefghijklmnopqrstuvwxyzAB",
            "samples": ["first", "second", "third"],
        },
    )

    collection = EvidenceEngine(config).process([result], context)

    serialized = json.dumps(collection.to_dict())
    assert "ghp_1234567890abcdefghijklmnopqrstuvwxyzAB" not in serialized
    assert "[REDACTED]" in serialized
    assert "[TRUNCATED]" in serialized
    assert any("truncated" in warning.lower() for warning in collection.warnings)


@pytest.mark.asyncio
async def test_collect_stage_exposes_processed_evidence() -> None:
    context = make_context()

    class SuccessfulAgent:
        identifier = "observer_agent"

        async def execute(self, execution_context: InvestigationContext) -> AgentResult:
            return AgentResult(
                agent_id=self.identifier,
                status=ExecutionStatus.SUCCESS,
                investigation_id=execution_context.investigation_id,
                execution_id=execution_context.execution_id,
                source="custom",
                data={"finding": "observed"},
            )

    agent = SuccessfulAgent()
    stage = CollectEvidenceStage(agents=[agent])

    result = await stage.execute(context)

    assert result.evidence_collection is not None
    assert result.evidence_collection["evidence_count"] == 1
    assert result.output_metadata["evidence_item_count"] == 1
    assert result.to_dict()["evidence_collection"]["summary"]["total_evidence_count"] == 1
