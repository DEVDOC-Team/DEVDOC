from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from app.core.config import settings


def _allowed_cors_origin(request: Request) -> str | None:
    origin = request.headers.get("origin")
    if not origin:
        return None

    allowed_origins = settings.cors_origins or (
        []
        if settings.is_production
        else ["http://localhost:5173", "http://127.0.0.1:5173"]
    )
    return origin if origin in allowed_origins else None


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Return a predictable JSON payload for HTTP errors."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {
                "code": exc.status_code,
                "message": exc.detail,
            },
        },
        headers=exc.headers,
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Prevent internal details from leaking to API clients."""
    origin = _allowed_cors_origin(request)
    headers = (
        {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Credentials": "true",
            "Vary": "Origin",
        }
        if origin
        else None
    )
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": {
                "code": 500,
                "message": "Internal server error",
            },
        },
        headers=headers,
    )
