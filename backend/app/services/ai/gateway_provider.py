"""ZaiGatewayProvider - REAL generation through the ai-gateway sidecar.

The sidecar (visionforge-studio/ai-gateway) wraps the z-ai-web-dev-sdk:
  POST /v1/chat  {messages}              -> {content}   (real LLM)
  POST /v1/image {prompt,size}           -> {image_base64} (real image model)
This provider performs REAL storyboard + keyframe generation. simulated=False.
"""

import base64
import json

import httpx

from app.core.config import settings
from app.services.ai.base import (
    ASPECT_TO_SIZE,
    AIProvider,
    KeyframeResult,
    ProviderError,
    Scene,
    Storyboard,
)

def sniff_image_format(raw: bytes) -> tuple[str, str]:
    """Return (extension, content_type) from the actual magic bytes.

    Image APIs frequently return JPEG even when asked for PNG; labeling the
    artifact by its REAL format keeps storage and <img> rendering honest.
    """
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        return "png", "image/png"
    if raw[:3] == b"\xff\xd8\xff":
        return "jpg", "image/jpeg"
    if raw[:6] in (b"GIF87a", b"GIF89a"):
        return "gif", "image/gif"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "webp", "image/webp"
    return "png", "image/png"  # unknown bytes: keep the generic container name


_STORYBOARD_SYSTEM = (
    "You are a professional video storyboard director. "
    "The user gives you a video concept. Return ONLY a JSON object, no prose, "
    "no markdown fences, with this exact shape:\n"
    '{"title": "short title", "scenes": [{"description": "what happens in the scene", '
    '"image_prompt": "a rich visual prompt for an image model to render this scene", '
    '"duration_seconds": 4}]}\n'
    "Rules: scene count exactly as requested; image_prompt must be self-contained, "
    "visually concrete, and include the requested style; duration_seconds between 2 and 8; "
    "output valid JSON only."
)


class ZaiGatewayProvider(AIProvider):
    name = "zai_gateway"
    model_version = "zai-gateway-1.0"
    simulated = False

    def __init__(self) -> None:
        self._base_url = settings.AI_GATEWAY_URL.rstrip("/")
        self._timeout = settings.AI_GATEWAY_TIMEOUT
        self._headers = {}
        if settings.AI_GATEWAY_TOKEN:
            self._headers["X-Gateway-Token"] = settings.AI_GATEWAY_TOKEN

    async def generate_storyboard(self, prompt: str, num_scenes: int, style: str) -> Storyboard:
        n = self.clamp_num_scenes(num_scenes)
        user_msg = (
            f'Video concept: "{prompt}". Style: {style}. '
            f"Number of scenes: exactly {n}. Respond with the JSON object only."
        )
        content = await self._chat(
            [
                {"role": "assistant", "content": _STORYBOARD_SYSTEM},
                {"role": "user", "content": user_msg},
            ]
        )
        data = self._extract_json(content)
        scenes = self._parse_scenes(data, n)
        title = str(data.get("title") or prompt[:60]).strip()[:120]
        return Storyboard(title=title, scenes=scenes)

    async def generate_keyframe(self, image_prompt: str, aspect: str) -> KeyframeResult:
        size = ASPECT_TO_SIZE.get(aspect, "1344x768")
        b64 = await self._image(image_prompt, size)
        try:
            raw = base64.b64decode(b64, validate=True)
        except Exception as exc:
            raise ProviderError(f"gateway returned invalid image payload: {exc}") from exc
        if len(raw) < 100:
            raise ProviderError("gateway image payload suspiciously small")
        extension, content_type = sniff_image_format(raw)
        return KeyframeResult(image_bytes=raw, extension=extension, content_type=content_type)

    # ---- gateway plumbing ----

    async def _chat(self, messages: list[dict]) -> str:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url}/v1/chat",
                    json={"messages": messages},
                    headers=self._headers,
                )
        except httpx.HTTPError as exc:
            raise ProviderError(f"ai-gateway unreachable at {self._base_url}: {exc}") from exc
        if response.status_code != 200:
            raise ProviderError(f"ai-gateway chat failed: HTTP {response.status_code}: {response.text[:200]}")
        content = response.json().get("content")
        if not content or not str(content).strip():
            raise ProviderError("ai-gateway returned empty completion")
        return str(content)

    async def _image(self, prompt: str, size: str) -> str:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url}/v1/image",
                    json={"prompt": prompt, "size": size},
                    headers=self._headers,
                )
        except httpx.HTTPError as exc:
            raise ProviderError(f"ai-gateway unreachable at {self._base_url}: {exc}") from exc
        if response.status_code != 200:
            raise ProviderError(f"ai-gateway image failed: HTTP {response.status_code}: {response.text[:200]}")
        b64 = response.json().get("image_base64")
        if not b64:
            raise ProviderError("ai-gateway returned no image data")
        return str(b64)

    def _parse_scenes(self, data: dict, expected: int) -> list[Scene]:
        raw_scenes = data.get("scenes")
        if not isinstance(raw_scenes, list) or not raw_scenes:
            raise ProviderError("storyboard JSON has no scenes list")
        scenes: list[Scene] = []
        for i, raw in enumerate(raw_scenes[:expected], start=1):
            if not isinstance(raw, dict):
                continue
            description = str(raw.get("description") or "").strip()
            image_prompt = str(raw.get("image_prompt") or description).strip()
            if not image_prompt:
                continue
            scenes.append(
                Scene(
                    index=len(scenes) + 1,
                    description=description or image_prompt[:120],
                    image_prompt=image_prompt[:600],
                    duration_seconds=self._clamp_duration(raw.get("duration_seconds", 4)),
                )
            )
        if len(scenes) < 2:
            raise ProviderError(f"storyboard parsed with too few usable scenes ({len(scenes)})")
        return scenes
