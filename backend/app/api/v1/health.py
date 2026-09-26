from fastapi import APIRouter

from app.schemas.health import HealthResponse

health_router = APIRouter(tags=["Health"])


@health_router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Return the health status of the API."""
    return HealthResponse(
        success=True,
        service="DEVDOC",
        status="healthy",
    )
