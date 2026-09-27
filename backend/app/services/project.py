"""Project management service."""

from __future__ import annotations

import re
import uuid
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.models.project import Project
from app.models.user import User
from app.schemas.project import ProjectCreate, ProjectUpdate


def slugify_name(name: str) -> str:
    """Generate a clean URL-friendly slug from a project name."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not slug:
        slug = f"project-{uuid.uuid4().hex[:6]}"
    return slug[:100]


class ProjectService:
    """Service handling project CRUD and authorization-aware database operations."""

    @staticmethod
    async def create_project(
        db: AsyncSession,
        current_user: User,
        data: ProjectCreate,
    ) -> Project:
        """Create a new project anchored to the authenticated user.

        Security:
        - `owner_id` is always derived strictly from `current_user.id`.
        - Enforces unique constraint on `(owner_id, slug)`.
        """
        slug = data.slug.strip().lower() if data.slug else slugify_name(data.name)

        # Check slug collision for this owner
        stmt = select(Project).where(
            Project.owner_id == current_user.id,
            Project.slug == slug,
        )
        existing = (await db.execute(stmt)).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Project with slug '{slug}' already exists for this owner",
            )

        project = Project(
            id=uuid.uuid4(),
            name=data.name,
            slug=slug,
            description=data.description,
            settings_json=data.settings_json,
            owner_id=current_user.id,
            is_active=True,
        )
        db.add(project)
        await db.commit()
        await db.refresh(project)

        logger.info("Created project '%s' (%s) for user %s", project.name, project.id, current_user.id)
        return project

    @staticmethod
    async def list_user_projects(
        db: AsyncSession,
        current_user: User,
        limit: int = 50,
        offset: int = 0,
        include_inactive: bool = False,
    ) -> tuple[list[Project], int]:
        """List projects belonging to the authenticated user with pagination."""
        base_conditions: list[Any] = [Project.owner_id == current_user.id]
        if not include_inactive:
            base_conditions.append(Project.is_active.is_(True))

        count_stmt = select(func.count()).select_from(Project).where(*base_conditions)
        total = (await db.execute(count_stmt)).scalar() or 0

        query_stmt = (
            select(Project)
            .where(*base_conditions)
            .order_by(Project.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        items = list((await db.execute(query_stmt)).scalars().all())

        return items, total

    @staticmethod
    async def update_project(
        db: AsyncSession,
        project: Project,
        data: ProjectUpdate,
    ) -> Project:
        """Update mutable project fields."""
        update_dict = data.model_dump(exclude_unset=True)

        for field, value in update_dict.items():
            setattr(project, field, value)

        await db.commit()
        await db.refresh(project)

        logger.info("Updated project %s (%s)", project.name, project.id)
        return project

    @staticmethod
    async def delete_project(
        db: AsyncSession,
        project: Project,
    ) -> uuid.UUID:
        """Delete project from database, triggering cascading cleanups."""
        project_id = project.id
        await db.delete(project)
        await db.commit()

        logger.info("Deleted project %s", project_id)
        return project_id
