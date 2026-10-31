"""Content Safety Layer (T-07).

Pre-generation: blocks illegal / harmful prompts before any provider call.
Post-generation: sanity-checks produced artifacts before delivery.

The default term list is intentionally small and extendable via the
SAFETY_EXTRA_BLOCKED_TERMS env variable. It is NOT a substitute for a
production moderation API - it is the honest local minimum.
"""

import re
from dataclasses import dataclass

from app.core.config import settings

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


@dataclass(frozen=True)
class SafetyVerdict:
    allowed: bool
    category: str | None = None
    reason: str | None = None


class SafetyLayer:
    """Stateless prompt/artifact screening. Kept dependency-free and testable."""

    def __init__(self, extra_terms: list[str] | None = None) -> None:
        self.blocked_terms = sorted({*_DEFAULT_BLOCKED_TERMS, *(extra_terms or [])})

    @property
    def max_prompt_chars(self) -> int:
        return settings.SAFETY_MAX_PROMPT_CHARS

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
