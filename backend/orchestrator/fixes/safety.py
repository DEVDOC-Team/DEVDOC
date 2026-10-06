"""Deterministic validation of generated Phase 16 proposal content."""

from __future__ import annotations

import re
import uuid
from pathlib import PurePosixPath, PureWindowsPath

from pydantic import BaseModel

from orchestrator.core.sanitizer import sanitize_string
from orchestrator.evidence.models import Evidence, EvidenceSource, EvidenceType
from orchestrator.fixes.models import (
    FixChangeType,
    FixCompletion,
    FixRisk,
    FixRiskSeverity,
)
from orchestrator.rca.models import CandidateRootCause, EvidenceClassification

_DESTRUCTIVE_PATTERNS = (
    re.compile(r"\brm\s+-[^\r\n]*r[^\r\n]*f\b", re.IGNORECASE),
    re.compile(r"\b(?:DROP\s+(?:DATABASE|TABLE|SCHEMA)|TRUNCATE\s+TABLE)\b", re.IGNORECASE),
    re.compile(r"\bterraform\s+destroy\b", re.IGNORECASE),
    re.compile(r"\bkubectl\s+delete\b", re.IGNORECASE),
    re.compile(r"\bdocker(?:\s+container)?\s+rm\b", re.IGNORECASE),
    re.compile(r"\bdocker\s+compose\s+down\b", re.IGNORECASE),
    re.compile(r"\bhelm\s+uninstall\b", re.IGNORECASE),
    re.compile(
        r"\bdelete\s+(?:all\s+)?(?:production|prod)\s+(?:data|records?)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bDELETE\s+FROM\s+[A-Za-z0-9_.\[\]]+", re.IGNORECASE),
)
_PATCH_PATH_PATTERN = re.compile(r"^(---|\+\+\+)\s+(\S+)")
_SEVERITY_RANK = {
    FixRiskSeverity.LOW: 0,
    FixRiskSeverity.MEDIUM: 1,
    FixRiskSeverity.HIGH: 2,
    FixRiskSeverity.CRITICAL: 3,
    FixRiskSeverity.UNKNOWN: 4,
}


class FixSafetyError(ValueError):
    """Generated content failed a bounded, deterministic safety check."""


def normalize_repository_path(path: str) -> str:
    """Accept only canonical repository-relative POSIX paths."""
    if (
        not path
        or "\x00" in path
        or "\\" in path
        or ":" in path
        or path.startswith("/")
        or PureWindowsPath(path).is_absolute()
        or PureWindowsPath(path).drive
    ):
        raise FixSafetyError("Proposal contains an unsafe repository path")
    parsed = PurePosixPath(path)
    if not parsed.parts or any(part in {"", ".", ".."} for part in parsed.parts):
        raise FixSafetyError("Proposal contains an unsafe repository path")
    normalized = parsed.as_posix()
    if normalized != path:
        raise FixSafetyError("Proposal contains a non-canonical repository path")
    return normalized


def validate_fix_completion(
    completion: FixCompletion,
    *,
    root_cause: CandidateRootCause,
    evidence_by_id: dict[uuid.UUID, Evidence],
    known_repository_paths: set[str],
    production_context: bool = False,
) -> FixCompletion:
    """Validate evidence, file targets, secrets, patch bounds, and minimum risk."""
    if completion.root_cause_reference != root_cause.candidate_id:
        raise FixSafetyError("Proposal referenced a root cause outside the active RCA")

    if _contains_secret(completion):
        raise FixSafetyError("Generated proposal contained sensitive data")
    if _contains_destructive_operation(completion):
        raise FixSafetyError("Generated proposal contained a destructive operation")

    root_support_ids = {
        reference.evidence_id
        for reference in root_cause.supporting_evidence
        if reference.classification == EvidenceClassification.FACT
    }
    cited_fact_ids: set[uuid.UUID] = set()
    for evidence_id in completion.evidence_references:
        evidence = evidence_by_id.get(evidence_id)
        if evidence is None or _is_external(evidence):
            raise FixSafetyError("Proposal referenced unsupported observed evidence")
        cited_fact_ids.add(evidence_id)
    if not cited_fact_ids.intersection(root_support_ids):
        raise FixSafetyError("Proposal did not cite observed evidence supporting the RCA")

    for evidence_id in completion.external_knowledge_references:
        evidence = evidence_by_id.get(evidence_id)
        if evidence is None or not _is_external(evidence):
            raise FixSafetyError("Proposal referenced invalid external knowledge")

    all_patch_files: set[str] = set()
    total_patch_lines = 0
    for change in completion.changes:
        change_fact_ids: set[uuid.UUID] = set()
        for evidence_id in change.evidence_references:
            evidence = evidence_by_id.get(evidence_id)
            if evidence is None or _is_external(evidence):
                raise FixSafetyError("A proposed change lacks valid observed evidence")
            change_fact_ids.add(evidence_id)
        if not change_fact_ids.intersection(root_support_ids):
            raise FixSafetyError("A proposed change is not linked to the selected RCA")

        target_path = change.target_path
        if target_path is not None:
            normalized = normalize_repository_path(target_path)
            if normalized not in known_repository_paths:
                raise FixSafetyError("Proposal targeted a repository path not verified by evidence")

        if (
            change.target in known_repository_paths
            or "/" in change.target
            or "\\" in change.target
            or bool(PurePosixPath(change.target).suffix)
        ):
            normalized_target = normalize_repository_path(change.target)
            if normalized_target not in known_repository_paths:
                raise FixSafetyError("Proposal targeted a repository path not verified by evidence")

        if change.proposed_diff is not None:
            if change.patch_status != "PROPOSED / UNVERIFIED":
                raise FixSafetyError("Generated patch was not marked proposed and unverified")
            patch_files, patch_lines = _validate_patch(
                change.proposed_diff,
                target_path,
                known_repository_paths,
            )
            all_patch_files.update(patch_files)
            total_patch_lines += patch_lines
    if len(all_patch_files) > 5 or total_patch_lines > 200:
        raise FixSafetyError("Generated proposal exceeded file or line limits")

    return _enforce_minimum_risk(completion, production_context=production_context)


