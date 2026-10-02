"""Tests for StageRegistry and stage lookup."""

from __future__ import annotations

import pytest

from orchestrator.contracts.stage import BaseStage, StageIdentifier
from orchestrator.core.context import InvestigationContext
from orchestrator.core.errors import DuplicateStageError, StageNotFoundError
from orchestrator.core.result import ExecutionStatus, StageResult
from orchestrator.stages.investigation import (
    InitializeStage,
    create_default_stage_registry,
)
from orchestrator.stages.registry import StageRegistry


class DummyStage(BaseStage):
    def __init__(self, sid: str, name: str = "Dummy") -> None:
        self._id = sid
        self._name = name

    @property
    def stage_id(self) -> str:
        return self._id

    @property
    def name(self) -> str:
        return self._name

    async def execute(self, context: InvestigationContext) -> StageResult:
        return StageResult(stage_id=self.stage_id, status=ExecutionStatus.SUCCESS)


def test_registry_initialization_empty() -> None:
    reg = StageRegistry()
    assert len(reg) == 0
    assert reg.list() == []


def test_registry_initialization_with_stages() -> None:
    s1 = DummyStage("s1")
    s2 = DummyStage("s2")
    reg = StageRegistry([s1, s2])
    assert len(reg) == 2
    assert reg.get("s1") is s1
    assert reg.get("s2") is s2


def test_stage_registration() -> None:
    reg = StageRegistry()
    stage = InitializeStage()
    reg.register(stage)

    assert len(reg) == 1
    assert reg.contains("initialize")
    assert "initialize" in reg
    assert reg.get("initialize") is stage


def test_duplicate_stage_registration_rejected() -> None:
    reg = StageRegistry()
    reg.register(InitializeStage())

    with pytest.raises(DuplicateStageError) as exc:
        reg.register(InitializeStage())
    assert "already registered" in str(exc.value)
    assert exc.value.stage_id == "initialize"


def test_empty_stage_id_rejected() -> None:
    reg = StageRegistry()
    dummy = DummyStage("")
    with pytest.raises(ValueError) as exc:
        reg.register(dummy)
    assert "must be a non-empty string" in str(exc.value)


def test_stage_lookup_success() -> None:
    reg = StageRegistry()
    dummy = DummyStage("collect_custom")
    reg.register(dummy)
    retrieved = reg.get("collect_custom")
    assert retrieved is dummy


def test_unknown_stage_detection() -> None:
    reg = StageRegistry()
    with pytest.raises(StageNotFoundError) as exc:
        reg.get("non_existent_stage")
    assert "was not found in the registry" in str(exc.value)
    assert exc.value.stage_id == "non_existent_stage"


def test_registry_list_deterministic_ordering() -> None:
    reg = StageRegistry()
    stages = [
        DummyStage("first"),
        DummyStage("second"),
        DummyStage("third"),
    ]
    for s in stages:
        reg.register(s)

    listed = reg.list()
    assert [s.stage_id for s in listed] == ["first", "second", "third"]


def test_registry_unregister() -> None:
    reg = StageRegistry()
    s = DummyStage("temp")
    reg.register(s)
    assert reg.contains("temp")

    reg.unregister("temp")
    assert not reg.contains("temp")
    assert len(reg) == 0

    with pytest.raises(StageNotFoundError):
        reg.unregister("temp")


def test_default_stage_registry_factory() -> None:
    reg = create_default_stage_registry()
    expected_stages = [
        StageIdentifier.INITIALIZE.value,
        StageIdentifier.COLLECT.value,
        StageIdentifier.ANALYZE.value,
        StageIdentifier.DIAGNOSE.value,
        StageIdentifier.PROPOSE.value,
        StageIdentifier.VERIFY.value,
        StageIdentifier.COMPLETE.value,
    ]
    assert len(reg) == 7
    for sid in expected_stages:
        assert reg.contains(sid)
        stage = reg.get(sid)
        assert stage.stage_id == sid
        assert stage.name
