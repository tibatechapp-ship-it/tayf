"""Project persistence.

Ownership is enforced here, at query level, not in the API layer: a project
lookup that does not filter by owner is a bug waiting to become a data leak.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Project, ProjectStatus


def create_project(
    session: Session,
    *,
    owner_id: uuid.UUID,
    name: str,
    description: str | None = None,
    status: ProjectStatus = ProjectStatus.DRAFT,
) -> Project:
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("project name must not be empty")
    if len(clean_name) > 120:
        raise ValueError("project name must be at most 120 characters")

    project = Project(
        user_id=owner_id,
        name=clean_name,
        description=description.strip() if description else None,
        status=status,
    )
    session.add(project)
    session.flush()
    return project


def list_projects_by_user(
    session: Session,
    owner_id: uuid.UUID,
    *,
    limit: int = 50,
    offset: int = 0,
) -> Sequence[Project]:
    """Newest first, paginated — never an unbounded list."""
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    return session.scalars(
        select(Project)
        .where(Project.user_id == owner_id)
        .order_by(Project.created_at.desc(), Project.id)
        .limit(limit)
        .offset(offset)
    ).all()


def get_project_by_id_and_owner(
    session: Session, project_id: uuid.UUID, owner_id: uuid.UUID
) -> Project | None:
    """``None`` for both 'missing' and 'someone else's' — no existence oracle."""
    return session.scalar(
        select(Project).where(Project.id == project_id, Project.user_id == owner_id)
    )
