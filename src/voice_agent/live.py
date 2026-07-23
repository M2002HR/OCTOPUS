from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path

from voice_agent.adapters.edge_tts import EdgeSpeechSynthesizer
from voice_agent.adapters.telegram import TelethonSession
from voice_agent.adapters.uag import UAGClient
from voice_agent.application import ConversationOrchestrator
from voice_agent.config import Settings
from voice_agent.domain import AudioTurn, Call, CallState
from voice_agent.messaging import MessageAssistant
from voice_agent.observability import Event
from voice_agent.storage import AuditStore
from voice_agent.voip import IncomingCallServer, TelethonVoipEngine

logger = logging.getLogger(__name__)


class LiveVoiceAssistant:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.audit = AuditStore(settings.audit_database_path, settings.audit_jsonl_path)
        self.telegram = TelethonSession(settings)
        self.uag = UAGClient(
            base_url=settings.uag_base_url,
            chat_endpoint=settings.uag_chat_endpoint,
            transcriptions_endpoint=settings.uag_transcriptions_endpoint,
            timeout_seconds=settings.uag_timeout_seconds,
            auth_token=settings.uag_auth_token,
            auth_header_name=settings.uag_auth_header_name,
            models=settings.chat_models,
            providers=settings.chat_providers,
            transcription_provider=settings.transcription_provider,
            transcription_models=settings.transcription_models,
        )
        self.orchestrator = ConversationOrchestrator(
            transcriber=self.uag,
            brain=self.uag,
            synthesizer=EdgeSpeechSynthesizer(
                voice=settings.edge_voice,
                rate=settings.edge_rate,
                ffmpeg_bin=settings.ffmpeg_bin,
            ),
            audit=self.audit,
            system_prompt=settings.system_prompt,
            output_dir=settings.runtime_dir / "tts",
            max_history_messages=settings.max_history_messages,
            persist_transcripts=settings.recording_mode == "transcript_only",
        )
        self.engine: TelethonVoipEngine | None = None
        self.inbound_server: IncomingCallServer | None = None
        self.message_assistant: MessageAssistant | None = None
        self.call: Call | None = None
        self.inbound_peer_id: int | None = None
        self.inbound_peer_username: str | None = None
        self._inbound_intro_path: Path | None = None
        self._turn_lock = asyncio.Lock()

    async def place_test_call(self, username: str) -> Call:
        """Place one explicitly requested, allowlisted call and start the disclosed assistant."""
        await self.telegram.connect()
        peer = await self.telegram.resolve_allowed_user(username)
        call = Call(peer_id=peer.user_id, peer_username=peer.username)
        call.transition(CallState.RINGING)
        self.call = call
        self.audit.append(
            Event(
                "call.requested",
                call.id,
                call.id,
                details={"peer_id": peer.user_id, "username": peer.username},
            )
        )

        async def on_utterance(turn: AudioTurn) -> None:
            # Serialisation prevents two overlapping replies from replacing the
            # single Telegram call's outbound media stream.
            async with self._turn_lock:
                result = await self.orchestrator.process(turn)
                if self.engine is not None:
                    await self.engine.play(result.audio_path)

        self.engine = TelethonVoipEngine(
            telethon_client=self.telegram.client,
            audit=self.audit,
            call_id=call.id,
            peer_id=peer.user_id,
            vad_start_rms=self.settings.vad_start_rms,
            vad_continue_rms=self.settings.vad_continue_rms,
            vad_start_ms=self.settings.vad_start_ms,
            vad_end_silence_ms=self.settings.vad_end_silence_ms,
            vad_min_utterance_ms=self.settings.vad_min_utterance_ms,
            vad_pre_roll_ms=self.settings.vad_pre_roll_ms,
            max_turn_seconds=self.settings.max_turn_seconds,
            call_timeout_seconds=self.settings.call_timeout_seconds,
            sample_rate=self.settings.audio_sample_rate,
            channels=self.settings.audio_channels,
            language=self.settings.language,
            runtime_dir=self.settings.runtime_dir,
            on_utterance=on_utterance,
        )
        intro = (
            "سلام. من یک دستیار صوتی خودکار هستم. "
            "برای پاسخ‌گویی، صدای شما به متن تبدیل و پردازش می‌شود. بفرمایید."
            if self.settings.require_disclosure
            else "سلام، بفرمایید."
        )
        intro_path = self.settings.runtime_dir / "intro" / f"{call.id}.ogg"
        await self.orchestrator.synthesizer.synthesize(intro, intro_path)
        call.transition(CallState.CONNECTING)
        self.audit.append(Event("call.connecting", call.id, call.id))
        try:
            await self.engine.place_and_play(intro_path)
        except Exception as exc:
            call.transition(CallState.FAILED)
            self.audit.append(
                Event(
                    "call.failed",
                    call.id,
                    call.id,
                    status="error",
                    details={"error_type": type(exc).__name__},
                )
            )
            raise
        call.transition(CallState.ACTIVE)
        self.audit.append(Event("call.active", call.id, call.id))
        return call

    async def serve_incoming(self) -> None:
        """Keep one Telegram session online and accept only the configured caller."""
        self.settings.validate_inbound_service()
        await self.telegram.connect()
        peer = await self.telegram.resolve_allowed_user(self.settings.inbound_username)
        self.inbound_peer_id = peer.user_id
        self.inbound_peer_username = peer.username
        self._inbound_intro_path = self.settings.runtime_dir / "intro" / "inbound-ready.ogg"
        await self.orchestrator.synthesizer.synthesize(
            self._introduction(), self._inbound_intro_path
        )
        self.inbound_server = IncomingCallServer(
            telethon_client=self.telegram.client,
            audit=self.audit,
            allowed_peer_id=peer.user_id,
            on_authorized_call=self._accept_incoming_call,
            on_call_ended=self._finish_incoming_call,
        )
        await self.inbound_server.start()
        if self.settings.message_enabled:
            message_peer = await self.telegram.resolve_allowed_user(self.settings.message_username)
            self.message_assistant = MessageAssistant(
                settings=self.settings,
                client=self.telegram.client,
                uag=self.uag,
                synthesizer=self.orchestrator.synthesizer,
                audit=self.audit,
                allowed_peer_id=message_peer.user_id,
            )
            await self.message_assistant.start()
        logger.info("inbound voice service is ready for the configured caller")

    async def _accept_incoming_call(self, peer_id: int, _: object) -> None:
        if self.inbound_server is None or self._inbound_intro_path is None:
            raise RuntimeError("inbound server is not initialized")
        if peer_id != self.inbound_peer_id:
            raise RuntimeError("incoming peer did not match the configured caller")
        call = Call(peer_id=peer_id, peer_username=self.inbound_peer_username)
        call.transition(CallState.RINGING)
        call.transition(CallState.CONNECTING)
        self.call = call
        self.audit.append(
            Event(
                "call.incoming.accepting",
                call.id,
                call.id,
                details={"peer_id": peer_id, "username": self.inbound_peer_username},
            )
        )

        async def on_utterance(turn: AudioTurn) -> None:
            async with self._turn_lock:
                result = await self.orchestrator.process(turn)
                if self.engine is not None:
                    await self.engine.play(result.audio_path)

        self.engine = TelethonVoipEngine(
            telethon_client=self.telegram.client,
            calls=self.inbound_server.calls,
            audit=self.audit,
            call_id=call.id,
            peer_id=peer_id,
            vad_start_rms=self.settings.vad_start_rms,
            vad_continue_rms=self.settings.vad_continue_rms,
            vad_start_ms=self.settings.vad_start_ms,
            vad_end_silence_ms=self.settings.vad_end_silence_ms,
            vad_min_utterance_ms=self.settings.vad_min_utterance_ms,
            vad_pre_roll_ms=self.settings.vad_pre_roll_ms,
            max_turn_seconds=self.settings.max_turn_seconds,
            call_timeout_seconds=self.settings.call_timeout_seconds,
            sample_rate=self.settings.audio_sample_rate,
            channels=self.settings.audio_channels,
            language=self.settings.language,
            runtime_dir=self.settings.runtime_dir,
            on_utterance=on_utterance,
        )
        try:
            await self.engine.place_and_play(self._inbound_intro_path)
        except Exception as exc:
            call.transition(CallState.FAILED)
            self.audit.append(
                Event(
                    "call.incoming.failed",
                    call.id,
                    call.id,
                    status="error",
                    details={"error_type": type(exc).__name__},
                )
            )
            self.engine.detach()
            self._cleanup_call_media(call.id)
            self.engine = None
            self.call = None
            raise
        call.transition(CallState.ACTIVE)
        self.audit.append(Event("call.active", call.id, call.id))

    async def _finish_incoming_call(self, peer_id: int) -> None:
        if self.call is None or self.call.peer_id != peer_id:
            return
        if self.call.state in {CallState.RINGING, CallState.CONNECTING, CallState.ACTIVE}:
            self.call.transition(CallState.ENDED)
        self.audit.append(Event("call.ended", self.call.id, self.call.id))
        self._cleanup_call_media(self.call.id)
        if self.engine is not None:
            self.engine.detach()
        self.engine = None
        self.call = None

    def _introduction(self) -> str:
        return (
            "سلام. من یک دستیار صوتی خودکار هستم. "
            "برای پاسخ‌گویی، صدای شما به متن تبدیل و پردازش می‌شود. بفرمایید."
            if self.settings.require_disclosure
            else "سلام، بفرمایید."
        )

    def _cleanup_call_media(self, call_id: str) -> None:
        for folder in ("incoming", "tts"):
            shutil.rmtree(self.settings.runtime_dir / folder / call_id, ignore_errors=True)

    async def close(self) -> None:
        if self.call is not None and self.call.state in {
            CallState.RINGING,
            CallState.CONNECTING,
            CallState.ACTIVE,
        }:
            self.call.transition(CallState.ENDED)
        try:
            if self.message_assistant is not None:
                await self.message_assistant.stop()
            if self.inbound_server is not None:
                await self.inbound_server.stop()
            if self.engine is not None:
                await self.engine.hangup()
        finally:
            if self.call is not None:
                # Audio is needed only while a live call is in progress.  Transcript
                # retention, when enabled, records historical file references but
                # deliberately does not retain the media itself.
                for folder in ("incoming", "tts", "intro"):
                    shutil.rmtree(
                        self.settings.runtime_dir / folder / self.call.id, ignore_errors=True
                    )
            if self._inbound_intro_path is not None:
                self._inbound_intro_path.unlink(missing_ok=True)
            await self.uag.aclose()
            await self.telegram.close()
            self.audit.close()


async def wait_for_termination() -> None:
    stop = asyncio.Event()
    try:
        loop = asyncio.get_running_loop()
        for signal_name in ("SIGINT", "SIGTERM"):
            import signal

            loop.add_signal_handler(getattr(signal, signal_name), stop.set)
    except (NotImplementedError, AttributeError):  # pragma: no cover - platform specific
        pass
    await stop.wait()
