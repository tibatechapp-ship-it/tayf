"""Verifiable per-stage proof for generation jobs.

Every pipeline stage appends one event to ``GenerationJob.proof_events``. Events
form a hash chain: each event stores the previous event's hash plus a SHA-256 of
its own canonical payload. The assembled document is also HMAC-signed with the
same secret seam used by stream tickets, so any edit to inputs, model version,
timings, cost or verification verdicts is detectable.

The trail is bookkeeping only: recording a proof event must never fail a job.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime
from typing import Any

from app.core.config import get_settings

GENESIS_HASH = "0" * 64
PROOF_VERSION = 1


def _canonical(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True, default=str)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def make_event(
    *,
    seq: int,
    stage: str,
    started_at: datetime,
    finished_at: datetime,
    inputs: dict[str, Any] | None = None,
    outputs: dict[str, Any] | None = None,
    verification: dict[str, Any] | None = None,
    cost: dict[str, Any] | None = None,
    provider_name: str = "",
    model_version: str = "",
    simulated: bool = False,
    prev_hash: str = GENESIS_HASH,
) -> dict[str, Any]:
    """Build one chained, hash-sealed proof event."""
    payload = {
        "seq": int(seq),
        "stage": stage,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_ms": max(0, int((finished_at - started_at).total_seconds() * 1000)),
        "provider_name": provider_name,
        "model_version": model_version,
        "simulated": bool(simulated),
        "inputs": inputs or {},
        "outputs": outputs or {},
        "verification": verification or {},
        "cost": cost or {},
        "prev_hash": prev_hash,
    }
    return {**payload, "event_hash": _sha256(_canonical(payload))}


def append_event(job: Any, **kwargs: Any) -> dict[str, Any]:
    """Append a chained event to a job.

    A fresh list is assigned on purpose: SQLAlchemy only flushes a JSON column
    when the value changes structurally, so mutating the existing list in place
    would silently lose the event.
    """
    events = list(getattr(job, "proof_events", None) or [])
    previous = events[-1]["event_hash"] if events else GENESIS_HASH
    event = make_event(prev_hash=previous, **kwargs)
    events.append(event)
    job.proof_events = events
    return event


def build_document(job: Any) -> dict[str, Any]:
    """Assemble the signed proof document from the job's durable fields."""
    return {
        "proof_version": PROOF_VERSION,
        "job_id": str(job.id),
        "project_id": str(job.project_id),
        "prompt": job.prompt,
        "num_scenes": job.num_scenes,
        "aspect": job.aspect,
        "style": job.style,
        "provider_name": job.provider_name,
        "model_version": job.model_version,
        "simulated": bool(job.simulated),
        "credits_charged": job.credits_charged,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "events": list(getattr(job, "proof_events", None) or []),
    }


def verify_events(events: list[Any]) -> dict[str, Any]:
    """Recompute the chain. Reports the first broken sequence when tampered."""
    previous = GENESIS_HASH
    for position, event in enumerate(events, start=1):
        if not isinstance(event, dict):
            return {"valid": False, "count": len(events), "broken_at": position}
        payload = {key: value for key, value in event.items() if key != "event_hash"}
        if payload.get("prev_hash") != previous:
            return {"valid": False, "count": len(events), "broken_at": position}
        if _sha256(_canonical(payload)) != event.get("event_hash"):
            return {"valid": False, "count": len(events), "broken_at": position}
        previous = str(event.get("event_hash"))
    return {"valid": True, "count": len(events), "broken_at": None}


def document_hash(document: dict[str, Any]) -> str:
    """Public hash: anyone holding the JSON can recompute and compare it."""
    return _sha256(_canonical(document))


def _secret() -> bytes:
    return get_settings().jwt_secret_effective.encode("utf-8")


def sign_document(document: dict[str, Any]) -> str:
    """Server-side authenticity tag over the canonical document."""
    return hmac.new(_secret(), _canonical(document).encode("utf-8"), hashlib.sha256).hexdigest()


def verify_document(document: dict[str, Any], signature: str) -> bool:
    return hmac.compare_digest(sign_document(document), signature)
