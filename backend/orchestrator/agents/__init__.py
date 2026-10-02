"""Orchestrator agents package."""

from __future__ import annotations

from orchestrator.agents.base import MockInvestigationAgent
from orchestrator.contracts.agent import BaseAgent

__all__ = [
    "BaseAgent",
    "MockInvestigationAgent",
]
