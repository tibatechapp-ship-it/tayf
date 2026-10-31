"""Project endpoints (Stage 3).

Authentication does not exist yet: the owner is an explicit query/body parameter
so ownership isolation is exercised by real tests. Stage 4 replaces it with the
JWT subject — every handler below already receives ``owner_id`` as a plain value,
so the swap is local to this file.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.repositories import project_repository, user_repository
from app.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate

router = APIRouter(prefix="/projects", tags=["projects"])

SessionDep = Annotated[Session, Depends(get_session)]
OwnerQuery = Annotated[
    uuid.UUID,
    Query(description="Owner of the projects. Temporary until Stage 4 JWT auth."),
]
LimitQuery = Annotated[int, Query(ge=1, le=100, description="Page size (1-100).")]
OffsetQuery = Annotated[int, Query(ge=0, description="Rows to skip.")]

_NOT_FOUND = {404: {"description": "Project not found or not owned by this owner"}}


def _get_owned_project(
    session: Session, project_id: uuid.UUID, owner_id: uuid.UUID
):
    """404 — never 403 — for both 'missing' and 'someone else's' (no oracle)."""
    project = project_repository.get_project_by_id_and_owner(session, project_id, owner_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )
    return project


@router.post(
    "",
    response_model=ProjectRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a project",
    responses={400: {"description": "owner_id does not reference an existing user"}},
)
def create_project(payload: ProjectCreate, session: SessionDep) -> ProjectRead:
    if user_repository.get_by_id(session, payload.owner_id) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Owner does not exist"
        )
    project = project_repository.create_project(
        session,
        owner_id=payload.owner_id,
        name=payload.name,
        description=payload.description,
    )
    session.commit()
    return ProjectRead.model_validate(project)


@router.get(
    "",
    response_model=list[ProjectRead],
    summary="List the owner's projects",
    description=(
        "Newest first. Archived (soft-deleted) projects are excluded unless "
        "`include_archived=true`."
    ),
)
def list_projects(
    session: SessionDep,
    owner_id: OwnerQuery,
    limit: LimitQuery = 20,
    offset: OffsetQuery = 0,
    include_archived: Annotated[bool, Query()] = False,
) -> list[ProjectRead]:
    projects = project_repository.list_projects_by_user(
        session,
        owner_id,
        limit=limit,
        offset=offset,
        include_archived=include_archived,
    )
    return [ProjectRead.model_validate(project) for project in projects]


@router.get(
    "/{project_id}",
    response_model=ProjectRead,
    summary="Read one project",
    responses=_NOT_FOUND,
)
def get_project(project_id: uuid.UUID, owner_id: OwnerQuery, session: SessionDep) -> ProjectRead:
    project = _get_owned_project(session, project_id, owner_id)
    return ProjectRead.model_validate(project)


@router.patch(
    "/{project_id}",
    response_model=ProjectRead,
    summary="Update a project (partial)",
    responses=_NOT_FOUND,
)
def update_project(
    project_id: uuid.UUID,
    payload: ProjectUpdate,
    owner_id: OwnerQuery,
    session: SessionDep,
) -> ProjectRead:
    project = _get_owned_project(session, project_id, owner_id)
    changes = payload.model_dump(exclude_unset=True)
    if changes:
        try:
            project_repository.update_project(session, project, changes=changes)
        except ValueError as exc:  # repository guard, schema already checked
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
            ) from exc
        session.commit()
    return ProjectRead.model_validate(project)


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Archive a project (soft delete)",
    description="Sets `status=archived` and keeps the row for audit. Idempotent.",
    responses=_NOT_FOUND,
)
def delete_project(
    project_id: uuid.UUID, owner_id: OwnerQuery, session: SessionDep
) -> Response:
    project = _get_owned_project(session, project_id, owner_id)
    project_repository.archive_project(session, project)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
