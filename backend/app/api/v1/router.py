from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.health import health_router
from app.api.v1.ready import ready_router

v1_router = APIRouter(prefix="/api/v1")
v1_router.include_router(health_router)
v1_router.include_router(ready_router)
v1_router.include_router(auth_router)

