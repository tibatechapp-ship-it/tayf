"""Provider factory - single place that maps AI_PROVIDER to an implementation."""

import json

from app.core.config import settings
from app.services.ai.base import AIProvider, ProviderError, Scene, Storyboard


def get_ai_provider() -> AIProvider:
    """Return the configured provider. Raises ProviderError on bad config."""
    provider = settings.AI_PROVIDER.strip().lower()
    if provider == "mock":
        from app.services.ai.mock_provider import MockAIProvider

        return MockAIProvider()
    if provider == "zai_gateway":
        from app.services.ai.gateway_provider import ZaiGatewayProvider

        return ZaiGatewayProvider()
    if provider == "openai_compatible":
        from app.services.ai.openai_provider import OpenAICompatibleProvider

        return OpenAICompatibleProvider()
    raise ProviderError(
        f"Unknown AI_PROVIDER='{provider}'. Expected: mock | zai_gateway | openai_compatible"
    )


def parse_storyboard_json(raw: str | None) -> Storyboard | None:
    """Deserialize stored storyboard for API output (tolerates corruption)."""
    if not raw:
        return None
    try:
        data = json.loads(raw)
        scenes = [
            Scene(
                index=int(s.get("index", i + 1)),
                description=str(s.get("description", "")),
                image_prompt=str(s.get("image_prompt", "")),
                duration_seconds=float(s.get("duration_seconds", 4)),
            )
            for i, s in enumerate(data.get("scenes", []))
            if isinstance(s, dict)
        ]
        return Storyboard(title=str(data.get("title", "")), scenes=scenes)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
