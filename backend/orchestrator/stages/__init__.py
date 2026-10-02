"""Investigation stages and stage registry."""

from __future__ import annotations

from orchestrator.stages.investigation import (
    AnalyzeStage,
    CollectEvidenceStage,
    CompleteStage,
    DiagnoseStage,
    InitializeStage,
    ProposeFixStage,
    VerifyStage,
    create_default_stage_registry,
    create_default_workflow,
    create_operational_stage_registry,
)
from orchestrator.stages.registry import StageRegistry

__all__ = [
    "AnalyzeStage",
    "CollectEvidenceStage",
    "CompleteStage",
    "DiagnoseStage",
    "InitializeStage",
    "ProposeFixStage",
    "StageRegistry",
    "VerifyStage",
    "create_default_stage_registry",
    "create_default_workflow",
    "create_operational_stage_registry",
]
