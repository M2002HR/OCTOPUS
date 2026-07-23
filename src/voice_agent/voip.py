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
        calls: Any | None = None,
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
        self.calls = calls if calls is not None else PyTgCalls(telethon_client)
        self._owns_calls = calls is None
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
        self.started = not self._owns_calls
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


class IncomingCallServer:
    """Own one already-authorized PyTgCalls client and selectively accept inbound calls."""

    def __init__(
        self,
        *,
        telethon_client: Any,
        audit: AuditStore,
        allowed_peer_id: int,
        on_authorized_call: Callable[[int, Any], Awaitable[None]],
        on_call_ended: Callable[[int], Awaitable[None]],
        calls: Any | None = None,
    ) -> None:
        self.calls = calls if calls is not None else PyTgCalls(telethon_client)
        self.audit = audit
        self.allowed_peer_id = allowed_peer_id
        self.on_authorized_call = on_authorized_call
        self.on_call_ended = on_call_ended
        self.started = False
        self.busy = False
        self._tasks: set[asyncio.Future[None]] = set()
        self.calls.add_handler(self._on_update)

    async def start(self) -> None:
        if self.started:
            return
        await self.calls.start()
        self.started = True
        self.audit.append(
            Event(
                "inbound.service.ready",
                "inbound-listener",
                details={"allowed_peer_id": self.allowed_peer_id},
            )
        )

    async def stop(self) -> None:
        self.calls.remove_handler(self._on_update)
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        self.started = False

    async def _on_update(self, _: Any, update: Any) -> None:
        if not isinstance(update, ChatUpdate):
            return
        if update.status & ChatUpdate.Status.INCOMING_CALL:
            if update.chat_id != self.allowed_peer_id:
                self.audit.append(
                    Event(
                        "call.incoming.rejected",
                        "inbound-listener",
                        details={"peer_id": update.chat_id, "reason": "unauthorized"},
                    )
                )
                self._track(self._discard(update.chat_id))
                return
            if self.busy:
                self.audit.append(
                    Event(
                        "call.incoming.rejected",
                        "inbound-listener",
                        details={"peer_id": update.chat_id, "reason": "busy"},
                    )
                )
                self._track(self._discard(update.chat_id))
                return
            self.busy = True
            self.audit.append(
                Event(
                    "call.incoming.authorized",
                    "inbound-listener",
                    details={"peer_id": update.chat_id},
                )
            )
            self._track(self._accept(update.chat_id, update))
            return
        is_allowed_discard = (
            update.chat_id == self.allowed_peer_id
            and update.status & ChatUpdate.Status.DISCARDED_CALL
        )
        if is_allowed_discard:
            was_busy = self.busy
            self.busy = False
            if was_busy:
                self._track(self.on_call_ended(update.chat_id))

    async def _accept(self, peer_id: int, update: Any) -> None:
        try:
            await self.on_authorized_call(peer_id, update)
        except Exception as exc:  # pragma: no cover - network failure path
            logger.exception("failed to accept authorized incoming Telegram call")
            self.busy = False
            self.audit.append(
                Event(
                    "call.incoming.failed",
                    "inbound-listener",
                    status="error",
                    details={"peer_id": peer_id, "error_type": type(exc).__name__},
                )
            )
            await self._discard(peer_id)

    async def _discard(self, peer_id: int) -> None:
        try:
            # PyTgCalls exposes this through its MTProto adapter but does not
            # currently publish a high-level decline method for private calls.
            await self.calls._app.discard_call(peer_id, True)
        except Exception as exc:  # pragma: no cover - Telegram failure path
            logger.exception("failed to reject incoming Telegram call")
            self.audit.append(
                Event(
                    "call.incoming.reject_failed",
                    "inbound-listener",
                    status="error",
                    details={"peer_id": peer_id, "error_type": type(exc).__name__},
                )
            )
        finally:
            self.calls._p2p_configs.pop(peer_id, None)

    def _track(self, coroutine: Awaitable[None]) -> None:
        task = asyncio.ensure_future(coroutine)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
