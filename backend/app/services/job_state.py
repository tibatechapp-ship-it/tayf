"""Atomic generation-job state transitions.

The API (cancel) and the worker (start/fail/complete) can run in different
threads/processes. Every transition below is a conditional UPDATE, so only one
writer can move a job out of an active state — the loser sees rowcount 0.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import GenerationJob, GenerationStatus, Project
from app.services import credits

ACTIVE_STATUSES = frozenset({GenerationStatus.PENDING, GenerationStatus.PROCESSING})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _owned_job_id(db: Session, job_id: UUID, owner_id: UUID) -> UUID | None:
    return db.scalar(
        select(GenerationJob.id)
        .join(Project, Project.id == GenerationJob.project_id)
        .where(GenerationJob.id == job_id, Project.user_id == owner_id)
    )


def _owner_exists(owner_id: UUID):
    """Correlated EXISTS for the UPDATE ... WHERE ownership guard."""
    return (
        select(Project.id)
        .where(Project.id == GenerationJob.project_id, Project.user_id == owner_id)
        .exists()
    )


def start(db: Session, job_id: UUID) -> GenerationJob | None:
    """Claim a PENDING job for the worker. Single winner only."""
    result = db.execute(
        update(GenerationJob)
        .where(GenerationJob.id == job_id, GenerationJob.status == GenerationStatus.PENDING)
        .values(status=GenerationStatus.PROCESSING)
    )
    if result.rowcount != 1:
        return None
    job = db.get(GenerationJob, job_id)
    db.refresh(job)
    return job


def cancel(db: Session, job_id: UUID, owner_id: UUID) -> tuple[GenerationJob | None, str]:
    """Cancel an active owned job. Returns (job, "ok"|"not_found"|"conflict")."""
    result = db.execute(
        update(GenerationJob)
        .where(
            GenerationJob.id == job_id,
            GenerationJob.status.in_(ACTIVE_STATUSES),
            _owner_exists(owner_id),
        )
        .values(status=GenerationStatus.CANCELLED, completed_at=_now())
    )
    if result.rowcount != 1:
        job = db.get(GenerationJob, job_id)
        if job is None or _owned_job_id(db, job_id, owner_id) is None:
            return None, "not_found"
        return job, "conflict"

    job = db.get(GenerationJob, job_id)
    db.refresh(job)
    if job.credits_charged > 0:
        amount = job.credits_charged
        credits.refund(
            db,
            owner_id,
            amount,
            job_id=job.id,
            reason="refund_job_cancelled",
            operation_key=f"refund_job_cancelled:{job.id}",
        )
        job.credits_charged = 0
    return job, "ok"


def fail(
    db: Session, job_id: UUID, message: str, category: str | None = None
) -> tuple[GenerationJob | None, bool]:
    """Move an active job to FAILED and refund once. Returns (job, changed)."""
    result = db.execute(
        update(GenerationJob)
        .where(
            GenerationJob.id == job_id,
            GenerationJob.status.in_(ACTIVE_STATUSES),
        )
        .values(
            status=GenerationStatus.FAILED,
            error_message=message[:1000],
            safety_category=category,
            completed_at=_now(),
        )
    )
    if result.rowcount != 1:
        return db.get(GenerationJob, job_id), False

    job = db.get(GenerationJob, job_id)
    db.refresh(job)
    owner_id = db.scalar(select(Project.user_id).where(Project.id == job.project_id))
    if job.credits_charged > 0 and owner_id is not None:
        amount = job.credits_charged
        credits.refund(
            db,
            owner_id,
            amount,
            job_id=job.id,
            reason="refund_job_failed",
            operation_key=f"refund_job_failed:{job.id}",
        )
        job.credits_charged = 0
    return job, True


def complete(
    db: Session,
    job_id: UUID,
    *,
    result_url: str,
    thumbnail_url: str | None,
    video_size_bytes: int,
    duration_seconds: float,
    storyboard: dict,
) -> bool:
    """Finalize an active job. Returns False if cancel/fail won the race."""
    result = db.execute(
        update(GenerationJob)
        .where(
            GenerationJob.id == job_id,
            GenerationJob.status.in_(ACTIVE_STATUSES),
        )
        .values(
            status=GenerationStatus.COMPLETED,
            result_url=result_url,
            thumbnail_url=thumbnail_url,
            video_size_bytes=video_size_bytes,
            duration_seconds=duration_seconds,
            storyboard=storyboard,
            completed_at=_now(),
        )
    )
    return result.rowcount == 1
