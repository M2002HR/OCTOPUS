from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path

from telegram_codex_agent.completion_calls import (
    CompletionCallRequest,
    repeated_notification_text,
)
from voice_agent.adapters.edge_tts import EdgeSpeechSynthesizer
from voice_agent.adapters.telegram import TelethonSession
from voice_agent.adapters.uag import UAGClient
from voice_agent.application import ConversationOrchestrator
from voice_agent.completion_calls import CompletionCallConsumer
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
            vision_models=settings.vision_models,
            vision_providers=settings.vision_providers,
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
            output_language=settings.language,
            max_voice_reply_characters=settings.max_voice_reply_characters,
            max_history_messages=settings.max_history_messages,
            persist_transcripts=settings.recording_mode == "transcript_only",
        )
        self.engine: TelethonVoipEngine | None = None
        self.notification_engine: TelethonVoipEngine | None = None
        self.completion_call_consumer: CompletionCallConsumer | None = None
        self.inbound_server: IncomingCallServer | None = None
        self.message_assistant: MessageAssistant | None = None
        self.call: Call | None = None
        self.inbound_peers: dict[int, str | None] = {}
        self._inbound_intro_path: Path | None = None
        self._inbound_intro_duration_ms = 0
        self._turn_lock = asyncio.Lock()
        self._notification_lock = asyncio.Lock()

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
                    await self.engine.play(result.audio_path, duration_ms=result.duration_ms)

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
            "This is an automated voice service. Your speech will be transcribed and processed. "
            "Hello, dear."
            if self.settings.require_disclosure
            else "Hello, dear."
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
        peers = await asyncio.gather(
            *(
                self.telegram.resolve_allowed_user(username)
                for username in self.settings.inbound_usernames
            )
        )
        self.inbound_peers = {peer.user_id: peer.username for peer in peers}
        if len(self.inbound_peers) != len(peers):
            raise RuntimeError("configured inbound usernames resolved to the same Telegram user")
        self._inbound_intro_path = self.settings.runtime_dir / "intro" / "inbound-ready.ogg"
        self._inbound_intro_path.unlink(missing_ok=True)
        self._inbound_intro_duration_ms = await self.orchestrator.synthesizer.synthesize(
            self._introduction(), self._inbound_intro_path
        )
        self.inbound_server = IncomingCallServer(
            telethon_client=self.telegram.client,
            audit=self.audit,
            allowed_peer_ids=frozenset(self.inbound_peers),
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
        if self.settings.completion_calls_enabled:
            self.completion_call_consumer = CompletionCallConsumer(
                redis_url=self.settings.completion_call_redis_url,
                stream=self.settings.completion_call_stream,
                consumer_group=self.settings.completion_call_consumer_group,
                retry_attempts=self.settings.completion_call_retry_attempts,
                retry_delay_seconds=self.settings.completion_call_retry_delay_seconds,
                audit=self.audit,
                handler=self._place_completion_call,
            )
            await self.completion_call_consumer.start()
        logger.info("inbound voice service is ready for the configured caller")

    async def _place_completion_call(self, request: CompletionCallRequest) -> None:
        """Call one allowlisted Bot user, repeat Ajil's message, then hang up."""

        if self.inbound_server is None:
            raise RuntimeError("voice service is not ready")
        peer = await self.telegram.get_allowed_user(request.target_user_id)
        output_dir = self.settings.runtime_dir / "completion-calls" / request.job_id
        audio_path = output_dir / "notification.ogg"
        repeated_text = repeated_notification_text(
            request.message,
            request.repeat_count,
        )
        try:
            duration_ms = await self.orchestrator.synthesizer.synthesize(
                repeated_text,
                audio_path,
                language="en",
            )
        except BaseException:
            shutil.rmtree(output_dir, ignore_errors=True)
            raise

        async with self._notification_lock:
            if self.call is not None or self.inbound_server.busy:
                shutil.rmtree(output_dir, ignore_errors=True)
                raise RuntimeError("voice service is busy with another call")
            self.inbound_server.busy = True
            notification_call = Call(
                peer_id=peer.user_id,
                peer_username=peer.username,
            )
            notification_call.transition(CallState.RINGING)

            async def ignore_utterance(turn: AudioTurn) -> None:
                turn.audio_path.unlink(missing_ok=True)

            engine = TelethonVoipEngine(
                telethon_client=self.telegram.client,
                calls=self.inbound_server.calls,
                audit=self.audit,
                call_id=notification_call.id,
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
                language="en",
                runtime_dir=self.settings.runtime_dir,
                on_utterance=ignore_utterance,
            )
            self.notification_engine = engine
            self.audit.append(
                Event(
                    "completion_call.requested",
                    request.job_id,
                    notification_call.id,
                    details={
                        "category": request.category,
                        "repeat_count": request.repeat_count,
                        "target_user_id": peer.user_id,
                    },
                )
            )
            try:
                notification_call.transition(CallState.CONNECTING)
                await engine.place_and_play(audio_path, duration_ms=duration_ms)
                notification_call.transition(CallState.ACTIVE)
                self.audit.append(
                    Event(
                        "completion_call.active",
                        request.job_id,
                        notification_call.id,
                        details={
                            "duration_ms": duration_ms,
                            "target_user_id": peer.user_id,
                        },
                    )
                )
                playback_seconds = max(1.0, duration_ms / 1000)
                await asyncio.sleep(
                    playback_seconds
                    + self.settings.completion_call_post_playback_seconds
                )
                notification_call.transition(CallState.ENDED)
            except Exception:
                if notification_call.state in {
                    CallState.RINGING,
                    CallState.CONNECTING,
                    CallState.ACTIVE,
                }:
                    notification_call.transition(CallState.FAILED)
                raise
            finally:
                try:
                    await engine.hangup()
                finally:
                    self.notification_engine = None
                    self.inbound_server.busy = False
                    shutil.rmtree(output_dir, ignore_errors=True)

    async def _accept_incoming_call(self, peer_id: int, _: object) -> None:
        if self.inbound_server is None or self._inbound_intro_path is None:
            raise RuntimeError("inbound server is not initialized")
        if peer_id not in self.inbound_peers:
            raise RuntimeError("incoming peer did not match the configured caller")
        call = Call(peer_id=peer_id, peer_username=self.inbound_peers[peer_id])
        call.transition(CallState.RINGING)
        call.transition(CallState.CONNECTING)
        self.call = call
        self.audit.append(
            Event(
                "call.incoming.accepting",
                call.id,
                call.id,
                details={"peer_id": peer_id, "username": self.inbound_peers[peer_id]},
            )
        )

        async def on_utterance(turn: AudioTurn) -> None:
            async with self._turn_lock:
                result = await self.orchestrator.process(turn)
                if self.engine is not None:
                    await self.engine.play(result.audio_path, duration_ms=result.duration_ms)

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
            await self.engine.place_and_play(
                self._inbound_intro_path, duration_ms=self._inbound_intro_duration_ms
            )
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
            "This is an automated voice service. Your speech will be transcribed and processed. "
            "Hello, dear."
            if self.settings.require_disclosure
            else "Hello, dear."
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
            if self.completion_call_consumer is not None:
                await self.completion_call_consumer.stop()
            if self.message_assistant is not None:
                await self.message_assistant.stop()
            if self.inbound_server is not None:
                await self.inbound_server.stop()
            if self.notification_engine is not None:
                await self.notification_engine.hangup()
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
