from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.github import router as github_router
from app.api.v1.health import health_router
from app.api.v1.incidents import router as incidents_router
from app.api.v1.investigations import router as investigations_router
from app.api.v1.projects import router as projects_router
from app.api.v1.ready import ready_router
from app.api.v1.users import router as users_router

v1_router = APIRouter(prefix="/api/v1")
v1_router.include_router(health_router)
v1_router.include_router(ready_router)
v1_router.include_router(auth_router)
v1_router.include_router(users_router)
v1_router.include_router(projects_router)
v1_router.include_router(github_router)
v1_router.include_router(incidents_router)
v1_router.include_router(investigations_router)




