"""VideoComposer tests - real ffmpeg assembly of a tiny video."""

import pytest

from app.services.compose import ComposerError, compose_video
from app.services.ai.mock_provider import MockAIProvider


def _frames(count: int):
    provider = MockAIProvider()
    frames = []
    for i in range(count):
        keyframe = provider._render_placeholder(1280, 720, f"scene {i}")
        frames.append((keyframe, 1.0))
    return frames


def test_compose_single_scene():
    result = compose_video(_frames(1), "16:9")
    assert b"ftyp" in result.video_bytes[:32]  # ISO-BMFF/MP4 signature
    assert len(result.video_bytes) > 10_000
    assert 0.8 <= result.duration_seconds <= 3.0
    assert result.thumbnail_bytes and result.thumbnail_bytes[:2] == b"\xff\xd8"  # JPEG magic


def test_compose_multi_scene_with_transitions():
    result = compose_video(_frames(3), "16:9")
    # 3 x 1.0s segments, 2 x 0.5s transitions => ~2s total
    assert 1.5 <= result.duration_seconds <= 3.5
    assert len(result.video_bytes) > 30_000


def test_compose_rejects_empty_frames():
    with pytest.raises(ComposerError):
        compose_video([], "16:9")
