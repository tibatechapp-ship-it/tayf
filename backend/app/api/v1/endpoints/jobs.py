"""Jobs endpoints: create (safety -> credits -> background pipeline) and read.

The pipeline runs as a Starlette background task AFTER the 202 response is
sent — this works identically under uvicorn and under TestClient (where the
task completes before the test sees the response, making tests deterministic).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.metrics import record_job_terminal
from app.core.ratelimit import job_rate_limit
from app.core.safety import get_safety_layer
from app.db.session import get_session
from app.models import GenerationJob, GenerationStatus, Project, User
from app.repositories import job_repository
from app.schemas.job import JobCreateIn, JobOut
from app.services import credits
from app.services.pipeline import run_job_pipeline

router = APIRouter(tags=["jobs"])

SessionDep = Annotated[Session, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]


def _get_owned_project(session: Session, project_id: uuid.UUID, owner_id: uuid.UUID) -> Project:
    project = session.get(Project, project_id)
    if project is None or project.user_id != owner_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="المشروع غير موجود")
    return project


@router.post(
    "/projects/{project_id}/jobs",
    response_model=JobOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Create a generation job (safety -> credits -> pipeline)",
    responses={
        402: {"description": "Insufficient credits"},
        404: {"description": "Project not found or not owned by this user"},
    },
)
def create_job(
    project_id: uuid.UUID,
    payload: JobCreateIn,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser,
    session: SessionDep,
    _rl: None = Depends(job_rate_limit),
) -> JobOut:
    settings = get_settings()
    project = _get_owned_project(session, project_id, current_user.id)
    safety = get_safety_layer()
    cost = payload.num_scenes * get_settings().CREDIT_PER_SCENE

    # 1) pre-generation safety screen (no charge on rejection)
    verdict = safety.check_prompt(payload.prompt)
    if not verdict.allowed:
        job = GenerationJob(
            project_id=project.id,
            prompt=payload.prompt,
            num_scenes=payload.num_scenes,
            aspect=payload.aspect,
            style=payload.style,
            provider_name="safety",
            model_version="pre-filter",
            status=GenerationStatus.REJECTED,
            rejection_reason=verdict.reason,
            safety_category=verdict.category,
            credits_charged=0,
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        record_job_terminal(GenerationStatus.REJECTED.value)
        return JobOut.from_model(job)

    # 2) create the job row FIRST (uncommitted) so the charge entry can carry
    #    its id — the ledger must be auditable down to the exact job.
    job = GenerationJob(
        project_id=project.id,
        prompt=payload.prompt,
        num_scenes=payload.num_scenes,
        aspect=payload.aspect,
        style=payload.style,
        input_params={"requested_by": str(current_user.id)},
        status=GenerationStatus.PENDING,
        credits_charged=cost,
    )
    session.add(job)
    session.flush()  # assigns job.id without committing

    cost = job.credits_charged
    try:
        credits.charge(
            session, current_user.id, cost, reason="job_charge", job_id=job.id
        )
    except credits.InsufficientCredits as exc:
        session.rollback()
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            detail=(
                f"رصيدك غير كافٍ: تحتاج {exc.needed} رصيدًا ولديك {exc.available}. "
                f"كل مشهد يكلف {settings.CREDIT_PER_SCENE} رصيدًا."
            ),
        ) from exc

    session.commit()
    session.refresh(job)

    background_tasks.add_task(run_job_pipeline, str(job.id))
    return JobOut.from_model(job)


@router.get(
    "/projects/{project_id}/jobs",
    response_model=list[JobOut],
    summary="List a project's jobs (newest first)",
)
def list_jobs(
    project_id: uuid.UUID,
    current_user: CurrentUser,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[JobOut]:
    project = _get_owned_project(session, project_id, current_user.id)
    jobs = job_repository.list_jobs_by_project(
        session, project.id, limit=limit, offset=offset
    )
    return [JobOut.from_model(job) for job in jobs]


@router.post(
    "/jobs/{job_id}/cancel",
    response_model=JobOut,
    summary="Cancel a pending/processing job (credits are refunded)",
    responses={
        404: {"description": "Job not found or not owned by this user"},
        409: {"description": "Job already reached a terminal state"},
    },
)
def cancel_job(job_id: uuid.UUID, current_user: CurrentUser, session: SessionDep) -> JobOut:
    job = job_repository.get_job_owned_by(session, job_id, current_user.id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="المهمة غير موجودة")
    if job.status in GenerationStatus.terminal():
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="لا يمكن إلغاء مهمة منتهية"
        )
    job.status = GenerationStatus.CANCELLED
    job.completed_at = datetime.now(timezone.utc)
    if job.credits_charged > 0:
        credits.refund(
            session, current_user.id, job.credits_charged,
            job_id=job.id, reason="refund_job_cancelled",
        )
        job.credits_charged = 0
    session.commit()
    session.refresh(job)
    record_job_terminal(GenerationStatus.CANCELLED.value)
    return JobOut.from_model(job)


@router.get(
    "/jobs/{job_id}",
    response_model=JobOut,
    summary="Read one job (poll for progress)",
    responses={404: {"description": "Job not found or not owned by this user"}},
)
def get_job(job_id: uuid.UUID, current_user: CurrentUser, session: SessionDep) -> JobOut:
    job = job_repository.get_job_owned_by(session, job_id, current_user.id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="المهمة غير موجودة")
    return JobOut.from_model(job)
