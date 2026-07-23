from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from voice_agent.domain import ChatMessage
from voice_agent.messaging import MediaLibrary, MessageAssistant, ResponseMode
from voice_agent.storage import AuditStore


class FakeClient:
    def __init__(self) -> None:
        self.sent_messages: list[str] = []
        self.sent_files: list[tuple[Path, bool]] = []

    def add_event_handler(self, *args: object) -> None:
        return None

    def remove_event_handler(self, *args: object) -> None:
        return None

    async def send_message(self, peer_id: int, text: str) -> None:
        assert peer_id == 11
        self.sent_messages.append(text)

    async def send_file(
        self, peer_id: int, path: Path, *, caption: str = "", voice_note: bool = False
    ) -> None:
        assert peer_id == 11
        assert path.is_file()
        self.sent_files.append((path, voice_note))


class FakeUAG:
    async def reply(self, *, messages: list[ChatMessage], system_prompt: str) -> str:
        assert messages[-1].content == "سلام"
        assert "send_media" in system_prompt
        return "این فایل برای شماست [[send_media:guide]]"

    async def reply_with_images(self, **kwargs: object) -> str:
        assert kwargs["image_paths"]
        return "تصویر دریافت شد"

    async def transcribe(self, path: Path, *, language: str | None) -> str:
        assert path.is_file()
        return "متن ویس"


class FakeSynthesizer:
    async def synthesize(self, text: str, destination: Path) -> int:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"ogg")
        return 250


class FakeMessage:
    def __init__(
        self,
        *,
        text: str = "",
        voice: bool = False,
        photo: bool = False,
        reply: FakeMessage | None = None,
    ) -> None:
        self.id = 1
        self.message = text
        self.voice = object() if voice else None
        self.audio = None
        self.photo = object() if photo else None
        self.video = None
        self.document = None
        self.reply_to = object() if reply else None
        self._reply = reply
        self.file = SimpleNamespace(size=8, mime_type="image/png" if photo else "audio/ogg")

    async def get_reply_message(self) -> FakeMessage | None:
        return self._reply

    async def download_media(self, *, file: Path) -> str:
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(b"media")
        return str(file)


def settings(tmp_path: Path) -> SimpleNamespace:
    library = tmp_path / "library"
    library.mkdir()
    (library / "guide.jpg").write_bytes(b"image")
    (library / "manifest.json").write_text(
        json.dumps(
            {
                "assets": [
                    {"id": "guide", "file": "guide.jpg", "caption": "Guide image"},
                    {"id": "escape", "file": "../outside.jpg", "caption": "Invalid"},
                ]
            }
        )
    )
    return SimpleNamespace(
        runtime_dir=tmp_path / "runtime",
        message_media_library_dir=library,
        message_media_manifest=library / "manifest.json",
        max_history_messages=8,
        message_default_response="text",
        message_vision_enabled=True,
        message_stt_language=None,
        message_max_media_bytes=1000,
        language="fa",
        system_prompt="base prompt",
        recording_mode="transcript_only",
    )


def make_assistant(tmp_path: Path) -> tuple[MessageAssistant, FakeClient, AuditStore]:
    store = AuditStore(tmp_path / "events.db", tmp_path / "events.jsonl")
    client = FakeClient()
    return (
        MessageAssistant(
            settings=settings(tmp_path),
            client=client,  # type: ignore[arg-type]
            uag=FakeUAG(),  # type: ignore[arg-type]
            synthesizer=FakeSynthesizer(),  # type: ignore[arg-type]
            audit=store,
            allowed_peer_id=11,
        ),
        client,
        store,
    )


def test_media_library_allows_only_manifested_files_inside_root(tmp_path: Path) -> None:
    configured = settings(tmp_path)
    library = MediaLibrary(
        root=configured.message_media_library_dir,
        manifest=configured.message_media_manifest,
    )

    assert list(library.assets()) == ["guide"]
    assert "guide: Guide image" in library.prompt_catalog()


@pytest.mark.asyncio
async def test_text_message_can_send_voice_and_requested_asset(tmp_path: Path) -> None:
    assistant, client, store = make_assistant(tmp_path)

    reply, asset = await assistant._reply(
        input_text="سلام", image_paths=(), trace_id="trace", conversation_id="message:11"
    )
    assert reply == "این فایل برای شماست"
    assert asset and asset.asset_id == "guide"
    await assistant._deliver_reply(
        reply=reply,
        mode=ResponseMode.VOICE,
        trace_id="trace",
        conversation_id="message:11",
    )
    await client.send_file(11, asset.path, caption=asset.caption)

    assert client.sent_files[0][1] is True
    assert client.sent_files[1][1] is False
    store.close()


@pytest.mark.asyncio
async def test_reply_context_adds_referenced_text_photo_and_voice_transcript(
    tmp_path: Path,
) -> None:
    assistant, _, store = make_assistant(tmp_path)
    referenced_voice = FakeMessage(text="", voice=True)
    referencing_voice = FakeMessage(text="جوابش چیه؟", reply=referenced_voice)
    voice_context = await assistant._extract_reply_context(  # type: ignore[arg-type]
        referencing_voice, "voice-trace", "message:11"
    )
    assert voice_context.kind == "voice"
    assert voice_context.text == "متن ویس"
    voice_prompt = assistant._with_reply_context("چی گفت؟", voice_context)
    assert "already been fully transcribed" in voice_prompt
    assert "متن ویس" in voice_prompt

    referenced_photo = FakeMessage(text="این تصویر نمونه است", photo=True)
    referencing_photo = FakeMessage(text="این چیه؟", reply=referenced_photo)
    photo_context = await assistant._extract_reply_context(  # type: ignore[arg-type]
        referencing_photo, "photo-trace", "message:11"
    )
    assert photo_context.kind == "photo"
    assert photo_context.text == "این تصویر نمونه است"
    assert photo_context.image_paths[0].is_file()
    prompt = assistant._with_reply_context("این چیه؟", photo_context)
    assert "replying to a photo" in prompt
    assert "این تصویر نمونه است" in prompt
    store.close()


def test_text_is_the_default_response_mode(tmp_path: Path) -> None:
    assistant, _, store = make_assistant(tmp_path)

    mode, prompt = assistant._response_mode("سلام")

    assert mode is ResponseMode.TEXT
    assert prompt == "سلام"
    store.close()


def test_explicit_text_request_overrides_voice_default(tmp_path: Path) -> None:
    assistant, _, store = make_assistant(tmp_path)

    mode, prompt = assistant._response_mode("/text لطفاً کوتاه جواب بده")

    assert mode is ResponseMode.TEXT
    assert prompt == "لطفاً کوتاه جواب بده"
    store.close()


def test_audio_and_image_attachments_are_classified_by_mime_type(tmp_path: Path) -> None:
    assistant, _, store = make_assistant(tmp_path)
    audio = SimpleNamespace(voice=None, audio=object(), photo=None, video=None, document=object())
    audio.file = SimpleNamespace(mime_type="audio/mpeg")
    image = SimpleNamespace(voice=None, audio=None, photo=None, video=None, document=object())
    image.file = SimpleNamespace(mime_type="image/webp")

    assert assistant._kind(audio) == "audio"  # type: ignore[arg-type]
    assert assistant._media_suffix(audio, ".ogg") == ".mp3"  # type: ignore[arg-type]
    assert assistant._kind(image) == "photo"  # type: ignore[arg-type]
    assert assistant._media_suffix(image, ".jpg") == ".webp"  # type: ignore[arg-type]
    store.close()
