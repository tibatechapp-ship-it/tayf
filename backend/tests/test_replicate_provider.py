"""Focused tests for the Replicate REST plumbing (no network, no SDK)."""

import pytest

import app.services.ai.replicate_t2v_provider as replicate_module
from app.core.config import get_settings
from app.services.ai.base import AIProvider, ProviderError, Scene, Storyboard
from app.services.ai.replicate_t2v_provider import ReplicateT2VProvider

_NO_JSON = object()
_MP4 = b"\x00\x00\x00\x18ftypmp42" + b"x" * 2048


class FakeResponse:
    def __init__(self, *, status_code=200, json_data=_NO_JSON, content=b"", text=""):
        self.status_code = status_code
        self._json = json_data
        self.content = content
        self.text = text

    def json(self):
        if self._json is _NO_JSON:
            raise ValueError("invalid JSON")
        return self._json


class FakeClient:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def request(self, method, url, *, json=None, headers=None):
        self.calls.append((method, url, json, headers))
        if not self.responses:
            raise AssertionError("unexpected extra Replicate request")
        return self.responses.pop(0)

    async def get(self, url, *, headers=None):
        return await self.request("GET", url, headers=headers)


@pytest.fixture
def provider(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "REPLICATE_API_TOKEN", "unit" + "-token")
    return ReplicateT2VProvider()


def _patch_client(monkeypatch, responses):
    created = []

    def factory(*_args, **_kwargs):
        client = FakeClient(responses)
        created.append(client)
        return client

    monkeypatch.setattr(replicate_module.httpx, "AsyncClient", factory)
    monkeypatch.setattr(replicate_module.asyncio, "sleep", lambda _seconds: _noop())
    return created


async def _noop():
    return None


@pytest.mark.asyncio
async def test_create_and_poll_prediction(provider, monkeypatch):
    created = _patch_client(
        monkeypatch,
        [
            FakeResponse(
                json_data={
                    "id": "p1",
                    "status": "starting",
                    "urls": {"get": "https://api.replicate.com/v1/predictions/p1"},
                }
            ),
            FakeResponse(json_data={"id": "p1", "status": "processing"}),
            FakeResponse(json_data={"id": "p1", "status": "succeeded", "output": ["done"]}),
        ],
    )

    prediction = await provider._create_prediction("minimax/h3-highspeed", {"prompt": "x"})
    output = await provider._await_prediction(prediction)

    assert output == ["done"]
    assert created[0].calls[0][0] == "POST"
    assert created[0].calls[0][2]["input"] == {"prompt": "x"}


@pytest.mark.asyncio
async def test_await_prediction_failure_is_provider_error(provider, monkeypatch):
    _patch_client(
        monkeypatch,
        [FakeResponse(json_data={"id": "p2", "status": "failed", "error": "bad model"})],
    )
    with pytest.raises(ProviderError, match="bad model"):
        await provider._await_prediction({"id": "p2", "status": "failed", "error": "bad model"})


@pytest.mark.asyncio
async def test_await_prediction_timeout(provider, monkeypatch):
    _patch_client(monkeypatch, [])
    provider._deadline_seconds = -1
    with pytest.raises(ProviderError, match="timed out"):
        await provider._await_prediction({"id": "p3", "status": "starting"})


@pytest.mark.asyncio
async def test_generate_storyboard_from_real_llm_output(provider, monkeypatch):
    payload = (
        '{"title":"Rain","scenes":['
        '{"description":"rain falls","image_prompt":"rain in neon alley","duration_seconds":4},'
        '{"description":"lantern","image_prompt":"lantern floats","duration_seconds":6}]}'
    )
    _patch_client(
        monkeypatch,
        [FakeResponse(json_data={"id": "p4", "status": "succeeded", "output": [payload]})],
    )

    storyboard = await provider.generate_storyboard("rainy city", 2, "cinematic")

    assert storyboard.title == "Rain"
    assert len(storyboard.scenes) == 2
    assert storyboard.scenes[1].duration_seconds == 6


@pytest.mark.asyncio
async def test_download_video_success(provider, monkeypatch):
    _patch_client(monkeypatch, [FakeResponse(status_code=200, content=_MP4)])
    raw = await provider._download_video("https://replicate.delivery/abc/output.mp4")
    assert raw == _MP4


@pytest.mark.asyncio
async def test_request_json_rejects_http_error(provider, monkeypatch):
    _patch_client(monkeypatch, [FakeResponse(status_code=503, text="unavailable")])
    with pytest.raises(ProviderError, match="HTTP 503"):
        await provider._request_json("GET", "https://api.replicate.com/v1/predictions/p5")


@pytest.mark.asyncio
async def test_request_json_rejects_invalid_json(provider, monkeypatch):
    _patch_client(monkeypatch, [FakeResponse(status_code=200)])
    with pytest.raises(ProviderError, match="invalid JSON"):
        await provider._request_json("GET", "https://api.replicate.com/v1/predictions/p6")


def test_helpers_reject_bad_shapes():
    with pytest.raises(ProviderError, match="unexpected output shape"):
        ReplicateT2VProvider._text_to_string({"unexpected": 1})
    with pytest.raises(ProviderError, match="no output URL"):
        ReplicateT2VProvider._video_url([{"logs": "done"}])
    with pytest.raises(ProviderError, match="non-Replicate"):
        ReplicateT2VProvider._validate_api_url("https://example.com/predictions")


def test_video_duration_is_clamped_to_vendor_range(provider):
    storyboard = Storyboard(
        title="Long",
        scenes=[Scene(index=i, description="x", image_prompt="x", duration_seconds=8) for i in range(1, 9)],
    )
    assert provider._video_duration(storyboard) == 15


@pytest.mark.asyncio
async def test_base_provider_defaults_are_honest():
    class MinimalProvider(AIProvider):
        name = "minimal"

        async def generate_storyboard(self, prompt, num_scenes, style):
            raise NotImplementedError

    minimal = MinimalProvider()
    assert minimal.supports_native_video is False
    with pytest.raises(ProviderError, match="does not render separate keyframes"):
        await minimal.generate_keyframe("x", "16:9")
    with pytest.raises(ProviderError, match="does not support native text-to-video"):
        await minimal.generate_video(Storyboard(title="x"), "16:9", "x")
    prompt = minimal.video_prompt(
        Storyboard(
            title="Rain",
            scenes=[Scene(index=1, description="rain", image_prompt="rain", duration_seconds=4)],
        ),
        "cinematic",
    )
    assert "Rain" in prompt and "cinematic" in prompt
