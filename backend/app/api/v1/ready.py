"""Readiness endpoint — verifies required dependencies are reachable.

GET /api/v1/ready

Unlike the liveness endpoint (GET /api/v1/health), this endpoint
actively checks that the database can be reached.  It should be used
as a Kubernetes readinessProbe / load-balancer health check so traffic
is only routed to instances that are fully operational.

The liveness endpoint (/health) must never fail due to database
unavailability — it only confirms the process is alive.
"""

from __future__ import annotations

from fastapi import APIRouter, status
from sqlalchemy import text

from app.core.logging import logger
from app.db.session import AsyncSessionLocal
from app.schemas.ready import ReadinessResponse

ready_router = APIRouter(tags=["Readiness"])


@ready_router.get(
    "/ready",
    response_model=ReadinessResponse,
    status_code=status.HTTP_200_OK,
    summary="Readiness check",
    description=(
        "Returns 200 when the API and all required dependencies (database) are healthy. "
        "Returns 503 when any dependency is unavailable."
    ),
)
async def readiness_check() -> ReadinessResponse:
    """Probe all required dependencies and return a structured status."""
    checks: dict[str, str] = {}
    overall_ok = True

    # Database check
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001
        logger.warning("Database readiness check failed: %s", exc)
        checks["database"] = "unavailable"
        overall_ok = False

    from fastapi.responses import JSONResponse

    payload = ReadinessResponse(
        success=overall_ok,
        service="DEVDOC",
        status="ready" if overall_ok else "degraded",
        checks=checks,
    )

    http_status = status.HTTP_200_OK if overall_ok else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(content=payload.model_dump(), status_code=http_status)  # type: ignore[return-value]
