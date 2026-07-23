"""Private, allowlisted Telegram message assistant with text-first replies."""

from __future__ import annotations

import asyncio
import json
import logging
import mimetypes
import re
import shutil
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from time import monotonic, time
from uuid import uuid4

from telethon import TelegramClient, events
from telethon.tl import types

from voice_agent.adapters.uag import UAGClient
from voice_agent.config import Settings
from voice_agent.domain import ChatMessage
from voice_agent.observability import Event
from voice_agent.ports import SpeechSynthesizer
from voice_agent.storage import AuditStore

logger = logging.getLogger(__name__)

MEDIA_DIRECTIVE = re.compile(r"\[\[send_media:([A-Za-z0-9_.-]+)\]\]")
TEXT_REQUEST = re.compile(r"(?:^/text\b|\b(?:متنی|متن بده|بدون ویس|ویس نده|text)\b)", re.I)
VOICE_REQUEST = re.compile(r"(?:^/voice\b|\b(?:ویس|صوتی|voice)\b)", re.I)


class ResponseMode(StrEnum):
    VOICE = "voice"
    TEXT = "text"


@dataclass(frozen=True, slots=True)
class LibraryAsset:
    asset_id: str
    path: Path
    caption: str


@dataclass(frozen=True, slots=True)
class MessageContent:
    kind: str
    text: str
    image_paths: tuple[Path, ...] = ()


class MediaLibrary:
    """Manifest-backed local assets that the assistant may send but never generate."""

    def __init__(self, *, root: Path, manifest: Path) -> None:
        self.root = root.resolve()
        self.manifest = manifest

    def assets(self) -> dict[str, LibraryAsset]:
        if not self.manifest.is_file():
            return {}
        try:
            payload = json.loads(self.manifest.read_text())
        except (OSError, json.JSONDecodeError):
            return {}
        rows = payload.get("assets", []) if isinstance(payload, dict) else []
        result: dict[str, LibraryAsset] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            asset_id = str(row.get("id") or "")
            file_name = str(row.get("file") or "")
            if not re.fullmatch(r"[A-Za-z0-9_.-]+", asset_id) or not file_name:
                continue
            candidate = (self.root / file_name).resolve()
            if not candidate.is_relative_to(self.root) or not candidate.is_file():
                continue
            result[asset_id] = LibraryAsset(
                asset_id=asset_id,
                path=candidate,
                caption=str(row.get("caption") or "").strip(),
            )
        return result

    def prompt_catalog(self) -> str:
        items = self.assets().values()
        if not items:
            return "No local image or video assets are available to send."
        return "\n".join(f"- {item.asset_id}: {item.caption or item.path.name}" for item in items)


