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

from app.core import arabic_nlp, branding, job_proof
from app.core.metrics import record_job_terminal
from app.core.safety import get_safety_layer
from app.db.session import SessionLocal
from app.models import GenerationJob, GenerationStatus
from app.models.base import utc_now
from app.services import approvals, job_state
from app.services.ai.base import Scene, Storyboard
from app.services.ai.factory import get_ai_provider
from app.services.compose import (
    ComposeResult,
    ComposerError,
    apply_watermark,
    compose_video,
    concat_videos,
    extract_thumbnail,
)
from app.services.storage.factory import get_storage
from app.services.video_chunks import chunk_object_key, plan_chunks


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


def _storyboard_from_job(job: GenerationJob) -> tuple[Storyboard, list[dict], list[dict]]:
    """Rebuild the in-memory storyboard after a resume (no re-generation cost)."""
    raw = job.storyboard if isinstance(job.storyboard, dict) else {}
    scenes: list[Scene] = []
    payload: list[dict] = []
    chunks_raw = raw.get("chunks")
    chunks = (
        [item for item in chunks_raw if isinstance(item, dict)]
        if isinstance(chunks_raw, list)
        else []
    )
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
    return Storyboard(title=str(raw.get("title") or ""), scenes=scenes), payload, chunks


def _stored_bytes(storage, key: object) -> bytes | None:
    """Read a committed artifact, treating a missing file as a cache miss."""
    if not isinstance(key, str) or not key:
        return None
    try:
        return storage.get_bytes(key)
    except Exception:
        return None


def _chunk_credits(total: int, index: int, count: int) -> int:
    """Split the job charge across chunks without losing or duplicating credits."""
    if count <= 0:
        return 0
    base = total // count
    extra = 1 if index < total % count else 0
    return base + extra


def _ensure_chunk_records(
    payload: dict,
    scenes: list[Scene],
    *,
    native: bool,
    job_id: UUID,
) -> list[dict]:
    """Reuse the committed chunk plan, or create one for legacy/new jobs."""
    plan = plan_chunks(scenes, native=native)
    existing = payload.get("chunks")
    if (
        isinstance(existing, list)
        and len(existing) == len(plan)
        and all(isinstance(item, dict) for item in existing)
    ):
        return existing
    records: list[dict] = []
    for chunk in plan:
        records.append(
            {
                "index": chunk.index,
                "scene_start": chunk.scene_start,
                "scene_end": chunk.scene_end,
                "duration_seconds": chunk.duration_seconds,
                "key": chunk_object_key(str(job_id), chunk.index),
                "status": "planned",
            }
        )
    payload["chunks"] = records
    return records


def _chunk_scenes(storyboard: Storyboard, record: dict) -> list[Scene]:
    start = int(record.get("scene_start") or 0)
    end = int(record.get("scene_end") or 0)
    return [scene for scene in storyboard.scenes if start <= scene.index <= end]


