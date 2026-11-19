"""Pro export endpoints: owner-scoped SRT, project file and scene stills."""

from __future__ import annotations

import json
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response

from app.api.deps import get_current_user
from app.db.session import get_session
from app.models import GenerationJob, User
from app.repositories import job_repository
from app.services import exports
from sqlalchemy.orm import Session

router = APIRouter(prefix="/jobs", tags=["exports"])

SessionDep = Annotated[Session, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]


def _owned_job(session: Session, job_id: uuid.UUID, owner_id: uuid.UUID) -> GenerationJob:
    job = job_repository.get_job_owned_by(session, job_id, owner_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="المهمة غير موجودة")
    return job


def _attachment(content: bytes, filename: str, media_type: str) -> Response:
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/{job_id}/export/srt",
    summary="Download Arabic-ready SRT subtitles for a job",
    responses={404: {"description": "Job not found or not owned by this user"}},
)
def export_srt(job_id: uuid.UUID, current_user: CurrentUser, session: SessionDep) -> Response:
    job = _owned_job(session, job_id, current_user.id)
    body = exports.build_srt(job).encode("utf-8-sig")  # BOM for subtitle players
    return _attachment(body, exports.safe_filename(job_id, "srt"), "application/x-subrip")


@router.get(
    "/{job_id}/export/project",
    summary="Download a portable JSON project manifest for a job",
    responses={404: {"description": "Job not found or not owned by this user"}},
)
def export_project(job_id: uuid.UUID, current_user: CurrentUser, session: SessionDep) -> Response:
    job = _owned_job(session, job_id, current_user.id)
    body = json.dumps(
        exports.build_project_file(job), ensure_ascii=False, indent=2
    ).encode("utf-8")
    return _attachment(body, exports.safe_filename(job_id, "tayf.json"), "application/json")


@router.get(
    "/{job_id}/export/stills",
    summary="Download a ZIP of the job's scene stills",
    responses={404: {"description": "Job not found or not owned by this user"}},
)
def export_stills(job_id: uuid.UUID, current_user: CurrentUser, session: SessionDep) -> Response:
    job = _owned_job(session, job_id, current_user.id)
    body = exports.build_stills_zip(job)
    return _attachment(body, exports.safe_filename(job_id, "zip"), "application/zip")
