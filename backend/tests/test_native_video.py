"""Native text-to-video path: the vendor video is stored instead of keyframes+ffmpeg compose."""

import time

from app.services.ai.base import VideoResult
from app.services.ai.mock_provider import MockAIProvider

_FAKE_MP4 = b"\x00\x00\x00\x18ftypmp42" + b"x" * 4096


class NativeVideoProvider(MockAIProvider):
    name = "replicate_t2v"
    model_version = "replicate:unit-video"
    simulated = False

    @property
    def supports_native_video(self) -> bool:
        return True

    async def generate_video(self, storyboard, aspect, style) -> VideoResult:
        return VideoResult(
            video_bytes=_FAKE_MP4,
            extension="mp4",
            content_type="video/mp4",
            duration_seconds=8.0,
        )


def _wait(client, headers, job_id, timeout_s=30) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        job = client.get(f"/api/v1/jobs/{job_id}", headers=headers).json()
        if job["status"] in ("completed", "failed", "rejected", "cancelled"):
            return job
        time.sleep(0.05)
    raise AssertionError("job did not reach a terminal state")


def test_native_t2v_pipeline_stores_vendor_video(client, auth_headers, project_id, monkeypatch):
    import app.services.pipeline as pipeline_module

    monkeypatch.setattr(pipeline_module, "get_ai_provider", NativeVideoProvider)
    monkeypatch.setattr(pipeline_module, "extract_thumbnail", lambda _raw: None)

    headers, _ = auth_headers
    created = client.post(
        f"/api/v1/projects/{project_id}/jobs",
        json={"prompt": "a lantern drifting over a night river", "num_scenes": 2},
        headers=headers,
    )
    assert created.status_code == 202, created.text
    job = _wait(client, headers, created.json()["id"])

    assert job["status"] == "completed", job
    assert job["provider"] == "replicate_t2v"
    assert job["model_version"] == "replicate:unit-video"
    assert job["simulated"] is False
    assert job["duration_seconds"] == 8.0
    assert job["video_size_bytes"] == len(_FAKE_MP4)
    assert job["stage"] == "completed"
    assert job["progress"] == 100

    artifact = client.get(job["output_url"])
    assert artifact.status_code == 200
    assert artifact.headers["content-type"] == "video/mp4"
    assert artifact.content[4:8] == b"ftyp"

    # Native T2V does not fabricate per-scene stills; the storyboard is honest.
    assert len(job["scenes"]) == 2
    assert all(scene["image_url"] is None for scene in job["scenes"])