def _save_storyboard(
    db: Session,
    job: GenerationJob,
    storyboard: Storyboard,
    scenes_payload: list[dict],
    chunks_payload: list[dict],
) -> None:
    """Persist a structurally new JSON value (SQLAlchemy needs a real change)."""
    job.storyboard = copy.deepcopy(
        {
            "title": storyboard.title,
            "scenes": scenes_payload,
            "chunks": chunks_payload,
        }
    )
    db.commit()


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

        job_brand = branding.job_branding(job.input_params)
        should_watermark = bool(job_brand["watermark"])

        provider = get_ai_provider()
        storage = get_storage()
        safety = get_safety_layer()
        job.provider_name = provider.name
        job.model_version = str(getattr(provider, "model_version", "") or "")
        job.simulated = bool(provider.simulated)
        db.commit()
        chunks_payload: list[dict] = []
        if resume_from == "storyboard":
            storyboard, _, chunks_payload = _storyboard_from_job(job)
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
        chunks_payload = _ensure_chunk_records(
            {"chunks": chunks_payload},
            storyboard.scenes,
            native=provider.supports_native_video,
            job_id=job.id,
        )
        storyboard_payload = copy.deepcopy(
            {
                "title": storyboard.title,
                "scenes": scenes_payload,
                "chunks": chunks_payload,
            }
        )
        job.storyboard = copy.deepcopy(storyboard_payload)
        db.commit()
        chunks_payload = storyboard_payload["chunks"]  # mutate the copy we persist

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
                # The approved final cut is already in storage — never re-generate.
                video_key = str(resume_context["video_key"])
                video_bytes = storage.get_bytes(video_key)
                video_duration = float(resume_context.get("duration_seconds") or 0.0)
                video_extension = str(resume_context.get("extension") or "mp4")
                video_content_type = str(resume_context.get("content_type") or "video/mp4")
                thumbnail_url = resume_context.get("thumbnail_url")
                result_url = None
            else:
                parts: list[tuple[bytes, str, float]] = []
                for record in chunks_payload:
                    if _cancelled(db, job, should_stop):
                        return
                    chunk_scenes = _chunk_scenes(storyboard, record)
                    if not chunk_scenes:
                        continue
                    raw = _stored_bytes(storage, record.get("key"))
                    if raw is None:
                        chunk_started = utc_now()
                        _progress(db, job, 70, "composing")
                        chunk = plan_chunks(chunk_scenes, native=True)[0]
                        try:
                            video = await provider.generate_video(
                                chunk.as_storyboard(f"{storyboard.title} — part {chunk.index + 1}"),
                                job.aspect,
                                job.style,
                            )
                        except Exception as exc:
                            _fail(db, job, f"native video generation failed: {exc}")
                            return
                        if _cancelled(db, job, should_stop):
                            return
                        raw = video.video_bytes
                        extension = video.extension
                        content_type = video.content_type
                        duration = video.duration_seconds
                        storage.store_bytes(str(record["key"]), raw, content_type)
                        record.update(
                            status="done",
                            extension=extension,
                            content_type=content_type,
                            duration_seconds=duration,
                        )
                        # Mark before proofing: a crash between them must never
                        # double-count the same credits on the next restart.
                        record["proofed"] = True
                        _save_storyboard(db, job, storyboard, scenes_payload, chunks_payload)
                        _proof(
                            db,
                            job,
                            stage="video",
                            started_at=chunk_started,
                            inputs={
                                "chunk": record["index"],
                                "scene_start": record["scene_start"],
                                "scene_end": record["scene_end"],
                                "aspect": job.aspect,
                            },
                            outputs={
                                "duration_seconds": duration,
                                "video_size_bytes": len(raw),
                            },
                            verification={"allowed": True, "checker": "provider"},
                            cost={
                                "credits": _chunk_credits(
                                    job.credits_charged, record["index"], len(chunks_payload)
                                ),
                                "basis": "scene_generation",
                            },
                        )
                    else:
                        extension = str(record.get("extension") or "mp4")
                        content_type = str(record.get("content_type") or "video/mp4")
                        duration = float(record.get("duration_seconds") or 0.0)
                        record["status"] = "done"
                        if not record.get("proofed"):
                            record["proofed"] = True
                            _save_storyboard(db, job, storyboard, scenes_payload, chunks_payload)
                            _proof(
                                db,
                                job,
                                stage="video",
                                started_at=utc_now(),
                                inputs={"chunk": record["index"], "resumed": True},
                                outputs={"video_size_bytes": len(raw)},
                                verification={"allowed": True, "checker": "provider"},
                                cost={
                                    "credits": _chunk_credits(
                                        job.credits_charged, record["index"], len(chunks_payload)
                                    ),
                                    "basis": "scene_generation",
                                },
                            )
                    parts.append((raw, extension, duration))

                concat_started = utc_now()
                if len(parts) == 1:
                    # A single chunk is already the final video; avoid a needless
                    # ffmpeg pass (and keep vendor bytes bit-for-bit intact).
                    raw, extension, duration = parts[0]
                    final = ComposeResult(
                        video_bytes=raw,
                        thumbnail_bytes=None,
                        duration_seconds=duration,
                        width=0,
                        height=0,
                    )
                    method = "single-chunk"
                else:
                    try:
                        final = await asyncio.to_thread(concat_videos, parts, job.aspect)
                    except ComposerError as exc:
                        _fail(db, job, f"video concatenation failed: {exc}")
                        return
                    method = "concat-demuxer"
                if _cancelled(db, job, should_stop):
                    return
                video_extension = parts[0][1] if parts else "mp4"
                watermark_applied = False
                if should_watermark:
                    try:
                        branded = await asyncio.to_thread(
                            apply_watermark, final.video_bytes, video_extension
                        )
                    except ComposerError as exc:
                        _fail(db, job, f"branding failed: {exc}")
                        return
                    final = ComposeResult(
                        video_bytes=branded,
                        thumbnail_bytes=None,
                        duration_seconds=final.duration_seconds,
                        width=final.width,
                        height=final.height,
                    )
                    watermark_applied = True
                    # apply_watermark always emits an MP4 container, even when
                    # the vendor chunk was WebM; keep the stored key honest.
                    video_extension = "mp4"
                _proof(
                    db,
                    job,
                    stage="compose",
                    started_at=concat_started,
                    inputs={
                        "chunks": len(parts),
                        "method": method,
                        "watermark": should_watermark,
                        "brand": job_brand["brand"],
                    },
                    outputs={
                        "duration_seconds": final.duration_seconds,
                        "watermark_applied": watermark_applied,
                    },
                    verification={"allowed": True, "checker": "concat"},
                )
                video_bytes = final.video_bytes
                video_duration = final.duration_seconds
                video_content_type = (
                    "video/webm" if video_extension == "webm" else "video/mp4"
                )
                result_url = None
                thumbnail_url = None
                if job.require_approvals:
                    # Store a reviewable preview BEFORE the gate. On resume the
                    # same key is read back instead of calling the vendor again.
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
                            "chunks": len(chunks_payload),
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

        chunk_parts: list[tuple[bytes, str, float]] = []
        legacy_frames: list[tuple[bytes, float]] | None = None
        single_thumbnail: bytes | None = None
        if resume_from == "assets" and resume_context.get("chunk_keys"):
            keys = [str(key) for key in resume_context["chunk_keys"]]
            durations = [float(value) for value in resume_context.get("chunk_durations", [])]
            for key, duration in zip(keys, durations, strict=True):
                raw = _stored_bytes(storage, key)
                if raw is None:
                    _fail(db, job, f"committed chunk is missing: {key}")
                    return
                chunk_parts.append((raw, "mp4", duration))
        else:
            if resume_from == "assets":
                # Legacy approval record from before chunking: keep it working.
                frame_keys = [str(key) for key in resume_context["frame_keys"]]
                durations = [float(value) for value in resume_context["durations"]]
                legacy_frames = [
                    (storage.get_bytes(key), duration)
                    for key, duration in zip(frame_keys, durations, strict=True)
                ]
            else:
                # ---- 3b) keyframe path, rendered one bounded chunk at a time ----
                for record in chunks_payload:
                    if _cancelled(db, job, should_stop):  # stop spending money
                        return
                    chunk_scenes = _chunk_scenes(storyboard, record)
                    if not chunk_scenes:
                        continue
                    chunk_started = utc_now()
                    _progress(db, job, 40, "keyframes")
                    frames: list[tuple[bytes, float]] = []
                    for scene in chunk_scenes:
                        position = scene.index - 1
                        existing_key = (
                            scenes_payload[position].get("image_url")
                            if 0 <= position < len(scenes_payload)
                            else None
                        )
                        image_bytes = _stored_bytes(storage, existing_key)
                        if image_bytes is None:
                            keyframe = await provider.generate_keyframe(
                                scene.image_prompt, job.aspect
                            )
                            key = f"jobs/{job.id}/scene_{scene.index}.{keyframe.extension}"
                            scenes_payload[position]["image_url"] = storage.store_bytes(
                                key, keyframe.image_bytes, keyframe.content_type
                            )
                            image_bytes = keyframe.image_bytes
                        frames.append((image_bytes, scene.duration_seconds))
                    if _cancelled(db, job, should_stop):
                        return

                    chunk_bytes = _stored_bytes(storage, record.get("key"))
                    if chunk_bytes is None:
                        try:
                            composed = await asyncio.to_thread(
                                compose_video, frames, job.aspect, watermark=False
                            )
                        except ComposerError as exc:
                            _fail(db, job, f"chunk composition failed: {exc}")
                            return
                        chunk_bytes = composed.video_bytes
                        chunk_duration = composed.duration_seconds
                        single_thumbnail = composed.thumbnail_bytes
                        storage.store_bytes(str(record["key"]), chunk_bytes, "video/mp4")
                        record.update(
                            status="done",
                            extension="mp4",
                            content_type="video/mp4",
                            duration_seconds=chunk_duration,
                        )
                    else:
                        chunk_duration = float(record.get("duration_seconds") or 0.0)
                        record["status"] = "done"

                    if not record.get("proofed"):
                        record["proofed"] = True
                        _save_storyboard(db, job, storyboard, scenes_payload, chunks_payload)
                        _proof(
                            db,
                            job,
                            stage="keyframes",
                            started_at=chunk_started,
                            inputs={
                                "chunk": record["index"],
                                "scene_start": record["scene_start"],
                                "scene_end": record["scene_end"],
                                "aspect": job.aspect,
                            },
                            outputs={"keyframes_stored": len(frames)},
                            verification={"allowed": True, "checker": "provider"},
                            cost={
                                "credits": _chunk_credits(
                                    job.credits_charged, record["index"], len(chunks_payload)
                                ),
                                "basis": "scene_generation",
                            },
                        )
                    _save_storyboard(db, job, storyboard, scenes_payload, chunks_payload)
                    chunk_parts.append((chunk_bytes, "mp4", chunk_duration))

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
                            "frame_keys": [
                                str(scene.get("image_url")) for scene in scenes_payload
                            ],
                            "durations": [scene.duration_seconds for scene in storyboard.scenes],
                            "chunk_keys": [str(record["key"]) for record in chunks_payload],
                            "chunk_durations": [
                                float(record.get("duration_seconds") or 0.0)
                                for record in chunks_payload
                            ],
                        },
                    ):
                        return
                    return

        compose_started = utc_now()
        _progress(db, job, 70, "composing")

        # ---- 4) final assembly (CPU-bound -> thread) ----
        method = "xfade"
        try:
            if len(chunk_parts) == 1:
                raw, _extension, duration = chunk_parts[0]
                final = ComposeResult(
                    video_bytes=raw,
                    thumbnail_bytes=single_thumbnail,
                    duration_seconds=duration,
                    width=0,
                    height=0,
                )
                method = "single-chunk"
            elif chunk_parts:
                final = await asyncio.to_thread(concat_videos, chunk_parts, job.aspect)
                method = "concat-demuxer"
            elif legacy_frames is not None:
                final = await asyncio.to_thread(compose_video, legacy_frames, job.aspect)
            else:
                raise ComposerError("no frames or chunks available for composition")
        except ComposerError as exc:
            _fail(db, job, f"composition failed: {exc}")
            return
        if _cancelled(db, job, should_stop):  # cancelled while ffmpeg was running
            return
        watermark_applied = False
        if should_watermark:
            try:
                branded = await asyncio.to_thread(apply_watermark, final.video_bytes, "mp4")
            except ComposerError as exc:
                _fail(db, job, f"branding failed: {exc}")
                return
            final = ComposeResult(
                video_bytes=branded,
                thumbnail_bytes=final.thumbnail_bytes,
                duration_seconds=final.duration_seconds,
                width=final.width,
                height=final.height,
            )
            watermark_applied = True
        _proof(
            db,
            job,
            stage="compose",
            started_at=compose_started,
            inputs={
                "aspect": job.aspect,
                "chunks": len(chunk_parts),
                "method": method,
                "watermark": should_watermark,
                "brand": job_brand["brand"],
            },
            outputs={
                "duration_seconds": final.duration_seconds,
                "watermark_applied": watermark_applied,
            },
            verification={"allowed": True, "checker": "compose"},
        )
        result = final

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
            {
                "title": storyboard.title,
                "scenes": scenes_payload,
                "chunks": chunks_payload,
            }
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
