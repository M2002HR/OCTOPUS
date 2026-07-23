"""Deterministic language hints for selecting a configured Edge TTS voice."""

import re

_PERSIAN = re.compile(r"[\u067e\u0686\u0698\u06a9\u06af\u06cc]")
_KURDISH = re.compile("[ێڕڵۆڤ]")
_ARABIC = re.compile(r"[\u0600-\u06ff]")
_TURKISH = re.compile(r"[çğıöşüÇĞİÖŞÜ]")
_CYRILLIC = re.compile(r"[\u0400-\u04ff]")


def language_hint(text: str) -> str | None:
    """Return a conservative language hint from a response's visible script."""
    if not text.strip():
        return None
    if _KURDISH.search(text):
        return "ckb"
    if _PERSIAN.search(text):
        return "fa"
    if _ARABIC.search(text):
        return "ar"
    if _CYRILLIC.search(text):
        return "ru"
    if _TURKISH.search(text):
        return "tr"
    if re.search(r"[A-Za-z]", text):
        return "en"
    return None
