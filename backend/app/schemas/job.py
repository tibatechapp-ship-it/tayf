"""Generation job schemas."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import GenerationStatus
from app.services.storage.refs import artifact_url, sign_review

STYLES = ["cinematic", "anime", "3d_render", "watercolor", "photorealistic", "noir"]


class JobCreateIn(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)
    num_scenes: int = Field(default=4, ge=2, le=24)
    aspect: str = Field(default="16:9")
    style: str = Field(default="cinematic", max_length=40)
    require_approvals: bool = False

    model_config = ConfigDict(extra="forbid")


class SceneOut(BaseModel):
    index: int
    description: str
    image_prompt: str = ""
    image_url: str | None = None
    duration_seconds: float


class ApprovalDecisionIn(BaseModel):
    decision: Literal["approve", "reject"]
    note: str | None = Field(default=None, max_length=1000)

    model_config = ConfigDict(extra="forbid")


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
    progress: int = Field(default=0, ge=0, le=100)
    stage: str = "queued"
    output_url: str | None = None
    thumbnail_url: str | None = None
    video_size_bytes: int | None = None
    duration_seconds: float | None = None
    credits_charged: int
    require_approvals: bool = False
    pending_approval: dict[str, Any] | None = None
    approval_history: list[dict[str, Any]] | None = None
    created_at: datetime
    completed_at: datetime | None = None
    scenes: list[SceneOut] = Field(default_factory=list)

    @classmethod
    def from_model(cls, job) -> "JobOut":  # noqa: ANN001
        data = cls.model_validate(job)
        data.provider = job.provider_name
        data.output_url = artifact_url(job.result_url)
        data.thumbnail_url = artifact_url(job.thumbnail_url)
        data.approval_history = job.approval_history or []
        gate = job.pending_approval
        data.pending_approval = (
            {
                "stage": gate.get("stage"),
                "review": sign_review(gate.get("review")),
                "requested_at": gate.get("requested_at"),
                "decision": gate.get("decision"),
                "note": gate.get("note"),
            }
            if isinstance(gate, dict)
            else None
        )
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
                        image_prompt=str(raw.get("image_prompt") or ""),
                        image_url=artifact_url(raw.get("image_url")),
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


class StreamTicketOut(BaseModel):
    """Short-lived capability for native EventSource (cannot send Bearer headers)."""

    job_id: UUID
    ticket: str
    expires_at: datetime
    expires_in: int


class JobProgressEvent(BaseModel):
    """One SSE progress frame. Mirrors JobOut fields needed for a live UI."""

    job_id: UUID
    status: GenerationStatus
    progress: int = Field(ge=0, le=100)
    stage: str
    error_message: str | None = None
    rejection_reason: str | None = None
    output_url: str | None = None
    thumbnail_url: str | None = None
    approval_stage: str | None = None
    completed_at: datetime | None = None

    @classmethod
    def from_model(cls, job) -> "JobProgressEvent":  # noqa: ANN001
        return cls(
            job_id=job.id,
            status=job.status,
            progress=job.progress,
            stage=job.stage,
            error_message=job.error_message,
            rejection_reason=job.rejection_reason,
            output_url=artifact_url(job.result_url),
            thumbnail_url=artifact_url(job.thumbnail_url),
            approval_stage=(job.pending_approval or {}).get("stage")
            if isinstance(job.pending_approval, dict)
            else None,
            completed_at=job.completed_at,
        )


class ProofEventOut(BaseModel):
    """One hash-sealed stage entry from the job's append-only proof trail."""

    seq: int
    stage: str
    started_at: str
    finished_at: str
    duration_ms: int
    provider_name: str
    model_version: str
    simulated: bool
    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)
    verification: dict[str, Any] = Field(default_factory=dict)
    cost: dict[str, Any] = Field(default_factory=dict)
    prev_hash: str
    event_hash: str


class ProofChainOut(BaseModel):
    valid: bool
    count: int
    broken_at: int | None = None


class JobProofOut(BaseModel):
    """A self-contained, verifiable proof document for one generation job."""

    job_id: UUID
    proof_version: int
    document: dict[str, Any]
    events: list[ProofEventOut]
    document_hash: str
    signature: str
    chain: ProofChainOut
