"""Focused tests for chunked long-video support (Batch 1)."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.job import JobCreateIn
from app.services.ai.base import Scene
from app.services.compose import ComposerError, compose_video
from app.services.pipeline import _ensure_chunk_records
from app.services.video_chunks import (
    KEYFRAME_CHUNK_SCENES,
    NATIVE_CHUNK_SECONDS,
    plan_chunks,
    scene_seconds,
)


def _scenes(count: int, seconds: float = 4.0) -> list[Scene]:
    return [
        Scene(
            index=index,
            description=f"scene {index}",
            image_prompt=f"scene {index} in cinematic light",
            duration_seconds=seconds,
        )
        for index in range(1, count + 1)
    ]


def test_planner_bounds_keyframe_and_native_chunks():
    scenes = _scenes(24, seconds=4.0)

    keyframe_chunks = plan_chunks(scenes, native=False)
    assert len(keyframe_chunks) == 3
    assert [len(chunk.scenes) for chunk in keyframe_chunks] == [
        KEYFRAME_CHUNK_SCENES,
        KEYFRAME_CHUNK_SCENES,
        KEYFRAME_CHUNK_SCENES,
    ]
    assert [chunk.scene_start for chunk in keyframe_chunks] == [1, 9, 17]
    assert [chunk.scene_end for chunk in keyframe_chunks] == [8, 16, 24]

    native_chunks = plan_chunks(scenes, native=True)
    assert len(native_chunks) == 8  # 3 x 4s = 12s; a 4th scene would exceed 15s
    assert all(chunk.duration_seconds <= NATIVE_CHUNK_SECONDS for chunk in native_chunks)
    assert native_chunks[0].scene_start == 1
    assert native_chunks[-1].scene_end == 24
    assert sum(len(chunk.scenes) for chunk in native_chunks) == 24


def test_planner_clamps_scene_seconds():
    scenes = _scenes(2, seconds=30.0)
    assert scene_seconds(scenes[0]) == 8.0
    chunks = plan_chunks(scenes, native=True)
    assert sum(chunk.duration_seconds for chunk in chunks) <= 16.0


def test_schema_accepts_24_scenes_but_rejects_25():
    payload = {"prompt": "long film", "num_scenes": 24}
    assert JobCreateIn(**payload).num_scenes == 24
    with pytest.raises(ValidationError):
        JobCreateIn(prompt="too long", num_scenes=25)


def test_chunk_records_are_persisted_for_long_storyboard():
    payload: dict = {}
    records = _ensure_chunk_records(
        payload, _scenes(10), native=False, job_id=uuid4()
    )
    assert payload["chunks"] == records
    assert len(records) == 2
    assert records[0]["scene_end"] == 8
    assert records[1]["scene_start"] == 9
    assert records[0]["status"] == "planned"
    assert records[0]["key"].endswith("chunks/chunk_000.mp4")


def test_concat_videos_joins_rendered_chunks():
    from app.services.ai.mock_provider import MockAIProvider
    from app.services.compose import concat_videos

    provider = MockAIProvider()
    parts = []
    for index in range(2):
        frame = provider._render_placeholder(320, 180, f"chunk {index}")
        result = compose_video([(frame, 1.0)], "16:9")
        parts.append((result.video_bytes, "mp4", result.duration_seconds))

    joined = concat_videos(parts, "16:9")
    assert joined.video_bytes[4:8] == b"ftyp"
    assert joined.duration_seconds >= 1.0
    assert joined.thumbnail_bytes and joined.thumbnail_bytes[:2] == b"\xff\xd8"

    with pytest.raises(ComposerError):
        concat_videos([], "16:9")
