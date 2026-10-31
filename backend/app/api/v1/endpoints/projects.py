"""Project endpoints — repository-driven CRUD behind JWT auth.

The unified merge completes the Stage-3 TODO: the owner is the JWT subject,
not a query parameter. Ownership isolation stays at query level (repositories);
`job_count` is enriched here because it is a wire-contract convenience.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_session
from app.models import User
from app.repositories import job_repository, project_repository
from app.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate

router = APIRouter(prefix="/projects", tags=["projects"])

SessionDep = Annotated[Session, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]
LimitQuery = Annotated[int, Query(ge=1, le=100, description="Page size (1-100).")]
OffsetQuery = Annotated[int, Query(ge=0, description="Rows to skip.")]

_NOT_FOUND = {404: {"description": "Project not found or not owned by this user"}}


def _get_owned_project(
    session: Session, project_id: uuid.UUID, owner_id: uuid.UUID
):
    """404 — never 403 — for both 'missing' and 'someone else's' (no oracle)."""
    project = project_repository.get_project_by_id_and_owner(
        session, project_id, owner_id
    )
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )
    return project


def _read_project(session: Session, project) -> ProjectRead:  # noqa: ANN001
    read = ProjectRead.model_validate(project)
    read.job_count = job_repository.count_jobs_for_project(session, project.id)
    return read


@router.post(
    "",
    response_model=ProjectRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a project",
)
def create_project(
    payload: ProjectCreate, current_user: CurrentUser, session: SessionDep
) -> ProjectRead:
    project = project_repository.create_project(
        session,
        owner_id=current_user.id,
        name=payload.name,
        description=payload.description,
    )
    session.commit()
    return _read_project(session, project)


@router.get(
    "",
    response_model=list[ProjectRead],
    summary="List the authenticated user's projects",
    description=(
        "Newest first, paginated. Archived (soft-deleted) projects are excluded "
        "unless `include_archived=true`."
    ),
)
def list_projects(
    current_user: CurrentUser,
    session: SessionDep,
    limit: LimitQuery = 20,
    offset: OffsetQuery = 0,
    include_archived: Annotated[bool, Query()] = False,
) -> list[ProjectRead]:
    projects = project_repository.list_projects_by_user(
        session,
        current_user.id,
        limit=limit,
        offset=offset,
        include_archived=include_archived,
    )
    return [_read_project(session, project) for project in projects]


@router.get(
    "/{project_id}",
    response_model=ProjectRead,
    summary="Read one project",
    responses=_NOT_FOUND,
)
def get_project(
    project_id: uuid.UUID, current_user: CurrentUser, session: SessionDep
) -> ProjectRead:
    project = _get_owned_project(session, project_id, current_user.id)
    return _read_project(session, project)


@router.patch(
    "/{project_id}",
    response_model=ProjectRead,
    summary="Update a project (partial)",
    responses=_NOT_FOUND,
)
def update_project(
    project_id: uuid.UUID,
    payload: ProjectUpdate,
    current_user: CurrentUser,
    session: SessionDep,
) -> ProjectRead:
    project = _get_owned_project(session, project_id, current_user.id)
    changes = payload.model_dump(exclude_unset=True)
    if changes:
        try:
            project_repository.update_project(session, project, changes=changes)
        except ValueError as exc:  # repository guard, schema already checked
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
            ) from exc
        session.commit()
    return _read_project(session, project)


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Archive a project (soft delete)",
    description="Sets `status=archived` and keeps the row for audit. Idempotent.",
    responses=_NOT_FOUND,
)
def delete_project(
    project_id: uuid.UUID, current_user: CurrentUser, session: SessionDep
) -> Response:
    project = _get_owned_project(session, project_id, current_user.id)
    project_repository.archive_project(session, project)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
