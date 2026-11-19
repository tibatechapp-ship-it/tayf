"""Deterministic chunk planning for long videos.

A chunk is a contiguous slice of the storyboard that fits one renderer call:
native T2V is limited to ``NATIVE_CHUNK_SECONDS`` of video per prediction, while
the keyframe/compose path stays at the proven ``KEYFRAME_CHUNK_SCENES`` size so
the ffmpeg filter graph never grows without bound.

Chunk state is stored in ``job.storyboard["chunks"]`` (an existing JSON column),
so a restarted worker can read back finished chunk keys instead of regenerating
them. No new database column or migration is involved.
"""

from dataclasses import dataclass

from app.services.ai.base import MAX_SCENE_SECONDS, MIN_SCENE_SECONDS, Scene, Storyboard

KEYFRAME_CHUNK_SCENES = 8
NATIVE_CHUNK_SECONDS = 15


@dataclass(frozen=True)
class SceneChunk:
    index: int
    scenes: tuple[Scene, ...]
    duration_seconds: float

    @property
    def scene_start(self) -> int:
        return self.scenes[0].index

    @property
    def scene_end(self) -> int:
        return self.scenes[-1].index

    def as_storyboard(self, title: str) -> Storyboard:
        """A self-contained storyboard for one provider/composer call."""
        return Storyboard(title=title, scenes=list(self.scenes))


def scene_seconds(scene: Scene) -> float:
    """Match the provider's duration clamp without depending on a provider instance."""
    try:
        value = float(scene.duration_seconds)
    except (TypeError, ValueError):
        value = 4.0
    return max(MIN_SCENE_SECONDS, min(MAX_SCENE_SECONDS, value))


def plan_chunks(scenes: list[Scene] | tuple[Scene, ...], *, native: bool) -> list[SceneChunk]:
    """Split scenes into bounded, contiguous chunks.

    Native chunks are bounded by cumulative seconds (<= 15); keyframe chunks are
    bounded by scene count (<= 8). A single scene never exceeds either bound on
    its own because provider durations are clamped to 2..8 seconds.
    """
    if not scenes:
        return []

    chunks: list[SceneChunk] = []
    current: list[Scene] = []
    total = 0.0

    def flush() -> None:
        nonlocal current, total
        if not current:
            return
        chunks.append(SceneChunk(index=len(chunks), scenes=tuple(current), duration_seconds=round(total, 2)))
        current = []
        total = 0.0

    for scene in scenes:
        seconds = scene_seconds(scene)
        if native and current and total + seconds > NATIVE_CHUNK_SECONDS:
            flush()
        elif not native and len(current) >= KEYFRAME_CHUNK_SCENES:
            flush()
        current.append(scene)
        total += seconds
    flush()
    return chunks


def chunk_object_key(job_id: str, index: int, extension: str = "mp4") -> str:
    """Provider-neutral storage key for one rendered chunk."""
    return f"jobs/{job_id}/chunks/chunk_{index:03d}.{extension}"


def chunk_from_storyboard(storyboard: object, index: int) -> dict | None:
    """Read a previously committed chunk record from a job's storyboard JSON."""
    if not isinstance(storyboard, dict):
        return None
    chunks = storyboard.get("chunks")
    if not isinstance(chunks, list):
        return None
    for record in chunks:
        if isinstance(record, dict) and record.get("index") == index and record.get("status") == "done":
            return record
    return None
