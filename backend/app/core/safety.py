"""Content Safety Layer (T-07).

Pre-generation: blocks illegal / harmful prompts before any provider call.
Post-generation: sanity-checks produced artifacts before delivery.

The default term list is intentionally small and extendable via the
SAFETY_EXTRA_BLOCKED_TERMS env variable. When MODERATION_API_URL is configured,
an external moderator is consulted after the local checks; failures are
fail-closed unless MODERATION_FAIL_CLOSED=false is explicitly set.
"""

import re
from dataclasses import dataclass

from app.core.config import settings
from app.core.moderation import ModerationClient, ModerationResult, get_moderation_client

_DEFAULT_BLOCKED_TERMS: list[str] = [
    # child safety (absolute block, EN + AR)
    "child sexual",
    "child porn",
    "csam",
    "child nude",
    "طفل إباحي",
    "إباحية أطفال",
    # weapons / violence instructions
    "bomb making",
    "how to make a bomb",
    "pipe bomb",
    "nerve agent",
    "bioweapon",
    "mass shooting",
    "صنع قنبلة",
    "سلاح بيولوجي",
    # non-consensual sexual content
    "non-consensual",
    "rape scene",
]

_WHITESPACE_RE = re.compile(r"\s+")
_UNSET = object()


@dataclass(frozen=True)
class SafetyVerdict:
    allowed: bool
    category: str | None = None
    reason: str | None = None


class SafetyLayer:
    """Local term screening plus an optional external moderation verdict."""

    def __init__(
        self,
        extra_terms: list[str] | None = None,
        moderator: ModerationClient | None | object = _UNSET,
    ) -> None:
        self.blocked_terms = sorted({*_DEFAULT_BLOCKED_TERMS, *(extra_terms or [])})
        # ``None`` explicitly disables external moderation (useful in tests).
        self.moderator = get_moderation_client() if moderator is _UNSET else moderator

    @property
    def max_prompt_chars(self) -> int:
        return settings.SAFETY_MAX_PROMPT_CHARS

    def _external_verdict(self, normalized: str) -> ModerationResult | None:
        checker = getattr(self.moderator, "check", None)
        if checker is None:
            return None
        result = checker(normalized)
        if result is None or result.allowed:
            return None
        return result

    def check_prompt(self, prompt: str) -> SafetyVerdict:
        text = (prompt or "").strip()
        normalized = _WHITESPACE_RE.sub(" ", text).lower()

        if len(text) < 3:
            return SafetyVerdict(False, "empty", "الوصف قصير جدًا - اكتب 3 أحرف على الأقل")
        if len(text) > self.max_prompt_chars:
            return SafetyVerdict(
                False,
                "too_long",
                f"الوصف يتجاوز الحد الأقصى ({self.max_prompt_chars} حرفًا)",
            )
        for term in self.blocked_terms:
            if term.lower() in normalized:
                return SafetyVerdict(
                    False,
                    "blocked_term",
                    "يتضمن الوصف محتوى مرفوضًا وفق سياسة السلامة ولا يمكن توليده",
                )

        external = self._external_verdict(normalized)
        if external is not None:
            return SafetyVerdict(False, external.category, external.reason)
        return SafetyVerdict(True)

    def check_text_block(self, text: str) -> SafetyVerdict:
        """Screen any AI-produced text (e.g. storyboard image prompts)."""
        return self.check_prompt(text[: self.max_prompt_chars])

    def check_artifact(self, size_bytes: int | None) -> SafetyVerdict:
        """Post-generation sanity check: a real artifact must be non-empty."""
        if size_bytes is None or size_bytes <= 0:
            return SafetyVerdict(False, "empty_artifact", "لم يُنتَج ملف صالح")
        return SafetyVerdict(True)


def get_safety_layer() -> SafetyLayer:
    return SafetyLayer(extra_terms=settings.extra_blocked_terms_list)
