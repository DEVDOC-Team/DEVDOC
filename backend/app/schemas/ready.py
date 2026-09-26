"""ReadinessResponse Pydantic schema."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ReadinessResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    success: bool
    service: str
    status: str
    checks: dict[str, str]
