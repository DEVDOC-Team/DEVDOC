"""Operational orchestrator factory for DEVDOC investigations.

Wires available operational agents, LLM reasoning, knowledge search, root-cause
analysis, fix generation, sandbox verification, and human approval gating into
a strongly typed, deterministic DEVDOCOrchestrator pipeline.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path

from app.core.config import Settings
from app.core.config import settings as default_settings
from app.core.github_client import GitHubAPIClient
from orchestrator.agents.docker_agent import DockerAgent
from orchestrator.agents.docker_inspector import DockerInspector
from orchestrator.agents.github_agent import GitHubAgent
from orchestrator.agents.monitoring_agent import MonitoringAgent
from orchestrator.agents.monitoring_provider import MonitoringProvider
from orchestrator.contracts.execution import WorkflowDefinition
from orchestrator.core.context import InvestigationContext
from orchestrator.core.orchestrator import DEVDOCOrchestrator
from orchestrator.fixes.models import FixProposal
from orchestrator.fixes.service import FixGeneratorService
from orchestrator.knowledge.factory import create_tavily_knowledge_search_service
from orchestrator.knowledge.service import KnowledgeSearchService
from orchestrator.llm.factory import create_nebius_llm_service
from orchestrator.llm.service import LLMService
from orchestrator.rca.service import RootCauseAnalysisService
from orchestrator.sandbox.contracts import SandboxProvider
from orchestrator.sandbox.models import VerificationCommand
from orchestrator.sandbox.service import SandboxVerificationService
from orchestrator.stages.investigation import (
    create_default_workflow,
    create_operational_stage_registry,
)

logger = logging.getLogger("devdoc.orchestrator.factory")


def create_operational_orchestrator(
    config: Settings | None = None,
    *,
    github_client: GitHubAPIClient | None = None,
    github_access_token: str | None = None,
    docker_inspector: DockerInspector | None = None,
    monitoring_provider: MonitoringProvider | None = None,
    llm_service: LLMService | None = None,
    knowledge_search_service: KnowledgeSearchService | None = None,
    rca_service: RootCauseAnalysisService | None = None,
    fix_generator_service: FixGeneratorService | None = None,
    sandbox_provider: SandboxProvider | None = None,
    sandbox_verification_service: SandboxVerificationService | None = None,
    sandbox_workspace_resolver: (
        Callable[
            [InvestigationContext, FixProposal],
            Awaitable[str | Path | None],
        ]
        | None
    ) = None,
    verification_commands: Sequence[VerificationCommand] = (),
    approval_artifact_recorder: (
        Callable[[InvestigationContext], Awaitable[uuid.UUID]] | None
    ) = None,
    workflow: WorkflowDefinition | None = None,
) -> DEVDOCOrchestrator:
    """Construct an operational DEVDOCOrchestrator with verified, available dependencies.

    Guarantees:
    1. Operational agents (GitHub, Docker, Monitoring) are only wired when valid clients,
       credentials, or providers are explicitly available.
    2. Phase 13 LLM reasoning is only initialized when explicitly opted in and budget-configured.
    3. Phase 14 knowledge search is only initialized when explicitly enabled and keyed.
    4. RCA (Phase 15) and Fix Generation (Phase 16) are wired only when an LLM service is available.
    5. Sandbox verification (Phase 17) is wired only when a sandbox provider is supplied.
    6. Human approval (Phase 18) remains a mandatory human gate; no automatic remediation occurs.
    7. Unconfigured or disabled capabilities degrade cleanly with typed statuses, never fabricating results.
    """
    cfg = config or default_settings

    # 1. Operational agents — wire only when credentials/providers are available
    github_agent: GitHubAgent | None = None
    if github_client is not None or github_access_token is not None:
        github_agent = GitHubAgent(
            client=github_client,
            access_token=github_access_token,
        )

    docker_agent: DockerAgent | None = None
    if docker_inspector is not None:
        docker_agent = DockerAgent(inspector=docker_inspector)

    monitoring_agent: MonitoringAgent | None = None
    if monitoring_provider is not None:
        monitoring_agent = MonitoringAgent(provider=monitoring_provider)

    # 2. Knowledge Search service (Phase 14)
    resolved_knowledge_search = knowledge_search_service
    if resolved_knowledge_search is None and cfg.knowledge_search_enabled:
        try:
            resolved_knowledge_search = create_tavily_knowledge_search_service(cfg)
        except Exception as exc:
            logger.warning(
                "Knowledge search enabled but initialization failed: %s; proceeding in degraded mode",
                exc,
            )
            resolved_knowledge_search = None

    # 3. LLM service (Phase 13)
    resolved_llm = llm_service
    if resolved_llm is None and cfg.llm_enabled:
        try:
            resolved_llm = create_nebius_llm_service(cfg)
        except Exception as exc:
            logger.warning(
                "LLM reasoning enabled but initialization failed: %s; proceeding in degraded mode",
                exc,
            )
            resolved_llm = None

    # 4. RCA (Phase 15) & Fix Generator (Phase 16) — require LLM service
    resolved_rca = rca_service
    if resolved_rca is None and resolved_llm is not None:
        resolved_rca = RootCauseAnalysisService(llm_service=resolved_llm)

    resolved_fixes = fix_generator_service
    if resolved_fixes is None and resolved_llm is not None:
        resolved_fixes = FixGeneratorService(llm_service=resolved_llm)

    # 5. Sandbox verification (Phase 17)
    resolved_sandbox = sandbox_verification_service
    if resolved_sandbox is None and sandbox_provider is not None:
        resolved_sandbox = SandboxVerificationService(provider=sandbox_provider)

    # 6. Build the operational stage registry
    registry = create_operational_stage_registry(
        github_agent=github_agent,
        docker_agent=docker_agent,
        monitoring_agent=monitoring_agent,
        llm_service=resolved_llm,
        knowledge_search_service=resolved_knowledge_search,
        rca_service=resolved_rca,
        fix_generator_service=resolved_fixes,
        sandbox_verification_service=resolved_sandbox,
        sandbox_workspace_resolver=sandbox_workspace_resolver,
        verification_commands=verification_commands,
        approval_artifact_recorder=approval_artifact_recorder,
    )

    resolved_workflow = workflow or create_default_workflow()
    return DEVDOCOrchestrator(registry=registry, workflow=resolved_workflow)
