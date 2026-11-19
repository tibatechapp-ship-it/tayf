"""Deterministic Arabic text normalization for tayf.

HONESTY RULE: this module performs rule-based normalization only. It never
invents grammar corrections, diacritics or facts. The original prompt stays in
``GenerationJob.prompt``; normalized text is a derived input recorded in the
per-stage proof chain so every change is visible and auditable.
"""

from __future__ import annotations

import re
import unicodedata

# Arabic block, Extended-A and Presentation Forms are all treated as Arabic.
_ARABIC_RANGES: tuple[tuple[int, int], ...] = (
    (0x0600, 0x06FF),
    (0x0750, 0x077F),
    (0x08A0, 0x08FF),
)
_TATWEEL = "\u0640"

# Orthographic normalization. This is not a spelling or grammar correction: it
# only folds equivalent code points into one canonical form for prompts.
_ALEF_TO_BASE = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا"})
_DIGIT_TO_ASCII = str.maketrans(
    {
        "٠": "0",
        "١": "1",
        "٢": "2",
        "٣": "3",
        "٤": "4",
        "٥": "5",
        "٦": "6",
        "٧": "7",
        "٨": "8",
        "٩": "9",
        "۰": "0",
        "۱": "1",
        "۲": "2",
        "۳": "3",
        "۴": "4",
        "۵": "5",
        "۶": "6",
        "۷": "7",
        "۸": "8",
        "۹": "9",
    }
)
_PUNCT_TO_ASCII = str.maketrans({"،": ",", "؛": ";", "؟": "?"})
_WHITESPACE = re.compile(r"\s+")

# Contiguous runs of Arabic / Latin / digits, used for a code-mixing audit.
_CODE_MIX = re.compile(
    r"(?P<digit>[0-9\u0660-\u0669\u06f0-\u06f9]+)"
    r"|(?P<ar>[\u0600-\u065f\u066a-\u06ef\u06fa-\u077f\u08a0-\u08ff]+)"
    r"|(?P<latin>[A-Za-z]+)"
)


def is_arabic_char(char: str) -> bool:
    """True when a single character belongs to an Arabic Unicode block."""
    codepoint = ord(char)
    return any(start <= codepoint <= end for start, end in _ARABIC_RANGES)


def has_arabic(text: str) -> bool:
    """True when the text contains at least one Arabic character."""
    return any(is_arabic_char(char) for char in (text or ""))


def normalize_arabic(text: str) -> str:
    """Return a canonical, deterministic form of Arabic text.

    Unifies alef variants, removes tatweel, maps Arabic-Indic digits and Arabic
    punctuation to ASCII, collapses whitespace and applies Unicode NFKC.
    Diacritics and the letter teh-marbuta are deliberately preserved.
    """
    if not text:
        return ""
    value = unicodedata.normalize("NFKC", text)
    value = value.replace(_TATWEEL, "")
    value = value.translate(_ALEF_TO_BASE)
    value = value.translate(_DIGIT_TO_ASCII)
    value = value.translate(_PUNCT_TO_ASCII)
    return _WHITESPACE.sub(" ", value).strip()


def code_mixing_spans(text: str) -> list[dict[str, str]]:
    """Return ordered ``{kind, text}`` runs for Arabic, Latin and digits."""
    spans: list[dict[str, str]] = []
    for match in _CODE_MIX.finditer(text or ""):
        kind = match.lastgroup
        if kind is None:
            continue
        spans.append({"kind": kind, "text": match.group(0)})
    return spans


def augment_storyboard_system(base: str, *, tashkeel: bool = False) -> str:
    """Append Arabic-aware rules to an existing storyboard system prompt.

    The rules are additive: English-only concepts are unaffected, and the JSON
    contract in ``base`` stays intact.
    """
    diacritics = " or when tashkeel is explicitly requested." if tashkeel else "."
    rules = (
        "Arabic handling rules (apply only when the concept contains Arabic):\n"
        "- Write the title, descriptions and image_prompt in clear Modern Standard Arabic.\n"
        "- Preserve proper names and Latin/code-mixed tokens exactly as supplied; "
        "do not translate them.\n"
        "- Keep digits and punctuation as supplied; never invent numbers.\n"
        "- Do not add diacritics unless the concept already uses them" + diacritics
    )
    return f"{base.strip()}\n\n{rules}"