def _validate_patch(
    patch: str,
    target_path: str | None,
    known_repository_paths: set[str],
) -> tuple[set[str], int]:
    if not target_path or len(patch.encode("utf-8")) > 20_000:
        raise FixSafetyError("Generated patch exceeded safety bounds")
    if "\x00" in patch or "GIT binary patch" in patch:
        raise FixSafetyError("Generated patch contained unsupported binary content")

    files: set[str] = set()
    has_old_header = False
    has_new_header = False
    changed_lines = 0
    for line in patch.splitlines():
        if line.startswith("--- "):
            has_old_header = True
        elif line.startswith("+++ "):
            has_new_header = True
        else:
            if line.startswith(("+", "-")):
                changed_lines += 1
            continue
        match = _PATCH_PATH_PATTERN.match(line)
        if match is None:
            raise FixSafetyError("Generated patch contained an invalid file header")
        path = match.group(2).split("\t", maxsplit=1)[0]
        if path == "/dev/null":
            continue
        prefix = "a/" if match.group(1) == "---" else "b/"
        if not path.startswith(prefix):
            raise FixSafetyError("Generated patch contained a non-canonical file header")
        normalized = normalize_repository_path(path[len(prefix) :])
        if normalized not in known_repository_paths:
            raise FixSafetyError("Generated patch targeted a file not verified by evidence")
        files.add(normalized)

    if not has_old_header or not has_new_header or not files or target_path not in files:
        raise FixSafetyError("Generated patch did not match its verified target")
    return files, changed_lines


def _contains_secret(value: object) -> bool:
    if isinstance(value, str):
        return sanitize_string(value) != value
    if isinstance(value, BaseModel):
        return any(_contains_secret(item) for item in value.model_dump().values())
    if isinstance(value, dict):
        return any(_contains_secret(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_secret(item) for item in value)
    return False


def _contains_destructive_operation(value: object) -> bool:
    if isinstance(value, str):
        return any(pattern.search(value) is not None for pattern in _DESTRUCTIVE_PATTERNS)
    if isinstance(value, BaseModel):
        return any(_contains_destructive_operation(item) for item in value.model_dump().values())
    if isinstance(value, dict):
        return any(_contains_destructive_operation(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_destructive_operation(item) for item in value)
    return False


def _is_external(evidence: Evidence) -> bool:
    return (
        evidence.source_type == EvidenceSource.EXTERNAL_KNOWLEDGE
        or evidence.evidence_type == EvidenceType.EXTERNAL_KNOWLEDGE
    )


def _enforce_minimum_risk(
    completion: FixCompletion,
    *,
    production_context: bool,
) -> FixCompletion:
    required = FixRiskSeverity.LOW
    if completion.change_type == FixChangeType.UNKNOWN:
        required = FixRiskSeverity.UNKNOWN
    if completion.change_type in {
        FixChangeType.DATABASE_CHANGE,
        FixChangeType.DEPENDENCY_CHANGE,
        FixChangeType.INFRASTRUCTURE_CHANGE,
        FixChangeType.DEPLOYMENT_CHANGE,
    }:
        required = FixRiskSeverity.HIGH
    if (
        production_context
        and completion.change_type == FixChangeType.CONFIGURATION_CHANGE
        and _SEVERITY_RANK[required] < _SEVERITY_RANK[FixRiskSeverity.HIGH]
    ):
        required = FixRiskSeverity.HIGH
    if any(
        "security" in text.lower()
        for text in (
            completion.summary,
            completion.rationale,
            *(change.target + " " + change.operation for change in completion.changes),
        )
    ):
        required = FixRiskSeverity.CRITICAL

    maximum = max(completion.risks, key=lambda risk: _SEVERITY_RANK[risk.severity])
    if _SEVERITY_RANK[maximum.severity] >= _SEVERITY_RANK[required]:
        return completion
    risks = list(completion.risks)
    index = risks.index(maximum)
    risks[index] = maximum.model_copy(update={"severity": required})
    return completion.model_copy(update={"risks": risks})


def risk_requires_human_review(risks: list[FixRisk]) -> bool:
    return any(
        risk.severity
        in {
            FixRiskSeverity.HIGH,
            FixRiskSeverity.CRITICAL,
            FixRiskSeverity.UNKNOWN,
        }
        for risk in risks
    )
