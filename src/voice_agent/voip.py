from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from ntgcalls import MediaSource
from pytgcalls import PyTgCalls
from pytgcalls.types import (
    CallConfig,
    ChatUpdate,
    Device,
    Direction,
    MediaStream,
    RawCallUpdate,
    StreamFrames,
)
from pytgcalls.types.raw import AudioParameters, AudioStream

from voice_agent.audio import VoiceActivityDetector
from voice_agent.audio_turns import PcmTurnAssembler
from voice_agent.domain import AudioTurn
from voice_agent.observability import Event
from voice_agent.storage import AuditStore

logger = logging.getLogger(__name__)


class TelethonVoipEngine:
    """Private-call media adapter that keeps PyTgCalls bound to the existing Telethon client."""

    def __init__(
        self,
        *,
        telethon_client: Any,
        audit: AuditStore,
        call_id: str,
        peer_id: int,
        vad_start_rms: int,
        vad_continue_rms: int,
        vad_start_ms: int,
        vad_end_silence_ms: int,
        vad_min_utterance_ms: int,
        vad_pre_roll_ms: int,
        max_turn_seconds: int,
        call_timeout_seconds: int,
        sample_rate: int,
        channels: int,
        language: str,
        runtime_dir: Path,
        on_utterance: Callable[[AudioTurn], Awaitable[None]],
    ) -> None:
        self.calls = PyTgCalls(telethon_client)
        self.audit = audit
        self.call_id = call_id
        self.peer_id = peer_id
        self.call_timeout_seconds = call_timeout_seconds
        self.language = language
        self.sample_rate = sample_rate
        self.channels = channels
        self.on_utterance = on_utterance
        self.assembler = PcmTurnAssembler(
            output_dir=runtime_dir / "incoming" / call_id,
            end_silence_ms=vad_end_silence_ms,
            min_speech_ms=vad_start_ms,
            min_utterance_ms=vad_min_utterance_ms,
            pre_roll_ms=vad_pre_roll_ms,
            max_turn_ms=max_turn_seconds * 1000,
            detector=VoiceActivityDetector(vad_start_rms, vad_continue_rms),
            sample_rate=sample_rate,
            channels=channels,
            on_utterance=self._schedule_utterance,
        )
        self.started = False
        # A direct Telethon raw handler distinguishes a missing Telegram update
        # from a downstream PyTgCalls/NTgCalls handshake failure.  Never retain
        # the call payload, keys, fingerprint, or signaling bytes.
        from telethon.events import Raw

        @telethon_client.on(Raw())  # type: ignore[untyped-decorator]
        async def _observe_raw_telegram_update(update: Any) -> None:
            update_name = type(update).__name__
            if update_name in {"UpdatePhoneCall", "UpdatePhoneCallSignalingData"}:
                self.audit.append(
                    Event(
                        "telegram.raw.call_update",
                        self.call_id,
                        self.call_id,
                        details={"update_type": update_name},
                    )
                )

        self.calls.add_handler(self._on_update)

    async def start(self) -> None:
        if self.started:
            return
        await self.calls.start()
        self.started = True
        self.audit.append(
            Event("voip.started", self.call_id, self.call_id, details={"peer_id": self.peer_id})
        )

    async def place_and_play(self, path: Path) -> None:
        await self.start()
        self.audit.append(
            Event("voip.playback.started", self.call_id, self.call_id, details={"file": path.name})
        )
        await self.calls.play(
            self.peer_id,
            await self._playback_stream(path),
            config=CallConfig(timeout=self.call_timeout_seconds),
        )

    async def play(self, path: Path) -> None:
        await self.place_and_play(path)

    async def _playback_stream(self, path: Path) -> MediaStream:
        """Play one file while explicitly requesting remote speaker PCM frames."""
        stream = MediaStream(path)
        await stream.check_stream()
        stream.speaker = AudioStream(
            MediaSource.EXTERNAL,
            "",
            AudioParameters(bitrate=self.sample_rate, channels=self.channels),
        )
        return stream

    async def hangup(self) -> None:
        if self.started:
            await self.calls.leave_call(self.peer_id)
            self.audit.append(Event("voip.hangup", self.call_id, self.call_id))

    async def _on_update(self, _: Any, update: Any) -> None:
        # Key-exchange state is recorded without persisting any cryptographic
        # material.  It is essential when diagnosing a call that rings but does
        # not transition to media.
        if isinstance(update, RawCallUpdate) and update.chat_id == self.peer_id:
            self.audit.append(
                Event(
                    "voip.call.update",
                    self.call_id,
                    self.call_id,
                    details={"status": str(update.status)},
                )
            )
            return
        if isinstance(update, ChatUpdate) and update.chat_id == self.peer_id:
            self.audit.append(
                Event(
                    "voip.chat.update",
                    self.call_id,
                    self.call_id,
                    details={"status": str(update.status)},
                )
            )
            return
        if not isinstance(update, StreamFrames):
            return
        if update.chat_id != self.peer_id:
            return
        if update.direction != Direction.INCOMING or update.device != Device.SPEAKER:
            return
        for frame in update.frames:
            self.assembler.feed(frame.frame)

    def _schedule_utterance(self, path: Path) -> None:
        turn = AudioTurn(
            call_id=self.call_id,
            audio_path=path,
            mime_type="audio/wav",
            language=self.language,
        )
        task: asyncio.Future[None] = asyncio.ensure_future(self.on_utterance(turn))
        task.add_done_callback(self._log_turn_failure)

    def _log_turn_failure(self, task: asyncio.Future[None]) -> None:
        try:
            task.result()
        except Exception:  # pragma: no cover - integration failure path
            logger.exception("voice turn processing failed")
            self.audit.append(Event("voip.turn.failed", self.call_id, self.call_id, status="error"))
