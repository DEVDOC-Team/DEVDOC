"""Investigation context.

Carries the strongly typed state, evidence references, metadata, and lifecycle
checkpoints throughout an investigation execution run. Enforces strict secret prevention
and controlled mutation.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from orchestrator.core.errors import ContextValidationError

if TYPE_CHECKING:
    from orchestrator.evidence.models import EvidenceCollection
    from orchestrator.fixes.models import FixProposal
    from orchestrator.rca.models import RootCauseAnalysis
    from orchestrator.sandbox.models import SandboxVerificationResult

# Disallowed keys to prevent accidental secret leakage into context
FORBIDDEN_KEY_PATTERNS = {
    "token",
    "password",
    "secret",
    "api_key",
    "apikey",
    "private_key",
    "auth_token",
    "authorization",
    "bearer",
}


class CancellationToken:
    """Thread-safe cooperative cancellation token for investigation runs."""

    def __init__(self) -> None:
        self._is_cancelled = False
        self._reason: str | None = None

    @property
    def is_cancelled(self) -> bool:
        return self._is_cancelled

    @property
    def reason(self) -> str | None:
        return self._reason

    def cancel(self, reason: str | None = None) -> None:
        """Signal cancellation to all cooperating stages and agents."""
        self._is_cancelled = True
        self._reason = reason or "Cancellation requested by user or system"


@dataclass
class InvestigationContext:
    """Strongly typed execution context for an investigation run.

    Guarantees:
    - Mandatory project, incident, and investigation IDs.
    - Clean per-run execution ID.
    - Zero secret or raw credential storage.
    - Audit tracking of stage transitions, evidence references, and warnings.
    """

    investigation_id: uuid.UUID
    incident_id: uuid.UUID
    project_id: uuid.UUID
    initiated_by_id: uuid.UUID | None = None
    execution_id: uuid.UUID = field(default_factory=uuid.uuid4)
    current_stage: str | None = None
    execution_metadata: dict[str, Any] = field(default_factory=dict)
    collected_evidence_references: list[dict[str, Any]] = field(default_factory=list)
    agent_outputs: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    execution_timestamps: dict[str, datetime] = field(default_factory=dict)
    evidence_collection: EvidenceCollection | None = None
    root_cause_analysis: RootCauseAnalysis | None = None
    fix_proposal: FixProposal | None = None
    sandbox_verification_result: SandboxVerificationResult | None = None
    cancellation_token: CancellationToken = field(default_factory=CancellationToken)

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        """Validate required context identifiers and absence of sensitive keys.

        Raises:
            ContextValidationError: If any identifier is missing/invalid or contains secrets.
        """
        if not isinstance(self.investigation_id, uuid.UUID):
            raise ContextValidationError(
                "investigation_id must be a valid UUID", invalid_field="investigation_id"
            )
        if not isinstance(self.incident_id, uuid.UUID):
            raise ContextValidationError(
                "incident_id must be a valid UUID", invalid_field="incident_id"
            )
        if not isinstance(self.project_id, uuid.UUID):
            raise ContextValidationError(
                "project_id must be a valid UUID", invalid_field="project_id"
            )
        if not isinstance(self.execution_id, uuid.UUID):
            raise ContextValidationError(
                "execution_id must be a valid UUID", invalid_field="execution_id"
            )
        if self.initiated_by_id is not None and not isinstance(self.initiated_by_id, uuid.UUID):
            raise ContextValidationError(
                "initiated_by_id must be a UUID or None", invalid_field="initiated_by_id"
            )

        # Enforce no secret storage in metadata
        self._check_secrets_recursive(self.execution_metadata, "execution_metadata")
        self._check_secrets_recursive(self.agent_outputs, "agent_outputs")

    def _check_secrets_recursive(self, obj: Any, path: str) -> None:
        """Scan keys recursively to prevent storing raw credentials or tokens."""
        if isinstance(obj, dict):
            for k, v in obj.items():
                k_lower = str(k).lower()
                for pattern in FORBIDDEN_KEY_PATTERNS:
                    if pattern in k_lower:
                        raise ContextValidationError(
                            f"Sensitive key '{k}' detected at '{path}'. Storing credentials in context is prohibited.",
                            invalid_field=path,
                        )
                self._check_secrets_recursive(v, f"{path}.{k}")
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                self._check_secrets_recursive(item, f"{path}[{i}]")

    def is_cancelled(self) -> bool:
        """Check whether execution has been requested to cancel."""
        return self.cancellation_token.is_cancelled

    def cancel(self, reason: str | None = None) -> None:
        """Trigger cancellation for this context."""
        self.cancellation_token.cancel(reason)

    def record_stage_start(self, stage_id: str) -> None:
        """Record the start of a stage with timestamp and current_stage marker."""
        self.current_stage = stage_id
        now = datetime.now(UTC)
        self.execution_timestamps[f"{stage_id}_start"] = now

    def record_stage_complete(self, stage_id: str) -> None:
        """Record the completion of a stage with timestamp."""
        now = datetime.now(UTC)
        self.execution_timestamps[f"{stage_id}_end"] = now

    def add_warning(self, warning: str) -> None:
        """Append an operational warning."""
        if warning and warning not in self.warnings:
            self.warnings.append(warning)

    def add_error(self, error: str) -> None:
        """Append an error message."""
        if error and error not in self.errors:
            self.errors.append(error)

    def add_evidence_reference(self, ref: dict[str, Any] | str) -> None:
        """Safely register an evidence reference (metadata only, no raw data/secrets)."""
        ref_dict = {"reference_id": ref} if isinstance(ref, str) else dict(ref)
        self._check_secrets_recursive(ref_dict, "evidence_reference")
        self.collected_evidence_references.append(ref_dict)

    def record_agent_output(self, agent_id: str, output: Any) -> None:
        """Safely record an agent's output metadata."""
        self._check_secrets_recursive(output, f"agent_output.{agent_id}")
        self.agent_outputs[agent_id] = output

    def to_dict(self) -> dict[str, Any]:
        """Produce a sanitized dictionary representation of the context."""
        return {
            "execution_id": str(self.execution_id),
            "investigation_id": str(self.investigation_id),
            "incident_id": str(self.incident_id),
            "project_id": str(self.project_id),
            "initiated_by_id": str(self.initiated_by_id) if self.initiated_by_id else None,
            "current_stage": self.current_stage,
            "execution_metadata": self.execution_metadata,
            "collected_evidence_references": self.collected_evidence_references,
            "agent_outputs": self.agent_outputs,
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "execution_timestamps": {
                k: v.isoformat() for k, v in self.execution_timestamps.items()
            },
            "is_cancelled": self.is_cancelled(),
            "sandbox_verification_result": (
                self.sandbox_verification_result.model_dump(mode="json")
                if self.sandbox_verification_result is not None
                else None
            ),
        }
