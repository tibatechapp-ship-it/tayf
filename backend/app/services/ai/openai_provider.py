"""OpenAICompatibleProvider - REAL generation via any OpenAI-compatible API.

Lets the owner "bring your own key" on any machine (Termux included):
OpenAI, OpenRouter, local servers (llama.cpp/LM Studio with image support),
etc. Configure OPENAI_BASE_URL + OPENAI_API_KEY in .env.

This implementation was verified for config validation and contract shape;
live billing-dependent calls are the owner's to enable with their own key.
simulated=False (it performs real network generation when configured).
"""

import base64

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
from app.services.ai.gateway_provider import _STORYBOARD_SYSTEM, sniff_image_format


class OpenAICompatibleProvider(AIProvider):
    name = "openai_compatible"
    model_version = "openai-compatible"
    simulated = False

    def __init__(self) -> None:
        if not (settings.OPENAI_BASE_URL and settings.OPENAI_API_KEY):
            raise ProviderError(
                "OPENAI_BASE_URL and OPENAI_API_KEY must be set in .env to use "
                "AI_PROVIDER=openai_compatible"
            )
        self._base = settings.OPENAI_BASE_URL.rstrip("/")
        self._headers = {"Authorization": f"Bearer {settings.OPENAI_API_KEY}"}
        self._timeout = settings.AI_GATEWAY_TIMEOUT

    async def generate_storyboard(self, prompt: str, num_scenes: int, style: str) -> Storyboard:
        n = self.clamp_num_scenes(num_scenes)
        payload = {
            "messages": [
                {"role": "system", "content": _STORYBOARD_SYSTEM},
                {
                    "role": "user",
                    "content": f'Video concept: "{prompt}". Style: {style}. Scenes: exactly {n}. JSON only.',
                },
            ],
            "temperature": 0.8,
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base}/chat/completions", json=payload, headers=self._headers
                )
        except httpx.HTTPError as exc:
            raise ProviderError(f"provider unreachable: {exc}") from exc
        if response.status_code != 200:
            raise ProviderError(f"chat failed: HTTP {response.status_code}: {response.text[:200]}")
        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("unexpected chat response shape") from exc
        data = self._extract_json(content)
        scenes: list[Scene] = []
        for raw in (data.get("scenes") or [])[:n]:
            if not isinstance(raw, dict):
                continue
            image_prompt = str(raw.get("image_prompt") or raw.get("description") or "").strip()
            if not image_prompt:
                continue
            scenes.append(
                Scene(
                    index=len(scenes) + 1,
                    description=str(raw.get("description") or image_prompt[:120]),
                    image_prompt=image_prompt[:600],
                    duration_seconds=self._clamp_duration(raw.get("duration_seconds", 4)),
                )
            )
        if len(scenes) < 2:
            raise ProviderError("storyboard parsed with too few usable scenes")
        return Storyboard(title=str(data.get("title") or prompt[:60])[:120], scenes=scenes)

    async def generate_keyframe(self, image_prompt: str, aspect: str) -> KeyframeResult:
        size = ASPECT_TO_SIZE.get(aspect, "1344x768")
        payload: dict = {"prompt": image_prompt, "size": size, "response_format": "b64_json"}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base}/images/generations", json=payload, headers=self._headers
                )
        except httpx.HTTPError as exc:
            raise ProviderError(f"provider unreachable: {exc}") from exc
        if response.status_code != 200:
            raise ProviderError(f"image failed: HTTP {response.status_code}: {response.text[:200]}")
        item = response.json().get("data", [{}])[0]
        if item.get("b64_json"):
            raw = base64.b64decode(item["b64_json"])
        elif item.get("url"):
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                file_response = await client.get(item["url"], headers=self._headers)
            if file_response.status_code != 200:
                raise ProviderError(f"image download failed: HTTP {file_response.status_code}")
            raw = file_response.content
        else:
            raise ProviderError("image response had neither b64_json nor url")
        if len(raw) < 100:
            raise ProviderError("image payload suspiciously small")
        extension, content_type = sniff_image_format(raw)
        return KeyframeResult(image_bytes=raw, extension=extension, content_type=content_type)
