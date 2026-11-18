"""AI provider abstraction (T-05).

Contract: every provider can (1) turn a user prompt into a structured
storyboard and (2) render one keyframe image per scene.

HONESTY RULE: `simulated` must be True ONLY for providers that fabricate
content locally (MockAIProvider). Real providers must set it to False.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import json
import re

ASPECT_TO_SIZE: dict[str, str] = {
    "16:9": "1344x768",
    "9:16": "720x1440",
    "1:1": "1024x1024",
}
VALID_ASPECTS = tuple(ASPECT_TO_SIZE.keys())

MIN_SCENES, MAX_SCENES = 2, 8
MIN_SCENE_SECONDS, MAX_SCENE_SECONDS = 2, 8


class ProviderError(RuntimeError):
    """Raised when a provider fails; surfaces as a FAILED job (with refund)."""


@dataclass(frozen=True)
class Scene:
    index: int
    description: str
    image_prompt: str
    duration_seconds: float


@dataclass(frozen=True)
class Storyboard:
    title: str
    scenes: list[Scene] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(
            {
                "title": self.title,
                "scenes": [
                    {
                        "index": s.index,
                        "description": s.description,
                        "image_prompt": s.image_prompt,
                        "duration_seconds": s.duration_seconds,
                    }
                    for s in self.scenes
                ],
            },
            ensure_ascii=False,
        )


@dataclass(frozen=True)
class KeyframeResult:
    image_bytes: bytes
    extension: str  # "png" | "jpg"
    content_type: str


@dataclass(frozen=True)
class VideoResult:
    video_bytes: bytes
    extension: str  # "mp4" | "webm"
    content_type: str
    duration_seconds: float


class AIProvider(ABC):
    """Abstract provider - swap implementations via AI_PROVIDER env."""

    name: str = "abstract"
    simulated: bool = True

    @property
    def supports_native_video(self) -> bool:
        """True only when the provider renders motion video itself."""
        return False

    @abstractmethod
    async def generate_storyboard(self, prompt: str, num_scenes: int, style: str) -> Storyboard:
        """Convert a free-text prompt into num_scenes structured scenes."""

    async def generate_keyframe(self, image_prompt: str, aspect: str) -> KeyframeResult:
        """Render one still image for a scene description.

        Native T2V providers do not fabricate separate keyframes; the pipeline
        skips this step for them.
        """
        raise ProviderError(f"{self.name} does not render separate keyframes")

    async def generate_video(
        self, storyboard: Storyboard, aspect: str, style: str
    ) -> VideoResult:
        """Render motion video directly. Only native T2V providers override this."""
        raise ProviderError(f"{self.name} does not support native text-to-video")

    @staticmethod
    def video_prompt(storyboard: Storyboard, style: str) -> str:
        """Turn the approved storyboard into one self-contained T2V prompt."""
        beats = "; ".join(
            f"{s.index}. {s.description or s.image_prompt} ({s.duration_seconds:g}s)"
            for s in storyboard.scenes
        )
        return (
            f"{storyboard.title}. {beats}. "
            f"Visual style: {style}. Single continuous cinematic shot sequence."
        ).strip()

    # ---- shared helpers ----

    @staticmethod
    def clamp_num_scenes(num_scenes: int) -> int:
        return max(MIN_SCENES, min(MAX_SCENES, int(num_scenes)))

    @staticmethod
    def _clamp_duration(seconds: float) -> float:
        try:
            value = float(seconds)
        except (TypeError, ValueError):
            value = 4.0
        return max(MIN_SCENE_SECONDS, min(MAX_SCENE_SECONDS, value))

    @staticmethod
    def _extract_json(text: str) -> dict:
        """Parse a JSON object out of an LLM answer (tolerates code fences)."""
        cleaned = text.strip()
        fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
        if fence:
            cleaned = fence.group(1)
        try:
            data = json.loads(cleaned)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
        brace = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if brace:
            try:
                data = json.loads(brace.group(0))
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError:
                pass
        raise ProviderError("could not parse storyboard JSON from provider response")
