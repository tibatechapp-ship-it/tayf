"""Generation pipeline: orchestrates storyboard -> keyframes -> compose -> store.

State machine (GenerationJob.status, lowercase StrEnum values on the wire):
  pending    : created, credits charged, waiting for the runner
  processing : storyboard/keyframes/composition in progress
  rejected   : blocked by safety pre-filter BEFORE charging (terminal)
  completed  : real artifact stored, result_url set (terminal)
  failed     : provider/composer error -> full refund (terminal)

The runner runs as a Starlette background task (after the 202 response) and
commits after every state change so GET /api/v1/jobs/{id} polling shows live
progress. Every step commits, so a restart can only lose the current step.
"""

import asyncio
import copy
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.core.safety import get_safety_layer
from app.models import GenerationJob, GenerationStatus, Project
from app.services.ai.base import ProviderError
from app.services.ai.factory import get_ai_provider
from app.services.compose import ComposerError, compose_video
from app.services.credits import refund
from app.services.storage.factory import get_storage


def _now():
    return datetime.now(timezone.utc)


def _fail(db: Session, job: GenerationJob, message: str, category: str | None = None) -> None:
    """Mark FAILED + refund (idempotent: only refunds once)."""
    job = db.get(GenerationJob, job.id)
    if job is None or job.status in GenerationStatus.terminal():
        return
    project = db.get(Project, job.project_id)
    job.status = GenerationStatus.FAILED
    job.error_message = message[:1000]
    job.safety_category = category
    job.completed_at = _now()
    if job.credits_charged > 0 and project is not None:
        refund(db, project.owner_id, job.credits_charged, job_id=job.id)
        job.credits_charged = 0
    db.commit()


async def run_job_pipeline(job_id: str | UUID) -> None:
    if isinstance(job_id, str):
        job_id = UUID(job_id)
    db = SessionLocal()
    try:
        job = db.get(GenerationJob, job_id)
        if job is None or job.status in GenerationStatus.terminal():
            return
        job.status = GenerationStatus.PROCESSING
        db.commit()

        provider = get_ai_provider()
        storage = get_storage()
        safety = get_safety_layer()
        job.provider_name = provider.name
        job.model_version = str(getattr(provider, "model_version", "") or "")
        job.simulated = bool(provider.simulated)
        db.commit()

        # ---- 1) storyboard (real or simulated by provider) ----
        try:
            storyboard = await provider.generate_storyboard(job.prompt, job.num_scenes, job.style)
        except Exception as exc:
            _fail(db, job, f"storyboard failed: {exc}")
            return

        # ---- 2) safety screen the AI-produced text as well ----
        for scene in storyboard.scenes:
            verdict = safety.check_text_block(f"{scene.description} {scene.image_prompt}")
            if not verdict.allowed:
                _fail(db, job, verdict.reason or "blocked by safety layer", verdict.category)
                return

        scenes_payload = [
            {
                "index": s.index,
                "description": s.description,
                "image_prompt": s.image_prompt,
                "duration_seconds": s.duration_seconds,
                "image_url": None,
            }
            for s in storyboard.scenes
        ]
        # NOTE: the deepcopy here is load-bearing. `scenes_payload` is mutated
        # in place by the keyframe step below; if the committed attribute value
        # shared that nested list, SQLAlchemy's old==new check would never see
        # a difference and the image_url update would silently vanish.
        job.storyboard = copy.deepcopy({"title": storyboard.title, "scenes": scenes_payload})
        db.commit()

        # ---- 3) keyframes per scene (stored for the gallery) ----
        frames: list[tuple[bytes, float]] = []
        try:
            for scene in storyboard.scenes:
                keyframe = await provider.generate_keyframe(scene.image_prompt, job.aspect)
                key = f"jobs/{job.id}/scene_{scene.index}.{keyframe.extension}"
                scenes_payload[scene.index - 1]["image_url"] = storage.put_bytes(
                    key, keyframe.image_bytes, keyframe.content_type
                )
                frames.append((keyframe.image_bytes, scene.duration_seconds))
        except Exception as exc:
            _fail(db, job, f"keyframe generation failed: {exc}")
            return
        # deepcopy: the nested payload was mutated in place, and SQLAlchemy
        # only flushes a JSON column when the new value differs structurally
        # from the committed one (shared nested objects would compare equal).
        job.storyboard = copy.deepcopy({"title": storyboard.title, "scenes": scenes_payload})
        db.commit()

        # ---- 4) compose real MP4 (CPU-bound -> thread) ----
        try:
            result = await asyncio.to_thread(compose_video, frames, job.aspect)
        except ComposerError as exc:
            _fail(db, job, f"composition failed: {exc}")
            return

        # ---- 5) post-generation safety + store artifacts ----
        verdict = safety.check_artifact(len(result.video_bytes))
        if not verdict.allowed:
            _fail(db, job, verdict.reason or "artifact failed post-check", verdict.category)
            return

        job.result_url = storage.put_bytes(
            f"jobs/{job.id}/video.mp4", result.video_bytes, "video/mp4"
        )
        if result.thumbnail_bytes:
            job.thumbnail_url = storage.put_bytes(
                f"jobs/{job.id}/thumb.jpg", result.thumbnail_bytes, "image/jpeg"
            )
        job.video_size_bytes = len(result.video_bytes)
        job.duration_seconds = result.duration_seconds
        job.storyboard = copy.deepcopy({"title": storyboard.title, "scenes": scenes_payload})
        job.status = GenerationStatus.COMPLETED
        job.completed_at = _now()
        db.commit()
        print(
            f"[pipeline] job {job_id} completed ({result.duration_seconds}s, "
            f"{len(result.video_bytes)} bytes, provider={provider.name}, "
            f"simulated={provider.simulated})"
        )
    except Exception as exc:  # pragma: no cover - last-resort guard
        try:
            _fail(db, job, f"unexpected pipeline error: {exc}")
        except Exception:
            pass
    finally:
        db.close()
