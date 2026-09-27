"""DEVDOC models package.

Import all models here so Alembic's env.py can discover metadata
by importing a single symbol: ``from app.models import Base``.

Phase 3: enums are also exported for use in Pydantic schemas and API
response serialisation in later phases.
"""

from app.db.base import Base
from app.models.approval import Approval, ApprovalDecision
from app.models.audit_log import AuditLog, AuditOutcome
from app.models.deployment import Deployment, DeploymentStatus
from app.models.evidence import Evidence, EvidenceKind
from app.models.fix_proposal import FixProposal, FixStatus
from app.models.github_connection import UserGitHubConnection
from app.models.incident import Incident, IncidentSeverity, IncidentSource, IncidentStatus
from app.models.investigation import Investigation, InvestigationStatus
from app.models.project import Project
from app.models.repository import Repository, VCSProvider
from app.models.user import User

__all__ = [
    # Base
    "Base",
    # Models
    "User",
    "UserGitHubConnection",
    "Project",
    "Repository",
    "Incident",
    "Investigation",
    "Evidence",
    "Deployment",
    "FixProposal",
    "Approval",
    "AuditLog",
    # Enums
    "VCSProvider",
    "IncidentSeverity",
    "IncidentSource",
    "IncidentStatus",
    "InvestigationStatus",
    "EvidenceKind",
    "DeploymentStatus",
    "FixStatus",
    "ApprovalDecision",
    "AuditOutcome",
]


