"""Pro export: portable, honest download packages for finished jobs.

Three artifact families, all derived from data the job already owns — nothing
is fabricated here:

- SRT subtitles: scene descriptions timed by each scene's ``duration_seconds``.
- Project file: a JSON manifest of the prompt, settings, storyboard and proof
  hash, so a job can be archived or reproduced elsewhere.
- Scene stills: a ZIP of the stored keyframe images (native T2V jobs have no
  separate keyframes and produce an empty, clearly-labelled archive).

Every path is owner-scoped at the endpoint; this module never sees a user id.
"""

from __future__ import annotations

import json
import os
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

from app.core import job_proof
from app.models.base import utc_now
from app.services.storage.factory import get_storage
from app.services.storage.refs import key_from_ref

EXPORT_FORMAT_VERSION = 1
MAX_STILLS_BYTES = 32 * 1024 * 1024  # guard against a pathological archive


def _storyboard_scenes(job: Any) -> list[dict[str, Any]]:
    """Return sorted scene dicts from a job's stored storyboard (JSON or dict)."""
    raw = getattr(job, "storyboard", None)
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return []
    if not isinstance(raw, dict):
        return []
    scenes = [s for s in raw.get("scenes", []) if isinstance(s, dict)]
    try:
        return sorted(scenes, key=lambda s: int(s.get("index", 0)))
    except (TypeError, ValueError):
        return scenes


def _srt_time(seconds: float) -> str:
    """Format seconds as SRT ``HH:MM:SS,mmm`` (non-negative, clamped)."""
    value = max(0.0, float(seconds))
    hours = int(value // 3600)
    minutes = int((value % 3600) // 60)
    secs = int(value % 60)
    millis = int(round((value - int(value)) * 1000))
    if millis == 1000:  # rounding carried into the next second
        secs, millis = secs + 1, 0
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def build_srt(job: Any) -> str:
    """Build an SRT subtitle file from scene descriptions and durations.

    Caption text is the scene description, falling back to image_prompt so a
    scene always produces a cue. Timings are cumulative over scene durations.
    """
    blocks: list[str] = []
    cursor = 0.0
    for seq, scene in enumerate(_storyboard_scenes(job), start=1):
        try:
            duration = max(0.0, float(scene.get("duration_seconds") or 0.0))
        except (TypeError, ValueError):
            duration = 0.0
        text = str(scene.get("description") or scene.get("image_prompt") or "").strip()
        start, end = cursor, cursor + duration
        cursor = end
        blocks.append(f"{seq}\n{_srt_time(start)} --> {_srt_time(end)}\n{text}\n")
    return "\n".join(blocks)


def build_project_file(job: Any) -> dict[str, Any]:
    """Build a portable JSON manifest for one job (neutral keys, no signed URLs)."""
    scenes: list[dict[str, Any]] = []
    for scene in _storyboard_scenes(job):
        try:
            index = int(scene.get("index", 0))
        except (TypeError, ValueError):
            index = 0
        scenes.append(
            {
                "index": index,
                "description": str(scene.get("description") or ""),
                "image_prompt": str(scene.get("image_prompt") or ""),
                "duration_seconds": float(scene.get("duration_seconds") or 0.0),
                "image_ref": key_from_ref(scene.get("image_url")),
            }
        )

    proof_hash: str | None = None
    try:
        document = job_proof.build_document(job)
        proof_hash = job_proof.document_hash(document)
    except Exception:  # pragma: no cover - proof is best-effort metadata
        proof_hash = None

    status = getattr(job, "status", "")
    created_at = getattr(job, "created_at", None)
    completed_at = getattr(job, "completed_at", None)
    return {
        "format": "tayf-project",
        "format_version": EXPORT_FORMAT_VERSION,
        "exported_at": utc_now().isoformat(),
        "job": {
            "id": str(getattr(job, "id", "")),
            "prompt": getattr(job, "prompt", ""),
            "num_scenes": int(getattr(job, "num_scenes", 0) or 0),
            "aspect": getattr(job, "aspect", ""),
            "style": getattr(job, "style", ""),
            "status": str(getattr(status, "value", status)),
            "provider": getattr(job, "provider_name", ""),
            "model_version": getattr(job, "model_version", ""),
            "simulated": bool(getattr(job, "simulated", False)),
            "credits_charged": int(getattr(job, "credits_charged", 0) or 0),
            "created_at": created_at.isoformat() if created_at else None,
            "completed_at": completed_at.isoformat() if completed_at else None,
        },
        "storyboard": {"scenes": scenes},
        "result_ref": key_from_ref(getattr(job, "result_url", None)),
        "thumbnail_ref": key_from_ref(getattr(job, "thumbnail_url", None)),
        "proof_document_hash": proof_hash,
        "honesty": "simulated=true means content was fabricated by the mock provider",
    }


def build_stills_zip(job: Any) -> bytes:
    """Build a ZIP of stored keyframes plus a manifest; tolerate missing images."""
    storage = get_storage()
    included: list[dict[str, Any]] = []
    total = 0
    out: bytes = b""
    from io import BytesIO

    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        for scene in _storyboard_scenes(job):
            ref = scene.get("image_url")
            key = key_from_ref(ref)
            if not key:
                continue
            try:
                data = storage.get_bytes(key)
            except Exception:  # pragma: no cover - storage backend specific
                continue
            total += len(data)
            if total > MAX_STILLS_BYTES:
                break
            ext = os.path.splitext(key)[1].lstrip(".").lower() or "png"
            name = f"scene_{scene.get('index', len(included) + 1)}.{ext}"
            archive.writestr(name, data)
            included.append(
                {
                    "index": scene.get("index"),
                    "file": name,
                    "description": str(scene.get("description") or ""),
                }
            )
        archive.writestr(
            "manifest.json",
            json.dumps(
                {
                    "format": "tayf-stills",
                    "format_version": EXPORT_FORMAT_VERSION,
                    "job_id": str(getattr(job, "id", "")),
                    "count": len(included),
                    "scenes": included,
                },
                ensure_ascii=False,
                indent=2,
            ),
        )
    out = buffer.getvalue()
    return out


def safe_filename(job_id: Any, suffix: str) -> str:
    """Build an ASCII-only attachment filename (no header injection)."""
    clean = "".join(c for c in str(job_id) if c.isalnum() or c in "-_")
    return f"tayf-{clean[:36]}.{suffix}" if clean else f"tayf-export.{suffix}"
