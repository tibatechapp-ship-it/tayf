"""Optional human approval gates for pipeline stages.

A gate never changes `status`: the job stays PROCESSING, but it releases the
worker lease and records `pending_approval`. The pipeline returns immediately,
so no worker slot stays blocked while a human reviews text or images. After a
decision the API schedules the same pipeline again with `resume_from=<stage>`;
the resume context (storage keys, durations) is carried inside the gate record,
so generation is never paid for twice.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, cast

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from app.models import GenerationJob, Project

_GATE_PROGRESS = {"storyboard": 35, "assets": 65}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def request_gate(
    db: Session,
    job_id: uuid.UUID,
    stage: str,
    *,
    review: dict[str, Any],
    resume: dict[str, Any],
) -> bool:
    """Atomically pause a processing job for human review.

    False means another writer (cancel/fail) won the race — the caller must
    stop without touching the job.
    """
    gate = {
        "stage": stage,
        "review": review,
        "resume": resume,
        "requested_at": _now(),
        "decision": None,
    }
    result = cast(
        CursorResult,
        db.execute(
            update(GenerationJob)
            .where(
                GenerationJob.id == job_id,
                GenerationJob.status == "processing",
            )
            .values(
                pending_approval=gate,
                stage=f"awaiting:{stage}",
                progress=_GATE_PROGRESS.get(stage, 50),
                worker_id=None,
                lease_until=None,
            )
        ),
    )
    db.commit()
    db.expire_all()  # the Core UPDATE must not be shadowed by a stale ORM object
    return result.rowcount == 1


def decide_gate(
    db: Session,
    job_id: uuid.UUID,
    owner_id: uuid.UUID,
    decision: str,
    note: str | None,
) -> tuple[str, dict[str, Any] | None]:
    """Decide the open gate. Returns (ok|not_found|conflict, gate).

    `reject` refunds the job through the existing cancel/refund path, so the
    ledger stays consistent with every other cancellation.
    """
    job = db.scalar(
        select(GenerationJob)
        .join(Project, Project.id == GenerationJob.project_id)
        .where(GenerationJob.id == job_id, Project.user_id == owner_id)
    )
    if job is None:
        return "not_found", None
    gate = job.pending_approval
    if not isinstance(gate, dict) or gate.get("decision") is not None:
        return "conflict", None
    if job.status != "processing":
        return "conflict", None

    record = {
        **gate,
        "decision": decision,
        "note": (note or "").strip()[:1000] or None,
        "decided_at": _now(),
        "decided_by": str(owner_id),
    }
    result = cast(
        CursorResult,
        db.execute(
            update(GenerationJob)
            .where(GenerationJob.id == job_id, GenerationJob.status == "processing")
            .values(
                pending_approval=record,
                approval_history=[*(job.approval_history or []), record],
                stage="processing" if decision == "approve" else job.stage,
                worker_id=None,
                lease_until=None,
            )
        ),
    )
    if result.rowcount != 1:
        db.rollback()
        return "conflict", None
    db.commit()
    db.expire_all()  # the endpoint calls job_state.cancel on the same session
    return "ok", record
