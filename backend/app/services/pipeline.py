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
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.core.metrics import record_job_terminal
from app.core.safety import get_safety_layer
from app.models import GenerationJob, GenerationStatus
from app.services import job_state
from app.services.ai.factory import get_ai_provider
from app.services.compose import ComposerError, compose_video, extract_thumbnail
from app.services.storage.factory import get_storage


def _fail(db: Session, job: GenerationJob, message: str, category: str | None = None) -> bool:
    """Atomically mark FAILED + refund once. False means another writer won."""
    _, changed = job_state.fail(db, job.id, message, category)
    if not changed:
        return False
    db.commit()
    record_job_terminal(GenerationStatus.FAILED.value)
    return True


def _cancelled(db: Session, job: GenerationJob, should_stop=None) -> bool:
    """Cooperative stop check: user cancellation from another session, or the
    worker's heartbeat reporting that lease ownership was lost."""
    fresh = db.get(GenerationJob, job.id)
    if fresh is not None and fresh.status == GenerationStatus.CANCELLED:
        return True
    return bool(should_stop and should_stop())


def _progress(db: Session, job: GenerationJob, percent: int, stage: str) -> None:
    """Commit a live progress checkpoint for GET polling and the SSE stream."""
    job.progress = percent
    job.stage = stage
    db.commit()


async def run_job_pipeline(
    job_id: str | UUID, *, claimed_by: str | None = None, should_stop=None
) -> None:
    """Run the pipeline. `claimed_by` means the durable queue already claimed
    the job; otherwise the job is claimed here (BackgroundTasks dev path)."""
    if isinstance(job_id, str):
        job_id = UUID(job_id)
    db = SessionLocal()
    try:
        if claimed_by is not None:
            job = db.get(GenerationJob, job_id)
            if (
                job is None
                or job.status != GenerationStatus.PROCESSING
                or job.worker_id != claimed_by
            ):
                return
        else:
            job = job_state.start(db, job_id)
            if job is None:  # already claimed, cancelled, or terminal
                return

        provider = get_ai_provider()
        storage = get_storage()
        safety = get_safety_layer()
        job.provider_name = provider.name
        job.model_version = str(getattr(provider, "model_version", "") or "")
        job.simulated = bool(provider.simulated)
        db.commit()
        _progress(db, job, 10, "storyboard")

        # ---- 1) storyboard (real or simulated by provider) ----
        try:
            storyboard = await provider.generate_storyboard(job.prompt, job.num_scenes, job.style)
        except Exception as exc:
            _fail(db, job, f"storyboard failed: {exc}")
            return
        if _cancelled(db, job, should_stop):  # user cancelled while the storyboard was generating
            return

        # ---- 2) safety screen the AI-produced text as well ----
        _progress(db, job, 30, "safety")
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
        storyboard_payload = copy.deepcopy({"title": storyboard.title, "scenes": scenes_payload})
        job.storyboard = copy.deepcopy(storyboard_payload)
        db.commit()

        # ---- 3a) native text-to-video: vendor renders motion directly ----
        if provider.supports_native_video:
            _progress(db, job, 70, "composing")
            try:
                video = await provider.generate_video(storyboard, job.aspect, job.style)
            except Exception as exc:
                _fail(db, job, f"native video generation failed: {exc}")
                return
            if _cancelled(db, job, should_stop):
                return

            _progress(db, job, 85, "storing")
            verdict = safety.check_artifact(len(video.video_bytes))
            if not verdict.allowed:
                _fail(db, job, verdict.reason or "artifact failed post-check", verdict.category)
                return
            result_url = storage.put_bytes(
                f"jobs/{job.id}/video.{video.extension}", video.video_bytes, video.content_type
            )
            try:
                thumbnail_bytes = await asyncio.to_thread(extract_thumbnail, video.video_bytes)
            except Exception:  # thumbnails are best-effort; the video is the artifact
                thumbnail_bytes = None
            thumbnail_url = (
                storage.put_bytes(
                    f"jobs/{job.id}/thumb.jpg", thumbnail_bytes, "image/jpeg"
                )
                if thumbnail_bytes
                else None
            )
            if not job_state.complete(
                db,
                job.id,
                result_url=result_url,
                thumbnail_url=thumbnail_url,
                video_size_bytes=len(video.video_bytes),
                duration_seconds=video.duration_seconds,
                storyboard=storyboard_payload,
            ):
                return
            db.commit()
            record_job_terminal(GenerationStatus.COMPLETED.value)
            print(
                f"[pipeline] job {job_id} completed via native T2V "
                f"({video.duration_seconds}s, {len(video.video_bytes)} bytes, "
                f"provider={provider.name}, simulated={provider.simulated})"
            )
            return

        _progress(db, job, 40, "keyframes")

        # ---- 3b) keyframe path (stored for the gallery) ----
        frames: list[tuple[bytes, float]] = []
        try:
            for scene in storyboard.scenes:
                if _cancelled(db, job, should_stop):  # between keyframes: stop spending money
                    return
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
        _progress(db, job, 70, "composing")

        # ---- 4) compose real MP4 (CPU-bound -> thread) ----
        try:
            result = await asyncio.to_thread(compose_video, frames, job.aspect)
        except ComposerError as exc:
            _fail(db, job, f"composition failed: {exc}")
            return
        if _cancelled(db, job, should_stop):  # cancelled while ffmpeg was running
            return

        # ---- 5) post-generation safety + store artifacts ----
        _progress(db, job, 85, "storing")
        verdict = safety.check_artifact(len(result.video_bytes))
        if not verdict.allowed:
            _fail(db, job, verdict.reason or "artifact failed post-check", verdict.category)
            return

        result_url = storage.put_bytes(
            f"jobs/{job.id}/video.mp4", result.video_bytes, "video/mp4"
        )
        thumbnail_url = None
        if result.thumbnail_bytes:
            thumbnail_url = storage.put_bytes(
                f"jobs/{job.id}/thumb.jpg", result.thumbnail_bytes, "image/jpeg"
            )
        storyboard_payload = copy.deepcopy(
            {"title": storyboard.title, "scenes": scenes_payload}
        )
        if not job_state.complete(
            db,
            job.id,
            result_url=result_url,
            thumbnail_url=thumbnail_url,
            video_size_bytes=len(result.video_bytes),
            duration_seconds=result.duration_seconds,
            storyboard=storyboard_payload,
        ):
            # cancel/fail won while the artifact was being stored
            return
        db.commit()
        record_job_terminal(GenerationStatus.COMPLETED.value)
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
