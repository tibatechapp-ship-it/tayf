"""AI provider abstraction tests (T-05) - mock path + config validation."""

import pytest

from app.services.ai.base import ProviderError
from app.services.ai.factory import get_ai_provider
from app.services.ai.gateway_provider import ZaiGatewayProvider
from app.services.ai.mock_provider import MockAIProvider


def test_factory_returns_mock_by_default():
    provider = get_ai_provider()
    assert isinstance(provider, MockAIProvider)
    assert provider.simulated is True  # honesty: mock is ALWAYS simulated


def test_factory_rejects_unknown_provider():
    from app.core.config import get_settings

    settings = get_settings()
    original = settings.AI_PROVIDER
    try:
        settings.AI_PROVIDER = "does_not_exist"
        with pytest.raises(ProviderError):
            get_ai_provider()
    finally:
        settings.AI_PROVIDER = original


def test_openai_provider_requires_config(monkeypatch):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "AI_PROVIDER", "openai_compatible")
    monkeypatch.setattr(settings, "OPENAI_BASE_URL", "")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")
    with pytest.raises(ProviderError):
        get_ai_provider()


@pytest.mark.asyncio
async def test_mock_storyboard_shape():
    provider = MockAIProvider()
    storyboard = await provider.generate_storyboard("a fox in the snow", 3, "anime")
    assert len(storyboard.scenes) == 3
    assert storyboard.scenes[0].index == 1
    assert all(2 <= s.duration_seconds <= 8 for s in storyboard.scenes)
    assert storyboard.to_json()  # serializable


@pytest.mark.asyncio
async def test_mock_keyframe_is_real_png_stamped_simulated():
    provider = MockAIProvider()
    result = await provider.generate_keyframe("a fox", "16:9")
    assert result.image_bytes[:8] == b"\x89PNG\r\n\x1a\n"  # real PNG signature
    assert len(result.image_bytes) > 10_000
    assert result.content_type == "image/png"


def test_storyboard_json_extraction_survives_code_fences():
    fenced = '```json\n{"title": "T", "scenes": [{"description": "d", "image_prompt": "p", "duration_seconds": 3}]}\n```'
    data = MockAIProvider._extract_json(fenced)
    assert data["title"] == "T"


def test_gateway_provider_scene_parsing():
    provider = ZaiGatewayProvider()
    data = {
        "title": "Journey",
        "scenes": [
            {"description": "d1", "image_prompt": "p1", "duration_seconds": 99},  # clamped
            {"description": "d2", "image_prompt": "p2", "duration_seconds": 2},
            {"bad": "row"},
        ],
    }
    scenes = provider._parse_scenes(data, expected=3)
    assert len(scenes) == 2
    assert scenes[0].duration_seconds == 8  # clamped to max


def test_image_format_sniffing_is_honest():
    from app.services.ai.gateway_provider import sniff_image_format

    png = sniff_image_format(b"\x89PNG\r\n\x1a\n" + b"fake")
    assert png == ("png", "image/png")
    jpg = sniff_image_format(b"\xff\xd8\xff\xe0" + b"fake")
    assert jpg == ("jpg", "image/jpeg")
    webp = sniff_image_format(b"RIFF\x00\x00\x00\x00WEBP" + b"fake")
    assert webp == ("webp", "image/webp")
    unknown = sniff_image_format(b"\x00\x00\x00\x00")
    assert unknown[0] == "png"  # generic fallback, never mislabeled as AI-verified
