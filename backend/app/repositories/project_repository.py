"""Project persistence.

Ownership is enforced here, at query level, not in the API layer: a project
lookup that does not filter by owner is a bug waiting to become a data leak.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from typing import Any

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
    limit: int = 20,
    offset: int = 0,
    include_archived: bool = False,
) -> Sequence[Project]:
    """Newest first, paginated — never an unbounded list."""
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    statement = (
        select(Project)
        .where(Project.user_id == owner_id)
        .order_by(Project.created_at.desc(), Project.id)
        .limit(limit)
        .offset(offset)
    )
    if not include_archived:
        # Soft-deleted rows stay in the table but leave the default listing.
        statement = statement.where(Project.status != ProjectStatus.ARCHIVED)
    return session.scalars(statement).all()


def get_project_by_id_and_owner(
    session: Session, project_id: uuid.UUID, owner_id: uuid.UUID
) -> Project | None:
    """``None`` for both 'missing' and 'someone else's' — no existence oracle."""
    return session.scalar(
        select(Project).where(Project.id == project_id, Project.user_id == owner_id)
    )


UPDATABLE_FIELDS = frozenset({"name", "description"})


def update_project(
    session: Session, project: Project, *, changes: Mapping[str, Any]
) -> Project:
    """Apply a partial update. ``changes`` may only contain ``name``/``description``.

    An explicit ``description: None`` clears the field; an absent key leaves it
    untouched — that is the difference a PATCH must preserve.
    """
    unknown = set(changes) - UPDATABLE_FIELDS
    if unknown:
        raise ValueError(f"fields not updatable: {', '.join(sorted(unknown))}")

    if "name" in changes:
        clean_name = (changes["name"] or "").strip()
        if not clean_name:
            raise ValueError("project name must not be empty")
        if len(clean_name) > 120:
            raise ValueError("project name must be at most 120 characters")
        project.name = clean_name

    if "description" in changes:
        raw = changes["description"]
        project.description = raw.strip() if isinstance(raw, str) and raw.strip() else None

    session.flush()
    return project


def archive_project(session: Session, project: Project) -> Project:
    """Soft delete: keep the row (and its jobs) for audit, hide it from listings."""
    project.status = ProjectStatus.ARCHIVED
    session.flush()
    return project
