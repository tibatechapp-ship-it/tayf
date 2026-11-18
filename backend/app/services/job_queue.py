"""Durable job queue backed by the `generation_jobs` table.

The table IS the queue — no Redis or extra dependency, so the stack still runs
on a single Termux host. Ownership is a time-limited lease: a worker claims a
PENDING row with one conditional UPDATE, renews the lease while the pipeline
runs, and any PROCESSING row whose lease expired is reclaimable by another
worker (or by the same worker on restart).
"""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.models import GenerationJob, GenerationStatus
from app.models.base import utc_now


def claim_next(
    db: Session, worker_id: str, *, lease_seconds: int = 600
) -> GenerationJob | None:
    """Atomically claim the oldest PENDING job. One winner across workers."""
    now = utc_now()
    # Two workers may read the same candidate; the conditional UPDATE below
    # makes only one of them win, the loser simply polls again.
    candidate_id = db.scalar(
        select(GenerationJob.id)
        .where(GenerationJob.status == GenerationStatus.PENDING)
        .order_by(GenerationJob.created_at, GenerationJob.id)
        .limit(1)
    )
    if candidate_id is None:
        return None
    result = db.execute(
        update(GenerationJob)
        .where(
            GenerationJob.id == candidate_id,
            GenerationJob.status == GenerationStatus.PENDING,
        )
        .values(
            status=GenerationStatus.PROCESSING,
            worker_id=worker_id,
            lease_until=now + timedelta(seconds=lease_seconds),
            attempts=GenerationJob.attempts + 1,
        )
    )
    db.commit()
    if result.rowcount != 1:
        return None
    return db.get(GenerationJob, candidate_id)


def renew_lease(
    db: Session, job_id: UUID, worker_id: str, *, lease_seconds: int = 600
) -> bool:
    """Extend the lease; False means this worker no longer owns the job."""
    result = db.execute(
        update(GenerationJob)
        .where(
            GenerationJob.id == job_id,
            GenerationJob.worker_id == worker_id,
            GenerationJob.status == GenerationStatus.PROCESSING,
        )
        .values(lease_until=utc_now() + timedelta(seconds=lease_seconds))
    )
    db.commit()
    return result.rowcount == 1


def recover_stale(db: Session) -> int:
    """Requeue PROCESSING jobs with no lease or an expired one."""
    result = db.execute(
        update(GenerationJob)
        .where(
            GenerationJob.status == GenerationStatus.PROCESSING,
            or_(
                GenerationJob.lease_until.is_(None),
                GenerationJob.lease_until < utc_now(),
            ),
        )
        .values(status=GenerationStatus.PENDING, worker_id=None, lease_until=None)
    )
    db.commit()
    return result.rowcount


def release_owned(db: Session, worker_id: str) -> int:
    """Give back still-owned jobs on a graceful worker shutdown."""
    result = db.execute(
        update(GenerationJob)
        .where(
            GenerationJob.worker_id == worker_id,
            GenerationJob.status == GenerationStatus.PROCESSING,
        )
        .values(status=GenerationStatus.PENDING, worker_id=None, lease_until=None)
    )
    db.commit()
    return result.rowcount
