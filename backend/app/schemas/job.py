"""Generation job schemas."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.file_tokens import sign_file_url
from app.models.enums import GenerationStatus

STYLES = ["cinematic", "anime", "3d_render", "watercolor", "photorealistic", "noir"]


class JobCreateIn(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)
    num_scenes: int = Field(default=4, ge=2, le=8)
    aspect: str = Field(default="16:9")
    style: str = Field(default="cinematic", max_length=40)

    model_config = ConfigDict(extra="forbid")


class SceneOut(BaseModel):
    index: int
    description: str
    image_url: str | None = None
    duration_seconds: float


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    status: GenerationStatus
    provider: str = ""
    model_version: str = ""
    simulated: bool
    prompt: str
    num_scenes: int
    aspect: str
    style: str
    error_message: str | None = None
    rejection_reason: str | None = None
    safety_category: str | None = None
    output_url: str | None = None
    thumbnail_url: str | None = None
    video_size_bytes: int | None = None
    duration_seconds: float | None = None
    credits_charged: int
    created_at: datetime
    completed_at: datetime | None = None
    scenes: list[SceneOut] = Field(default_factory=list)

    @classmethod
    def from_model(cls, job) -> "JobOut":  # noqa: ANN001
        data = cls.model_validate(job)
        data.provider = job.provider_name
        data.output_url = sign_file_url(job.result_url)
        data.thumbnail_url = sign_file_url(job.thumbnail_url)
        storyboard = _storyboard_dict(job)
        if storyboard:
            scenes: list[SceneOut] = []
            for raw in storyboard.get("scenes", []):
                if not isinstance(raw, dict):
                    continue
                try:
                    index = int(raw.get("index"))
                except (TypeError, ValueError):
                    continue
                scenes.append(
                    SceneOut(
                        index=index,
                        description=str(raw.get("description") or ""),
                        image_url=sign_file_url(raw.get("image_url")),
                        duration_seconds=float(raw.get("duration_seconds") or 4.0),
                    )
                )
            scenes.sort(key=lambda s: s.index)
            data.scenes = scenes
        return data


def _storyboard_dict(job) -> dict[str, Any] | None:  # noqa: ANN001
    raw = getattr(job, "storyboard", None)
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        import json

        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None
    return None


class JobListOut(BaseModel):
    jobs: list[JobOut]
