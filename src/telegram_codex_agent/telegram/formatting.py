from __future__ import annotations

from html import escape


def split_telegram_text(text: str, limit: int = 3800) -> list[str]:
    """Split at a readable boundary without exceeding Telegram's message ceiling."""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    remainder = text
    while len(remainder) > limit:
        boundary = max(remainder.rfind("\n", 0, limit), remainder.rfind(" ", 0, limit))
        if boundary <= 0:
            boundary = limit
        chunks.append(remainder[:boundary].rstrip())
        remainder = remainder[boundary:].lstrip()
    if remainder:
        chunks.append(remainder)
    return chunks


def as_html(text: str) -> str:
    return escape(text, quote=False)
