"""ReplicateT2VProvider - real storyboard + NATIVE text-to-video on Replicate.

Two official Replicate models are used:
  1. a chat/LLM model for the JSON storyboard;
  2. MiniMax H3 Highspeed (configurable) for the motion video itself.

This provider does NOT fabricate separate keyframes: the pipeline skips the
keyframe/compose path for it and stores the vendor video directly. simulated
stays False only because the media really comes from the vendor.
"""

from __future__ import annotations

import asyncio
import time
from urllib.parse import urlparse

import httpx

from app.core.config import settings
from app.services.ai.base import (
    AIProvider,
    ProviderError,
    Scene,
    Storyboard,
    VideoResult,
)
from app.services.ai.gateway_provider import _STORYBOARD_SYSTEM

_API_BASE = "https://api.replicate.com/v1"
_ALLOWED_VIDEO_HOSTS = {"replicate.delivery"}
_ALLOWED_ASPECTS = {"16:9", "9:16", "1:1"}


class ReplicateT2VProvider(AIProvider):
    name = "replicate_t2v"
    simulated = False

    def __init__(self) -> None:
        token = settings.REPLICATE_API_TOKEN.strip()
        if not token:
            raise ProviderError(
                "REPLICATE_API_TOKEN must be set in .env to use AI_PROVIDER=replicate_t2v"
            )
        self._token = token
        self._storyboard_model = settings.REPLICATE_STORYBOARD_MODEL.strip()
        self._video_model = settings.REPLICATE_T2V_MODEL.strip()
        version = settings.REPLICATE_T2V_VERSION.strip()
        if version:
            self._video_ref = version if len(version) == 64 else f"{self._video_model}:{version}"
        else:
            self._video_ref = self._video_model
        if not self._storyboard_model or not self._video_model:
            raise ProviderError("Replicate model settings must not be empty")
        self._timeout = settings.AI_GATEWAY_TIMEOUT
        self._poll_seconds = max(0.5, float(settings.REPLICATE_POLL_SECONDS))
        self._deadline_seconds = max(30, int(settings.REPLICATE_PREDICTION_TIMEOUT))
        self._max_video_bytes = max(1024, int(settings.REPLICATE_MAX_VIDEO_BYTES))
        self.model_version = f"replicate:{self._video_ref}"

    @property
    def supports_native_video(self) -> bool:
        return True

    # ---- AIProvider contract ----

    async def generate_storyboard(self, prompt: str, num_scenes: int, style: str) -> Storyboard:
        n = self.clamp_num_scenes(num_scenes)
        user_prompt = (
            f"{_STORYBOARD_SYSTEM}\n\nVideo concept: {prompt}\n"
            f"Style: {style}\nNumber of scenes: exactly {n}. Return JSON only."
        )
        prediction = await self._create_prediction(
            self._storyboard_model,
            {"prompt": user_prompt, "max_tokens": min(4000, 600 + n * 100), "temperature": 0.7},
        )
        output = await self._await_prediction(prediction)
        data = self._extract_json(self._text_to_string(output))
        return Storyboard(
            title=str(data.get("title") or prompt[:60]).strip()[:120],
            scenes=self._parse_scenes(data, n),
        )

    async def generate_video(
        self, storyboard: Storyboard, aspect: str, style: str
    ) -> VideoResult:
        duration = self._video_duration(storyboard)
        ratio = aspect if aspect in _ALLOWED_ASPECTS else "16:9"
        prompt = self.video_prompt(storyboard, style)
        prediction = await self._create_prediction(
            self._video_ref,
            {"prompt": prompt, "duration": duration, "ratio": ratio},
        )
        output = await self._await_prediction(prediction)
        video_url = self._video_url(output)
        raw = await self._download_video(video_url)
        extension, content_type = self._sniff_video(raw)
        return VideoResult(
            video_bytes=raw,
            extension=extension,
            content_type=content_type,
            duration_seconds=float(duration),
        )

    # ---- helpers (public for focused tests) ----

    @staticmethod
    def _text_to_string(output: object) -> str:
        if isinstance(output, str):
            return output
        if isinstance(output, (list, tuple)):
            return "".join(str(part) for part in output)
        if isinstance(output, dict):
            for key in ("text", "content", "output"):
                value = output.get(key)
                if isinstance(value, str):
                    return value
                if isinstance(value, (list, tuple)):
                    return "".join(str(part) for part in value)
        raise ProviderError("Replicate text model returned an unexpected output shape")

    @staticmethod
    def _video_url(output: object) -> str:
        candidates: list[object]
        if isinstance(output, (str, dict)):
            candidates = [output]
        elif isinstance(output, (list, tuple)):
            candidates = list(output)
        else:
            candidates = []
        for item in candidates:
            url = ReplicateT2VProvider._first_url(item)
            if url:
                return url
        raise ProviderError("Replicate video model returned no output URL")

    @staticmethod
    def _first_url(item: object) -> str | None:
        if isinstance(item, str) and item.startswith("https://"):
            return item
        if isinstance(item, dict):
            for key in ("video", "url", "output", "file", "video_url"):
                value = item.get(key)
                if isinstance(value, str) and value.startswith("https://"):
                    return value
                if isinstance(value, (list, tuple)):
                    for sub in value:
                        nested = ReplicateT2VProvider._first_url(sub)
                        if nested:
                            return nested
            for value in item.values():
                if isinstance(value, dict):
                    nested = ReplicateT2VProvider._first_url(value)
                    if nested:
                        return nested
        return None

    @staticmethod
    def _sniff_video(raw: bytes) -> tuple[str, str]:
        if len(raw) >= 12 and raw[4:8] == b"ftyp":
            return "mp4", "video/mp4"
        if len(raw) >= 4 and raw[:4] == b"\x1a\x45\xdf\xa3":
            return "webm", "video/webm"
        raise ProviderError("Replicate returned an unrecognized video container")

    def _video_duration(self, storyboard: Storyboard) -> int:
        total = sum(self._clamp_duration(s.duration_seconds) for s in storyboard.scenes)
        return max(4, min(15, int(round(total))))

    def _parse_scenes(self, data: dict, expected: int) -> list[Scene]:
        raw_scenes = data.get("scenes")
        if not isinstance(raw_scenes, list) or not raw_scenes:
            raise ProviderError("storyboard JSON has no scenes list")
        scenes: list[Scene] = []
        for raw in raw_scenes[:expected]:
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

    # ---- Replicate HTTP plumbing ----

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
            "Prefer": "wait=60",
        }

    async def _create_prediction(self, model: str, model_input: dict) -> dict:
        prediction = await self._request_json(
            "POST",
            f"{_API_BASE}/predictions",
            payload={"version": model, "input": model_input},
        )
        if not isinstance(prediction, dict) or not prediction.get("id"):
            raise ProviderError("Replicate did not return a prediction id")
        return prediction

    async def _await_prediction(self, prediction: dict) -> object:
        started = time.monotonic()
        while True:
            status = str(prediction.get("status") or "").lower()
            if status == "succeeded":
                return prediction.get("output")
            if status in {"failed", "canceled", "aborted"}:
                detail = str(prediction.get("error") or status)[:200]
                raise ProviderError(f"Replicate prediction {status}: {detail}")
            if time.monotonic() - started > self._deadline_seconds:
                raise ProviderError("Replicate prediction timed out")
            get_url = ((prediction.get("urls") or {}).get("get")) or (
                f"{_API_BASE}/predictions/{prediction['id']}"
            )
            self._validate_api_url(get_url)
            await asyncio.sleep(self._poll_seconds)
            fresh = await self._request_json("GET", get_url)
            if not isinstance(fresh, dict):
                raise ProviderError("Replicate status response was not an object")
            prediction = fresh

    async def _request_json(
        self, method: str, url: str, *, payload: dict | None = None
    ) -> object:
        self._validate_api_url(url)
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.request(
                    method, url, json=payload, headers=self._headers
                )
        except httpx.HTTPError as exc:
            raise ProviderError(f"Replicate unreachable: {exc}") from exc
        if response.status_code not in (200, 201):
            raise ProviderError(
                f"Replicate API failed: HTTP {response.status_code}: {response.text[:200]}"
            )
        try:
            return response.json()
        except ValueError as exc:
            raise ProviderError("Replicate API returned invalid JSON") from exc

    async def _download_video(self, url: str) -> bytes:
        hostname = (urlparse(url).hostname or "").lower()
        if hostname not in _ALLOWED_VIDEO_HOSTS and not hostname.endswith(
            ".replicate.delivery"
        ):
            raise ProviderError("Replicate output URL is not on replicate.delivery")
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(url, headers=self._headers)
        except httpx.HTTPError as exc:
            raise ProviderError(f"video download failed: {exc}") from exc
        if response.status_code != 200:
            raise ProviderError(f"video download failed: HTTP {response.status_code}")
        if len(response.content) > self._max_video_bytes:
            raise ProviderError("video output exceeds the configured size limit")
        if len(response.content) < 1024:
            raise ProviderError("video output suspiciously small")
        return response.content

    @staticmethod
    def _validate_api_url(url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != "api.replicate.com":
            raise ProviderError("refusing a non-Replicate prediction URL")
