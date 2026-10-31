"""MockAIProvider - OFFLINE SIMULATION. No network, no real AI.

This provider fabricates content locally so the whole product works without
any API key (Termux / tests / demos). Everything it produces is marked
`simulated=True` and every image is stamped "SIMULATED" - we never present
mock output as real generation.
"""

import asyncio
import io

from PIL import Image, ImageDraw

from app.services.ai.base import (
    AIProvider,
    KeyframeResult,
    ProviderError,
    Scene,
    Storyboard,
)

# deterministic palettes per scene index (dark, production-like gradients)
_PALETTES = [
    ((13, 17, 23), (247, 129, 102)),
    ((22, 27, 34), (63, 185, 80)),
    ((15, 20, 30), (210, 153, 34)),
    ((20, 15, 30), (137, 87, 229)),
    ((10, 25, 25), (56, 199, 199)),
    ((30, 15, 20), (248, 81, 73)),
    ((18, 22, 15), (140, 200, 80)),
    ((25, 18, 10), (230, 160, 60)),
]

_SIZE_MAP = {"16:9": (1280, 720), "9:16": (720, 1280), "1:1": (1024, 1024)}


class MockAIProvider(AIProvider):
    name = "mock"
    model_version = "mock-1.0"
    simulated = True

    async def generate_storyboard(self, prompt: str, num_scenes: int, style: str) -> Storyboard:
        await asyncio.sleep(0.2)  # simulate thinking latency
        n = self.clamp_num_scenes(num_scenes)
        beats = ["Opening shot", "Development", "Turning point", "Build-up",
                 "Climax", "Aftermath", "Closing shot", "Final frame"]
        scenes = [
            Scene(
                index=i + 1,
                description=f"[SIMULATED STORYBOARD] {beats[i % len(beats)]} for: {prompt[:120]}",
                image_prompt=f"simulated placeholder image ({style} style) for: {prompt[:120]}",
                duration_seconds=4.0,
            )
            for i in range(n)
        ]
        return Storyboard(title=f"Simulated: {prompt[:60]}", scenes=scenes)

    async def generate_keyframe(self, image_prompt: str, aspect: str) -> KeyframeResult:
        await asyncio.sleep(0.1)  # simulate render latency
        width, height = _SIZE_MAP.get(aspect, (1280, 720))
        try:
            image_bytes = await asyncio.to_thread(self._render_placeholder, width, height, image_prompt)
        except Exception as exc:  # pragma: no cover - Pillow should always work
            raise ProviderError(f"mock keyframe rendering failed: {exc}") from exc
        return KeyframeResult(image_bytes=image_bytes, extension="png", content_type="image/png")

    @staticmethod
    def _render_placeholder(width: int, height: int, label: str) -> bytes:
        """Gradient placeholder with an explicit SIMULATED stamp."""
        top, accent = _PALETTES[len(label) % len(_PALETTES)]
        image = Image.new("RGB", (width, height))
        draw = ImageDraw.Draw(image)
        for y in range(height):
            t = y / max(height - 1, 1)
            color = tuple(int(top[c] + (accent[c] - top[c]) * (0.35 * t)) for c in range(3))
            draw.line([(0, y), (width, y)], fill=color)

        # diagonal "SIMULATED" watermark band (English: fonts + shaping safety)
        band_h = max(height // 6, 60)
        for i in range(-1, 3):
            draw.text(
                (width // 12 + i * 40, height // 2 - band_h // 2 + i * 10),
                "SIMULATED KEYFRAME (MOCK PROVIDER - NOT REAL AI)",
                fill=(232, 236, 241),
            )
        draw.rectangle(
            [width // 8, height // 8, width - width // 8, height - height // 8],
            outline=(232, 236, 241),
            width=max(3, width // 400),
        )
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()
