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
from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.core import arabic_nlp, job_proof
from app.core.metrics import record_job_terminal
from app.core.safety import get_safety_layer
from app.db.session import SessionLocal
from app.models import GenerationJob, GenerationStatus
from app.models.base import utc_now
from app.services import approvals, job_state
from app.services.ai.base import Scene, Storyboard
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


def _proof(
    db: Session,
    job: GenerationJob,
    *,
    stage: str,
    started_at: datetime,
    inputs: dict | None = None,
    outputs: dict | None = None,
    verification: dict | None = None,
    cost: dict | None = None,
) -> None:
    """Append a proof event. Bookkeeping never fails the actual generation."""
    try:
        job_proof.append_event(
            job,
            seq=len(job.proof_events or []) + 1,
            stage=stage,
            started_at=started_at,
            finished_at=utc_now(),
            inputs=inputs,
            outputs=outputs,
            verification=verification,
            cost=cost,
            provider_name=job.provider_name,
            model_version=job.model_version,
            simulated=job.simulated,
        )
        db.commit()
    except Exception as exc:  # pragma: no cover - proof is strictly additive
        db.rollback()
        print(f"[proof] could not record stage '{stage}': {exc}")


def _storyboard_from_job(job: GenerationJob) -> tuple[Storyboard, list[dict]]:
    """Rebuild the in-memory storyboard after a resume (no re-generation cost)."""
    raw = job.storyboard if isinstance(job.storyboard, dict) else {}
    scenes: list[Scene] = []
    payload: list[dict] = []
    for item in raw.get("scenes", []) if isinstance(raw.get("scenes", []), list) else []:
        if not isinstance(item, dict):
            continue
        index = int(item.get("index") or len(scenes) + 1)
        duration = float(item.get("duration_seconds") or 4.0)
        description = str(item.get("description") or "")
        image_prompt = str(item.get("image_prompt") or "")
        scenes.append(
            Scene(
                index=index,
                description=description,
                image_prompt=image_prompt,
                duration_seconds=duration,
            )
        )
        payload.append(
            {
                "index": index,
                "description": description,
                "image_prompt": image_prompt,
                "duration_seconds": duration,
                "image_url": item.get("image_url"),
            }
        )
    return Storyboard(title=str(raw.get("title") or ""), scenes=scenes), payload


def _hold(
    db: Session,
    job: GenerationJob,
    stage: str,
    *,
    review: dict,
    resume: dict,
) -> bool:
    """Pause for human review. False => the caller must stop immediately."""
    started = utc_now()
    if job.pending_approval is not None:  # a consumed gate must not block the next one
        job.pending_approval = None
        db.commit()
    paused = approvals.request_gate(db, job.id, stage, review=review, resume=resume)
    if paused:
        _proof(
            db,
            job,
            stage=f"approval:{stage}",
            started_at=started,
            inputs={"review": review},
            verification={"allowed": True, "checker": "human", "decision": "pending"},
        )
    return paused


