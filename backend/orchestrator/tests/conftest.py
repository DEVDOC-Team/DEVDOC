"""Pytest configuration for orchestrator test suite."""

from __future__ import annotations

import sys
from pathlib import Path

# Add backend directory to sys.path so 'orchestrator' and 'app' packages are discoverable
BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
