from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from voice_agent.domain import ChatMessage


class Transcriber(Protocol):
    async def transcribe(self, audio_path: Path, *, language: str | None) -> str: ...


class ChatBrain(Protocol):
    async def reply(self, *, messages: Sequence[ChatMessage], system_prompt: str) -> str: ...


class SpeechSynthesizer(Protocol):
    async def synthesize(
        self, text: str, destination: Path, *, language: str | None = None
    ) -> int: ...


class AudioPlayer(Protocol):
    async def play(self, path: Path) -> None: ...