async def run_job_pipeline(
    job_id: str | UUID,
    *,
    claimed_by: str | None = None,
    should_stop=None,
    resume_from: str | None = None,
) -> None:
    """Run the pipeline. `claimed_by` means the durable queue already claimed
    the job; `resume_from` continues after an approved human gate; otherwise
    the job is claimed here (BackgroundTasks dev path)."""
    if isinstance(job_id, str):
        job_id = UUID(job_id)
    db = SessionLocal()
    try:
        if resume_from is not None:
            job = db.get(GenerationJob, job_id)
            gate = job.pending_approval if job is not None else None
            if (
                job is None
                or job.status != GenerationStatus.PROCESSING
                or not isinstance(gate, dict)
                or gate.get("stage") != resume_from
                or gate.get("decision") != "approve"
            ):
                return
            resume_context = dict(gate.get("resume") or {})
            job.pending_approval = None  # consumed; the decision stays in history
            db.commit()
        elif claimed_by is not None:
            job = db.get(GenerationJob, job_id)
            if (
                job is None
                or job.status != GenerationStatus.PROCESSING
                or job.worker_id != claimed_by
            ):
                return
            resume_context = {}
        else:
            job = job_state.start(db, job_id)
            if job is None:  # already claimed, cancelled, or terminal
                return
            resume_context = {}

        provider = get_ai_provider()
        storage = get_storage()
        safety = get_safety_layer()
        job.provider_name = provider.name
        job.model_version = str(getattr(provider, "model_version", "") or "")
        job.simulated = bool(provider.simulated)
        db.commit()
        if resume_from == "storyboard":
            storyboard, _ = _storyboard_from_job(job)
        else:
            storyboard_started = utc_now()
            _progress(db, job, 10, "storyboard")

            # ---- 1a) Arabic prompt normalization (deterministic, no invented fixes) ----
            nlp_prompt_started = utc_now()
            provider_prompt = job.prompt
            if arabic_nlp.has_arabic(job.prompt):
                normalized_prompt = arabic_nlp.normalize_arabic(job.prompt)
                provider_prompt = normalized_prompt
                _proof(
                    db,
                    job,
                    stage="arabic_nlp",
                    started_at=nlp_prompt_started,
                    inputs={"field": "prompt", "arabic": True, "length": len(job.prompt)},
                    outputs={
                        "normalized": normalized_prompt[:500],
                        "changed": normalized_prompt != job.prompt,
                        "code_mix": arabic_nlp.code_mixing_spans(job.prompt)[:20],
                    },
                    verification={
                        "allowed": True,
                        "checker": "arabic_nlp.rules",
                        "stage": "pre_storyboard",
                    },
                )

            # ---- 1) storyboard (real or simulated by provider) ----
            try:
                storyboard = await provider.generate_storyboard(
                    provider_prompt, job.num_scenes, job.style
                )
            except Exception as exc:
                _fail(db, job, f"storyboard failed: {exc}")
                return
            if _cancelled(db, job, should_stop):  # cancelled while generating
                return
            _proof(
                db,
                job,
                stage="storyboard",
                started_at=storyboard_started,
                inputs={
                    "prompt": provider_prompt,
                    "num_scenes": job.num_scenes,
                    "style": job.style,
                },
                outputs={"title": storyboard.title, "scene_count": len(storyboard.scenes)},
                verification={"allowed": True, "checker": "provider"},
            )

            # ---- 1b) normalize Arabic text produced by the provider ----
            nlp_scene_started = utc_now()
            ar_title = storyboard.title
            ar_scenes = list(storyboard.scenes)
            normalized_fields = 0
            if arabic_nlp.has_arabic(ar_title):
                ar_title = arabic_nlp.normalize_arabic(ar_title)
                normalized_fields += 1
            rebuilt_scenes: list[Scene] = []
            for scene in ar_scenes:
                description = scene.description
                image_prompt = scene.image_prompt
                if arabic_nlp.has_arabic(description):
                    description = arabic_nlp.normalize_arabic(description)
                    normalized_fields += 1
                if arabic_nlp.has_arabic(image_prompt):
                    image_prompt = arabic_nlp.normalize_arabic(image_prompt)
                    normalized_fields += 1
                rebuilt_scenes.append(
                    Scene(
                        index=scene.index,
                        description=description,
                        image_prompt=image_prompt,
                        duration_seconds=scene.duration_seconds,
                    )
                )
            if normalized_fields:
                storyboard = Storyboard(title=ar_title, scenes=rebuilt_scenes)
                _proof(
                    db,
                    job,
                    stage="arabic_nlp",
                    started_at=nlp_scene_started,
                    inputs={"field": "storyboard", "scenes": len(ar_scenes)},
                    outputs={
                        "fields_normalized": normalized_fields,
                        "title": ar_title[:200],
                    },
                    verification={
                        "allowed": True,
                        "checker": "arabic_nlp.rules",
                        "stage": "post_storyboard",
                    },
                )

            # ---- 2) safety screen the AI-produced text as well ----
            safety_started = utc_now()
            _progress(db, job, 30, "safety")
            scenes_checked = 0
            for scene in storyboard.scenes:
                verdict = safety.check_text_block(f"{scene.description} {scene.image_prompt}")
                scenes_checked += 1
                if not verdict.allowed:
                    _proof(
                        db,
                        job,
                        stage="safety_text",
                        started_at=safety_started,
                        inputs={"scenes_checked": scenes_checked},
                        verification={
                            "allowed": False,
                            "checker": "safety.text",
                            "reason": verdict.reason,
                            "category": verdict.category,
                        },
                    )
                    _fail(db, job, verdict.reason or "blocked by safety layer", verdict.category)
                    return
            _proof(
                db,
                job,
                stage="safety_text",
                started_at=safety_started,
                inputs={"scenes_checked": scenes_checked},
                verification={
                    "allowed": True,
                    "checker": "safety.text",
                    "scenes_checked": scenes_checked,
                },
            )

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

        # ---- human gate 1: review the generated script before spending on assets ----
        if job.require_approvals and resume_from is None:
            if not _hold(
                db,
                job,
                "storyboard",
                review=copy.deepcopy(storyboard_payload),
                resume={"stage": "storyboard"},
            ):
                return
            return

        # ---- 3a) native text-to-video: vendor renders motion directly ----
        if provider.supports_native_video:
            if resume_from == "assets":
                # The approved bytes are already in storage — never re-generate.
                video_key = str(resume_context["video_key"])
                video_bytes = storage.get_bytes(video_key)
                video_duration = float(resume_context.get("duration_seconds") or 0.0)
                video_extension = str(resume_context.get("extension") or "mp4")
                video_content_type = str(resume_context.get("content_type") or "video/mp4")
                thumbnail_url = resume_context.get("thumbnail_url")
                result_url = None
            else:
                video_started = utc_now()
                _progress(db, job, 70, "composing")
                try:
                    video = await provider.generate_video(storyboard, job.aspect, job.style)
                except Exception as exc:
                    _fail(db, job, f"native video generation failed: {exc}")
                    return
                if _cancelled(db, job, should_stop):
                    return
                _proof(
                    db,
                    job,
                    stage="video",
                    started_at=video_started,
                    inputs={"aspect": job.aspect, "style": job.style},
                    outputs={
                        "duration_seconds": video.duration_seconds,
                        "video_size_bytes": len(video.video_bytes),
                    },
                    verification={"allowed": True, "checker": "provider"},
                    cost={
                        "credits": job.credits_charged,
                        "basis": "scene_generation",
                    },
                )
                video_bytes = video.video_bytes
                video_duration = video.duration_seconds
                video_extension = video.extension
                video_content_type = video.content_type
                result_url = None
                thumbnail_url = None
                if job.require_approvals:
                    # Store a reviewable preview BEFORE the gate. On resume the
                    # same keys are read back instead of calling the vendor again.
                    video_key = f"jobs/{job.id}/video.{video_extension}"
                    result_url = storage.store_bytes(video_key, video_bytes, video_content_type)
                    try:
                        preview = await asyncio.to_thread(extract_thumbnail, video_bytes)
                    except Exception:
                        preview = None
                    thumbnail_url = (
                        storage.store_bytes(f"jobs/{job.id}/thumb.jpg", preview, "image/jpeg")
                        if preview
                        else None
                    )
                    if not _hold(
                        db,
                        job,
                        "assets",
                        review={
                            "kind": "video",
                            "video_url": result_url,
                            "thumbnail_url": thumbnail_url,
                            "duration_seconds": video_duration,
                        },
                        resume={
                            "video_key": video_key,
                            "extension": video_extension,
                            "content_type": video_content_type,
                            "duration_seconds": video_duration,
                            "thumbnail_url": thumbnail_url,
                        },
                    ):
                        return
                    return

            artifact_started = utc_now()
            _progress(db, job, 85, "storing")
            verdict = safety.check_artifact(len(video_bytes))
            if not verdict.allowed:
                _proof(
                    db,
                    job,
                    stage="safety_artifact",
                    started_at=artifact_started,
                    inputs={"video_size_bytes": len(video_bytes)},
                    verification={
                        "allowed": False,
                        "checker": "safety.artifact",
                        "reason": verdict.reason,
                        "category": verdict.category,
                    },
                )
                _fail(db, job, verdict.reason or "artifact failed post-check", verdict.category)
                return
            _proof(
                db,
                job,
                stage="safety_artifact",
                started_at=artifact_started,
                inputs={"video_size_bytes": len(video_bytes)},
                verification={"allowed": True, "checker": "safety.artifact"},
            )
            store_started = utc_now()
            if thumbnail_url is None and resume_from != "assets":
                try:
                    final_thumb = await asyncio.to_thread(extract_thumbnail, video_bytes)
                except Exception:
                    final_thumb = None
                thumbnail_url = (
                    storage.store_bytes(f"jobs/{job.id}/thumb.jpg", final_thumb, "image/jpeg")
                    if final_thumb
                    else None
                )
            result_url = storage.store_bytes(
                f"jobs/{job.id}/video.{video_extension}", video_bytes, video_content_type
            )
            if not job_state.complete(
                db,
                job.id,
                result_url=result_url,
                thumbnail_url=thumbnail_url,
                video_size_bytes=len(video_bytes),
                duration_seconds=video_duration,
                storyboard=storyboard_payload,
            ):
                return
            db.commit()
            _proof(
                db,
                job,
                stage="store",
                started_at=store_started,
                outputs={"result_url": result_url, "thumbnail_url": thumbnail_url},
                verification={"allowed": True, "checker": "storage"},
            )
            record_job_terminal(GenerationStatus.COMPLETED.value)
            print(
                f"[pipeline] job {job_id} completed via native T2V "
                f"({video_duration}s, {len(video_bytes)} bytes, "
                f"provider={provider.name}, simulated={provider.simulated})"
            )
            return

        if resume_from == "assets":
            frame_keys = [str(key) for key in resume_context["frame_keys"]]
            durations = [float(value) for value in resume_context["durations"]]
            frames = [
                (storage.get_bytes(key), duration)
                for key, duration in zip(frame_keys, durations, strict=True)
            ]
        else:
            keyframes_started = utc_now()
            _progress(db, job, 40, "keyframes")

            # ---- 3b) keyframe path (stored for the gallery) ----
            frames: list[tuple[bytes, float]] = []
            frame_keys: list[str] = []
            try:
                for scene in storyboard.scenes:
                    if _cancelled(db, job, should_stop):  # stop spending money
                        return
                    keyframe = await provider.generate_keyframe(scene.image_prompt, job.aspect)
                    key = f"jobs/{job.id}/scene_{scene.index}.{keyframe.extension}"
                    scenes_payload[scene.index - 1]["image_url"] = storage.store_bytes(
                        key, keyframe.image_bytes, keyframe.content_type
                    )
                    frame_keys.append(key)
                    frames.append((keyframe.image_bytes, scene.duration_seconds))
            except Exception as exc:
                _fail(db, job, f"keyframe generation failed: {exc}")
                return
            # deepcopy: the nested payload was mutated in place, and SQLAlchemy
            # only flushes a JSON column when the new value differs structurally
            # from the committed one (shared nested objects would compare equal).
            job.storyboard = copy.deepcopy({"title": storyboard.title, "scenes": scenes_payload})
            db.commit()
            _proof(
                db,
                job,
                stage="keyframes",
                started_at=keyframes_started,
                inputs={"aspect": job.aspect, "scenes": job.num_scenes},
                outputs={"keyframes_stored": len(frames)},
                verification={"allowed": True, "checker": "provider"},
                cost={
                    "credits": job.credits_charged,
                    "basis": "scene_generation",
                },
            )
            if job.require_approvals:
                if not _hold(
                    db,
                    job,
                    "assets",
                    review={
                        "kind": "images",
                        "scenes": [
                            {
                                "index": scene.get("index"),
                                "description": scene.get("description"),
                                "image_url": scene.get("image_url"),
                            }
                            for scene in scenes_payload
                        ],
                    },
                    resume={
                        "frame_keys": frame_keys,
                        "durations": [duration for _, duration in frames],
                    },
                ):
                    return
                return

        compose_started = utc_now()
        _progress(db, job, 70, "composing")

        # ---- 4) compose real MP4 (CPU-bound -> thread) ----
        try:
            result = await asyncio.to_thread(compose_video, frames, job.aspect)
        except ComposerError as exc:
            _fail(db, job, f"composition failed: {exc}")
            return
        if _cancelled(db, job, should_stop):  # cancelled while ffmpeg was running
            return
        _proof(
            db,
            job,
            stage="compose",
            started_at=compose_started,
            inputs={"aspect": job.aspect, "frames": len(frames)},
            outputs={"duration_seconds": result.duration_seconds},
            verification={"allowed": True, "checker": "compose"},
        )

        # ---- 5) post-generation safety + store artifacts ----
        artifact_started = utc_now()
        _progress(db, job, 85, "storing")
        verdict = safety.check_artifact(len(result.video_bytes))
        if not verdict.allowed:
            _proof(
                db,
                job,
                stage="safety_artifact",
                started_at=artifact_started,
                inputs={"video_size_bytes": len(result.video_bytes)},
                verification={
                    "allowed": False,
                    "checker": "safety.artifact",
                    "reason": verdict.reason,
                    "category": verdict.category,
                },
            )
            _fail(db, job, verdict.reason or "artifact failed post-check", verdict.category)
            return
        _proof(
            db,
            job,
            stage="safety_artifact",
            started_at=artifact_started,
            inputs={"video_size_bytes": len(result.video_bytes)},
            verification={"allowed": True, "checker": "safety.artifact"},
        )
        store_started = utc_now()
        result_url = storage.store_bytes(
            f"jobs/{job.id}/video.mp4", result.video_bytes, "video/mp4"
        )
        thumbnail_url = None
        if result.thumbnail_bytes:
            thumbnail_url = storage.store_bytes(
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
        _proof(
            db,
            job,
            stage="store",
            started_at=store_started,
            outputs={"result_url": result_url, "thumbnail_url": thumbnail_url},
            verification={"allowed": True, "checker": "storage"},
        )
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