class MessageAssistant:
    def __init__(
        self,
        *,
        settings: Settings,
        client: TelegramClient,
        uag: UAGClient,
        synthesizer: SpeechSynthesizer,
        audit: AuditStore,
        allowed_peer_id: int,
    ) -> None:
        self.settings = settings
        self.client = client
        self.uag = uag
        self.synthesizer = synthesizer
        self.audit = audit
        self.allowed_peer_id = allowed_peer_id
        self.library = MediaLibrary(
            root=settings.message_media_library_dir,
            manifest=settings.message_media_manifest,
        )
        self.histories: dict[int, list[ChatMessage]] = {}
        self._lock = asyncio.Lock()
        self._handler_registered = False

    async def start(self) -> None:
        self.client.add_event_handler(self._on_message, events.NewMessage(incoming=True))
        self._handler_registered = True
        self.audit.append(
            Event(
                "message.service.ready",
                str(uuid4()),
                details={"allowed_peer_id": self.allowed_peer_id},
            )
        )

    async def stop(self) -> None:
        if self._handler_registered:
            self.client.remove_event_handler(self._on_message)
            self._handler_registered = False

    async def _on_message(self, event: events.NewMessage.Event) -> None:
        if not event.is_private or event.sender_id != self.allowed_peer_id:
            return
        async with self._lock:
            await self._process_event(event)

    async def _process_event(self, event: events.NewMessage.Event) -> None:
        trace_id = str(uuid4())
        conversation_id = f"message:{self.allowed_peer_id}"
        started = monotonic()
        message = event.message
        kind = self._kind(message)
        self.audit.append(
            Event(
                "message.received",
                trace_id,
                conversation_id,
                details={"kind": kind, "telegram_message_id": message.id},
            )
        )
        try:
            content = await self._extract_input(message, trace_id, conversation_id)
            if content is None:
                return
            mode, input_text = self._response_mode(content.text)
            reply_context = await self._extract_reply_context(message, trace_id, conversation_id)
            prompt = self._with_reply_context(input_text, reply_context)
            reply, asset = await self._reply(
                input_text=prompt,
                image_paths=(*content.image_paths, *reply_context.image_paths),
                trace_id=trace_id,
                conversation_id=conversation_id,
            )
            if asset is not None:
                await self.client.send_file(self.allowed_peer_id, asset.path, caption=asset.caption)
                self.audit.append(
                    Event(
                        "message.media.sent",
                        trace_id,
                        conversation_id,
                        details={"asset_id": asset.asset_id, "suffix": asset.path.suffix.lower()},
                    )
                )
            await self._deliver_reply(
                reply=reply,
                mode=mode,
                trace_id=trace_id,
                conversation_id=conversation_id,
            )
            if self.settings.recording_mode == "transcript_only":
                self.audit.record_message_turn(
                    occurred_at=time(),
                    trace_id=trace_id,
                    conversation_id=conversation_id,
                    input_kind=kind,
                    input_text=prompt,
                    reply=reply,
                    response_mode=mode.value,
                    media_asset_id=asset.asset_id if asset else None,
                )
            self.audit.append(
                Event(
                    "message.completed",
                    trace_id,
                    conversation_id,
                    details={"elapsed_ms": round((monotonic() - started) * 1000), "mode": mode},
                )
            )
        except Exception as exc:
            logger.exception("message assistant failed")
            self.audit.append(
                Event(
                    "message.failed",
                    trace_id,
                    conversation_id,
                    status="error",
                    details={"error_type": type(exc).__name__},
                )
            )
            await self.client.send_message(
                self.allowed_peer_id,
                "متأسفم، پردازش این پیام با خطا روبه‌رو شد. لطفاً دوباره تلاش کنید.",
            )
        finally:
            for path in (
                self.settings.runtime_dir / "messages" / "incoming" / trace_id,
                self.settings.runtime_dir / "messages" / "outgoing" / f"{trace_id}.ogg",
            ):
                if path.is_dir():
                    shutil.rmtree(path, ignore_errors=True)
                else:
                    path.unlink(missing_ok=True)

    @staticmethod
    def _kind(message: types.Message) -> str:
        if message.voice:
            return "voice"
        if message.audio:
            return "audio"
        if message.photo or MessageAssistant._is_image_attachment(message):
            return "photo"
        if message.video:
            return "video"
        if message.document:
            return "document"
        return "text"

    @staticmethod
    def _is_image_attachment(message: types.Message) -> bool:
        mime_type = message.file.mime_type if message.file else ""
        return bool(mime_type and mime_type.startswith("image/"))

    @staticmethod
    def _media_suffix(message: types.Message, fallback: str) -> str:
        mime_type = message.file.mime_type if message.file else None
        return mimetypes.guess_extension(mime_type or "") or fallback

    async def _extract_input(
        self, message: types.Message, trace_id: str, conversation_id: str
    ) -> MessageContent | None:
        size = int(message.file.size or 0) if message.file else 0
        if size > self.settings.message_max_media_bytes:
            await self.client.send_message(
                self.allowed_peer_id,
                "حجم فایل بیشتر از حد مجاز دستیار است.",
            )
            self.audit.append(
                Event("message.rejected", trace_id, conversation_id, details={"reason": "size"})
            )
            return None
        incoming = self.settings.runtime_dir / "messages" / "incoming" / trace_id
        if message.voice or message.audio:
            suffix = self._media_suffix(message, ".ogg")
            path = await message.download_media(file=incoming / f"audio{suffix}")
            if not path:
                raise RuntimeError("Telegram did not download the audio message")
            self.audit.append(Event("message.stt.started", trace_id, conversation_id))
            text = await self.uag.transcribe(
                Path(path), language=self.settings.message_stt_language
            )
            self.audit.append(
                Event(
                    "message.stt.completed",
                    trace_id,
                    conversation_id,
                    details={"chars": len(text)},
                )
            )
            return MessageContent(kind=self._kind(message), text=text)
        if message.photo or self._is_image_attachment(message):
            path = await message.download_media(
                file=incoming / f"photo{self._media_suffix(message, '.jpg')}"
            )
            if not path:
                raise RuntimeError("Telegram did not download the photo")
            return MessageContent(
                kind="photo",
                text=message.message or "Describe this image.",
                image_paths=(Path(path),),
            )
        if message.video or message.document:
            # Videos/documents are accepted as attachments and may carry a caption. They are not
            # sent to a vision model because Ajil's configured OpenAI-compatible contract supports
            # inline images only; this avoids falsely claiming frame-level video understanding.
            path = await message.download_media(file=incoming)
            self.audit.append(
                Event(
                    "message.attachment.received",
                    trace_id,
                    conversation_id,
                    details={"kind": self._kind(message), "downloaded": bool(path)},
                )
            )
            return MessageContent(
                kind=self._kind(message),
                text=message.message or "I received an attachment without a caption.",
            )
        text = (message.message or "").strip()
        if not text:
            await self.client.send_message(self.allowed_peer_id, "لطفاً متن، ویس یا تصویر بفرستید.")
            return None
        return MessageContent(kind="text", text=text)

    async def _extract_reply_context(
        self, message: types.Message, trace_id: str, conversation_id: str
    ) -> MessageContent:
        if not message.reply_to:
            return MessageContent(kind="none", text="")
        replied = await message.get_reply_message()
        if replied is None:
            self.audit.append(
                Event("message.reply_context.unavailable", trace_id, conversation_id)
            )
            return MessageContent(kind="unavailable", text="")
        size = int(replied.file.size or 0) if replied.file else 0
        if size > self.settings.message_max_media_bytes:
            self.audit.append(
                Event(
                    "message.reply_context.rejected",
                    trace_id,
                    conversation_id,
                    details={"reason": "size", "kind": self._kind(replied)},
                )
            )
            return MessageContent(
                kind="oversize", text="[Referenced attachment exceeded the limit]"
            )

        incoming = self.settings.runtime_dir / "messages" / "incoming" / trace_id / "reply"
        if replied.voice or replied.audio:
            suffix = self._media_suffix(replied, ".ogg")
            path = await replied.download_media(file=incoming / f"audio{suffix}")
            if not path:
                raise RuntimeError("Telegram did not download the replied audio message")
            self.audit.append(Event("message.reply_context.stt.started", trace_id, conversation_id))
            transcript = await self.uag.transcribe(
                Path(path), language=self.settings.message_stt_language
            )
            self.audit.append(
                Event(
                    "message.reply_context.stt.completed",
                    trace_id,
                    conversation_id,
                    details={"chars": len(transcript)},
                )
            )
            content = MessageContent(kind="voice", text=transcript)
        elif replied.photo or self._is_image_attachment(replied):
            path = await replied.download_media(
                file=incoming / f"photo{self._media_suffix(replied, '.jpg')}"
            )
            if not path:
                raise RuntimeError("Telegram did not download the replied photo")
            content = MessageContent(
                kind="photo",
                text=replied.message or "Referenced image.",
                image_paths=(Path(path),),
            )
        elif replied.video or replied.document:
            path = await replied.download_media(file=incoming)
            content = MessageContent(
                kind=self._kind(replied),
                text=replied.message or "Referenced attachment without a caption.",
            )
            self.audit.append(
                Event(
                    "message.reply_context.attachment.received",
                    trace_id,
                    conversation_id,
                    details={"kind": content.kind, "downloaded": bool(path)},
                )
            )
        else:
            content = MessageContent(kind="text", text=(replied.message or "").strip())

        self.audit.append(
            Event(
                "message.reply_context.loaded",
                trace_id,
                conversation_id,
                details={"kind": content.kind, "images": len(content.image_paths)},
            )
        )
        return content

    @staticmethod
    def _with_reply_context(input_text: str, context: MessageContent) -> str:
        if not context.text and not context.image_paths:
            return input_text
        reference = context.text or "[Referenced image without a caption]"
        return (
            f"[The user is replying to a {context.kind} message:]\n{reference}\n\n"
            f"[New message:]\n{input_text}"
        )

    def _response_mode(self, text: str) -> tuple[ResponseMode, str]:
        if TEXT_REQUEST.search(text):
            clean = re.sub(r"^/(?:text)\s*", "", text, flags=re.I).strip()
            return ResponseMode.TEXT, clean or "لطفاً به این پیام به‌صورت متن پاسخ بده."
        if VOICE_REQUEST.search(text):
            clean = re.sub(r"^/(?:voice)\s*", "", text, flags=re.I).strip()
            return ResponseMode.VOICE, clean or "لطفاً به این پیام به‌صورت صوتی پاسخ بده."
        return ResponseMode(self.settings.message_default_response), text

    async def _reply(
        self,
        *,
        input_text: str,
        image_paths: tuple[Path, ...],
        trace_id: str,
        conversation_id: str,
    ) -> tuple[str, LibraryAsset | None]:
        history = self.histories.setdefault(self.allowed_peer_id, [])
        history[:] = history[-self.settings.max_history_messages :]
        system_prompt = self._message_system_prompt()
        self.audit.append(Event("message.ai.started", trace_id, conversation_id))
        if image_paths and self.settings.message_vision_enabled:
            raw_reply = await self.uag.reply_with_images(
                messages=history,
                system_prompt=system_prompt,
                image_paths=image_paths,
                prompt=input_text,
            )
            history.append(ChatMessage("user", f"[Image context received] {input_text}"))
        else:
            raw_reply = await self.uag.reply(
                messages=[*history, ChatMessage("user", input_text)], system_prompt=system_prompt
            )
            history.append(ChatMessage("user", input_text))
        reply, asset = self._extract_media(raw_reply)
        history.append(ChatMessage("assistant", reply))
        history[:] = history[-self.settings.max_history_messages :]
        self.audit.append(
            Event(
                "message.ai.completed",
                trace_id,
                conversation_id,
                details={"chars": len(reply), "media_requested": asset is not None},
            )
        )
        return reply, asset

    def _message_system_prompt(self) -> str:
        return (
            f"{self.settings.system_prompt}\n\n"
            "Reply in the same language as the user's latest message unless they explicitly ask "
            "for another language. Write naturally and directly, as in an ordinary private chat. "
            "Do not volunteer a persona, implementation details, or that you are an assistant/bot. "
            "If asked directly about your identity, answer truthfully. Keep answers concise. "
            "Do not claim to generate images or videos. You may send one existing local media "
            "asset "
            "only by placing [[send_media:ASSET_ID]] at the very end of your response. "
            "Never expose this directive to the user. Available assets:\n"
            f"{self.library.prompt_catalog()}"
        )

    def _extract_media(self, reply: str) -> tuple[str, LibraryAsset | None]:
        match = MEDIA_DIRECTIVE.search(reply)
        clean = MEDIA_DIRECTIVE.sub("", reply).strip()
        asset = self.library.assets().get(match.group(1)) if match else None
        return clean or "انجام شد.", asset

    async def _deliver_reply(
        self, *, reply: str, mode: ResponseMode, trace_id: str, conversation_id: str
    ) -> None:
        if mode is ResponseMode.TEXT:
            await self.client.send_message(self.allowed_peer_id, reply)
            self.audit.append(Event("message.text.sent", trace_id, conversation_id))
            return
        destination = self.settings.runtime_dir / "messages" / "outgoing" / f"{trace_id}.ogg"
        self.audit.append(Event("message.tts.started", trace_id, conversation_id))
        duration_ms = await self.synthesizer.synthesize(reply, destination)
        await self.client.send_file(self.allowed_peer_id, destination, voice_note=True)
        self.audit.append(
            Event(
                "message.voice.sent",
                trace_id,
                conversation_id,
                details={"duration_ms": duration_ms},
            )
        )
