"""Cost reporting over the append-only proof trail and credit ledger.

The dashboard never invents money amounts. Credits are the settlement unit,
``CreditLedger`` is the financial source of truth, and proof events explain
where a job's scene-generation credits were spent and how long each stage took.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import CreditLedger, GenerationJob, Project
from app.services import credits

GENERATION_STAGES = {"keyframes", "video"}


def _as_int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def event_credits(event: dict[str, Any]) -> int:
    """Read a proof event's credit attribution, tolerating old/malformed rows."""
    cost = event.get("cost")
    if not isinstance(cost, dict):
        return 0
    return _as_int(cost.get("credits"))


def job_events(job: GenerationJob) -> list[dict[str, Any]]:
    raw = getattr(job, "proof_events", None)
    if not isinstance(raw, list):
        return []
    return [event for event in raw if isinstance(event, dict)]


def attributed_job_credits(events: list[dict[str, Any]]) -> int:
    """Attribute a job's charge to the stage that produced its scenes.

    New jobs record the per-scene charge on ``keyframes`` (image pipeline) or
    ``video`` (native T2V). Legacy jobs recorded it on ``store``; fall back to
    that single entry so historical proof documents still produce a report.
    """
    total = sum(
        event_credits(event)
        for event in events
        if str(event.get("stage") or "") in GENERATION_STAGES
    )
    if total:
        return total
    return sum(
        event_credits(event)
        for event in events
        if str(event.get("stage") or "") == "store"
    )


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _status(job: GenerationJob) -> str:
    status = getattr(job, "status", "")
    return str(getattr(status, "value", status))


def build_report(session: Session, user_id: UUID, limit: int) -> dict[str, Any]:
    """Build one owner-scoped cost report; ``limit`` caps the job-level detail."""
    charged: int = int(
        session.execute(
            select(func.coalesce(func.sum(-CreditLedger.delta), 0)).where(
                CreditLedger.user_id == user_id,
                CreditLedger.reason == "job_charge",
            )
        ).scalar_one()
    )
    refunded: int = int(
        session.execute(
            select(func.coalesce(func.sum(CreditLedger.delta), 0)).where(
                CreditLedger.user_id == user_id,
                CreditLedger.reason.like("refund_job_%"),
            )
        ).scalar_one()
    )

    jobs = session.scalars(
        select(GenerationJob)
        .join(Project, Project.id == GenerationJob.project_id)
        .where(Project.user_id == user_id)
        .order_by(GenerationJob.created_at.desc(), GenerationJob.id.desc())
        .limit(max(1, min(limit, 200)))
    ).all()

    stage_totals: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"stage": "", "events": 0, "duration_ms": 0, "credits": 0}
    )
    model_totals: dict[tuple[str, str, bool], dict[str, Any]] = defaultdict(
        lambda: {
            "provider": "",
            "model_version": "",
            "simulated": False,
            "jobs": 0,
            "events": 0,
            "duration_ms": 0,
            "credits": 0,
            "job_ids": set(),
        }
    )
    recent_jobs: list[dict[str, Any]] = []
    scenes_generated = 0

    for job in jobs:
        events = job_events(job)
        attributed = attributed_job_credits(events)
        if attributed:
            scenes_generated += _as_int(job.num_scenes)
        job_duration = 0
        for event in events:
            stage = str(event.get("stage") or "unknown")
            duration = _as_int(event.get("duration_ms"))
            billable_stage = stage in GENERATION_STAGES or (
                not attributed and stage == "store"
            )
            event_cost = event_credits(event) if billable_stage else 0
            job_duration += duration

            stage_row = stage_totals[stage]
            stage_row["stage"] = stage
            stage_row["events"] += 1
            stage_row["duration_ms"] += duration
            stage_row["credits"] += event_cost

            key = (
                str(event.get("provider_name") or job.provider_name or ""),
                str(event.get("model_version") or job.model_version or ""),
                bool(event.get("simulated", job.simulated)),
            )
            model_row = model_totals[key]
            model_row["provider"] = key[0]
            model_row["model_version"] = key[1]
            model_row["simulated"] = key[2]
            model_row["events"] += 1
            model_row["duration_ms"] += duration
            model_row["credits"] += event_cost
            model_row["job_ids"].add(job.id)

        recent_jobs.append(
            {
                "job_id": job.id,
                "created_at": _iso(job.created_at),
                "status": _status(job),
                "scenes": _as_int(job.num_scenes),
                "credits_charged": _as_int(job.credits_charged),
                "attributed_credits": attributed,
                "duration_ms": job_duration,
                "model_version": str(job.model_version or ""),
                "simulated": bool(job.simulated),
            }
        )

    stages = sorted(
        (
            {key: value for key, value in row.items() if key != "stage"}
            | {"stage": row["stage"]}
            for row in stage_totals.values()
        ),
        key=lambda row: (-row["credits"], -row["duration_ms"], row["stage"]),
    )
    models = sorted(
        (
            {
                "provider": row["provider"],
                "model_version": row["model_version"],
                "simulated": row["simulated"],
                "jobs": len(row["job_ids"]),
                "events": row["events"],
                "duration_ms": row["duration_ms"],
                "credits": row["credits"],
            }
            for row in model_totals.values()
        ),
        key=lambda row: (-row["credits"], -row["duration_ms"], row["model_version"]),
    )

    return {
        "balance": credits.balance_of(session, user_id),
        "credits_charged": _as_int(charged),
        "credits_refunded": _as_int(refunded),
        "credits_net": _as_int(charged) - _as_int(refunded),
        "jobs_analyzed": len(jobs),
        "scenes_generated": scenes_generated,
        "total_duration_ms": sum(row["duration_ms"] for row in stages),
        "attribution": "scene_generation",
        "stages": stages,
        "models": models,
        "recent_jobs": recent_jobs,
    }
