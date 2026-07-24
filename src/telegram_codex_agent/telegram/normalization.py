from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from telegram_codex_agent.jobs.models import Attachment, NormalizedInput


def deterministic_inbox_path(root: Path, *, file_unique_id: str, filename: str) -> Path:
    safe = "".join(char if char.isalnum() or char in ".-_" else "_" for char in filename)
    return root / file_unique_id[:2] / f"{file_unique_id}-{safe}"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalize_message(
    message: Any, *, user_id: str, chat_id: str, conversation_id: str
) -> NormalizedInput:
    """Map an aiogram-like message object into a stable internal command input."""
    attachments: list[Attachment] = []
    kind = "text"
    text = getattr(message, "text", None) or getattr(message, "caption", None) or ""
    if getattr(message, "voice", None):
        kind = "voice"
        media = message.voice
        attachments.append(
            Attachment(
                kind="voice",
                telegram_file_id=media.file_id,
                file_unique_id=media.file_unique_id,
                mime_type=getattr(media, "mime_type", "audio/ogg") or "audio/ogg",
                size_bytes=getattr(media, "file_size", 0) or 0,
                caption=text,
            )
        )
    elif getattr(message, "photo", None):
        kind = "photo"
        media = message.photo[-1]
        attachments.append(
            Attachment(
                kind="photo",
                telegram_file_id=media.file_id,
                file_unique_id=media.file_unique_id,
                mime_type="image/jpeg",
                size_bytes=getattr(media, "file_size", 0) or 0,
                caption=text,
            )
        )
    elif getattr(message, "document", None):
        kind = "document"
        media = message.document
        attachments.append(
            Attachment(
                kind="document",
                telegram_file_id=media.file_id,
                file_unique_id=media.file_unique_id,
                mime_type=getattr(media, "mime_type", "application/octet-stream")
                or "application/octet-stream",
                size_bytes=getattr(media, "file_size", 0) or 0,
                caption=text,
            )
        )
    elif getattr(message, "video", None):
        kind = "video"
        media = message.video
        attachments.append(
            Attachment(
                kind="video",
                telegram_file_id=media.file_id,
                file_unique_id=media.file_unique_id,
                mime_type=getattr(media, "mime_type", "video/mp4") or "video/mp4",
                size_bytes=getattr(media, "file_size", 0) or 0,
                caption=text,
            )
        )
    reply = getattr(message, "reply_to_message", None)
    reply_to = None
    if reply is not None:
        reply_to = {
            "telegram_message_id": reply.message_id,
            "text": getattr(reply, "text", None) or getattr(reply, "caption", None) or "",
        }
    return NormalizedInput(
        user_id=user_id,
        chat_id=chat_id,
        conversation_id=conversation_id,
        telegram_message_id=getattr(message, "message_id", None),
        kind=kind,
        text=text,
        attachments=attachments,
        reply_to=reply_to,
        metadata={"forward_origin": bool(getattr(message, "forward_origin", None))},
    )
