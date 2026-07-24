"""English-only response guard for every user-facing assistant channel."""

import unicodedata

# Providers commonly use typography such as curly quotes and non-breaking hyphens
# in otherwise English replies.  Canonicalise that typography before enforcing the
# product's ASCII-only delivery policy.  This is deliberately a small, explicit
# set: characters from another writing system still fail validation below.
_ASCII_TYPOGRAPHY = str.maketrans(
    {
        "\u00a0": " ",
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2212": "-",
        "\u2018": "'",
        "\u2019": "'",
        "\u201a": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u201e": '"',
        "\u2026": "...",
    }
)


def normalize_english_output(text: str) -> str | None:
    """Return deliverable ASCII English, or ``None`` for invalid output."""
    normalized = unicodedata.normalize("NFKC", text).translate(_ASCII_TYPOGRAPHY).strip()
    if not normalized:
        return None
    try:
        normalized.encode("ascii")
    except UnicodeEncodeError:
        return None
    return normalized


def limit_voice_reply(text: str, maximum_characters: int) -> str:
    """Keep a response short enough to complete naturally in a voice turn."""
    if len(text) <= maximum_characters:
        return text
    clipped = text[: maximum_characters + 1]
    boundary = max(clipped.rfind(". "), clipped.rfind("! "), clipped.rfind("? "))
    if boundary >= maximum_characters // 3:
        return clipped[: boundary + 1].strip()
    words = clipped.rsplit(" ", 1)[0].rstrip(" ,;:-")
    return f"{words}." if words and words[-1] not in ".!?" else words


def is_english_output(text: str) -> bool:
    """Accept English output, including normalisable English typography."""
    return normalize_english_output(text) is not None


def fallback_reply() -> str:
    return "Could you please repeat that?"
