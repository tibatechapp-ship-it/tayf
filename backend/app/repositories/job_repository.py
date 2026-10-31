"""Job persistence — ownership joins live here, never in the API layer."""

from __future__ import annotations

import uuid
from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import GenerationJob, GenerationStatus, Project


def count_jobs_for_project(session: Session, project_id: uuid.UUID) -> int:
    return int(
        session.execute(
            select(func.count()).select_from(GenerationJob).where(
                GenerationJob.project_id == project_id
            )
        ).scalar_one()
    )


def list_jobs_by_project(
    session: Session,
    project_id: uuid.UUID,
    *,
    limit: int = 50,
    offset: int = 0,
) -> Sequence[GenerationJob]:
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    statement = (
        select(GenerationJob)
        .where(GenerationJob.project_id == project_id)
        .order_by(GenerationJob.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return session.scalars(statement).all()


def get_job_owned_by(
    session: Session, job_id: uuid.UUID, owner_id: uuid.UUID
) -> GenerationJob | None:
    """Fetch a job only through its project's owner — no existence oracle."""
    return session.scalar(
        select(GenerationJob)
        .join(Project, Project.id == GenerationJob.project_id)
        .where(GenerationJob.id == job_id, Project.user_id == owner_id)
    )


def count_active_jobs(session: Session) -> int:
    """Jobs not in a terminal state (monitoring/queue-depth metric)."""
    return int(
        session.execute(
            select(func.count()).select_from(GenerationJob).where(
                GenerationJob.status.not_in(GenerationStatus.terminal())
            )
        ).scalar_one()
    )
