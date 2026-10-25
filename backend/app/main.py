from __future__ import annotations

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from starlette.routing import Match

from app.api.router import api_router
from app.core.config import settings
from app.core.exceptions import generic_exception_handler, http_exception_handler
from app.core.logging import logger
from app.core.metrics import metrics_registry
from app.core.rate_limit import rate_limit_middleware, rate_limiter


async def security_headers_middleware(request: Request, call_next):
    """Add conservative security headers to every HTTP response."""
    response = await call_next(request)
    if not settings.security_headers_enabled:
        return response

    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("X-XSS-Protection", "0")
    response.headers.setdefault("Cache-Control", "no-store")

    if request.url.scheme == "https":
        response.headers.setdefault(
            "Strict-Transport-Security",
            f"max-age={settings.hsts_max_age_seconds}; includeSubDomains",
        )

    return response


async def metrics_middleware(request: Request, call_next):
    """Record bounded-cardinality HTTP metrics, skipping /metrics itself."""
    if not settings.metrics_enabled or request.url.path == settings.metrics_path:
        return await call_next(request)

    start = time.time()
    response = await call_next(request)
    duration = time.time() - start

    path_template = request.url.path
    if request.app:
        for route in request.app.routes:
            match, _ = route.matches(request.scope)
            if match == Match.FULL:
                path_template = getattr(route, "path", request.url.path)
                break

    metrics_registry.record_http_request(
        method=request.method,
        path_template=path_template,
        status_code=response.status_code,
        duration_seconds=duration,
    )
    return response


@asynccontextmanager
async def lifespan(_: FastAPI):
    await rate_limiter.start()
    logger.info("Starting %s v%s in %s mode", settings.app_name, settings.app_version, settings.environment)
    try:
        yield
    finally:
        await rate_limiter.close()
        logger.info("Shutting down %s", settings.app_name)


app = FastAPI(
    title=settings.app_name,
    description="AI-powered DevOps and SRE incident investigation backend foundation.",
    version=settings.app_version,
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    openapi_url=None if settings.is_production else "/openapi.json",
    lifespan=lifespan,
)

allowed_hosts = settings.trusted_hosts
if not allowed_hosts:
    if settings.is_production:
        raise RuntimeError("Trusted hosts must be configured before the app starts in production mode")
    allowed_hosts = ["localhost", "127.0.0.1", "[::1]", "testserver"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins if settings.cors_origins else ([] if settings.is_production else ["http://localhost:5173", "http://127.0.0.1:5173"]),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)
app.middleware("http")(rate_limit_middleware)
app.middleware("http")(security_headers_middleware)
app.middleware("http")(metrics_middleware)

app.include_router(api_router)


@app.get(settings.metrics_path, tags=["Observability"], summary="Prometheus metrics")
async def prometheus_metrics() -> Response:
    """Export bounded-cardinality Prometheus metrics for scraping."""
    if not settings.metrics_enabled:
        raise HTTPException(status_code=404, detail="Metrics disabled")
    return Response(
        content=metrics_registry.export_prometheus_text(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


@app.get("/", tags=["Root"], summary="API root")
async def root() -> dict[str, str]:
    """Return a friendly landing payload for the API root."""
    return {
        "service": settings.app_name,
        "status": "ok",
        "docs_url": "/docs" if not settings.is_production else None,
        "health_url": "/api/v1/health",
        "ready_url": "/api/v1/ready",
    }


app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)
