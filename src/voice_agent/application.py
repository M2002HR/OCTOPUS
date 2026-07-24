from __future__ import annotations

from pathlib import Path
from time import monotonic, time
from uuid import uuid4

from voice_agent.domain import AssistantTurn, AudioTurn, ChatMessage
from voice_agent.english import fallback_reply, limit_voice_reply, normalize_english_output
from voice_agent.observability import Event
from voice_agent.ports import ChatBrain, SpeechSynthesizer, Transcriber
from voice_agent.storage import AuditStore


class ConversationOrchestrator:
    def __init__(
        self,
        *,
        transcriber: Transcriber,
        brain: ChatBrain,
        synthesizer: SpeechSynthesizer,
        audit: AuditStore,
        system_prompt: str,
        output_dir: Path,
        output_language: str | None = None,
        max_voice_reply_characters: int = 480,
        max_history_messages: int = 12,
        persist_transcripts: bool = True,
    ) -> None:
        self.transcriber = transcriber
        self.brain = brain
        self.synthesizer = synthesizer
        self.audit = audit
        self.system_prompt = system_prompt
        self.output_dir = output_dir
        self.output_language = output_language
        self.max_voice_reply_characters = max_voice_reply_characters
        self.max_history_messages = max_history_messages
        self.persist_transcripts = persist_transcripts
        self.histories: dict[str, list[ChatMessage]] = {}

    async def process(self, turn: AudioTurn) -> AssistantTurn:
        started = monotonic()
        turn_id = str(uuid4())
        self.audit.append(
            Event(
                "turn.received",
                turn.trace_id,
                turn.call_id,
                turn_id,
                details={"audio": turn.audio_path.name},
            )
        )
        try:
            self.audit.append(Event("stt.started", turn.trace_id, turn.call_id, turn_id))
            transcript = await self.transcriber.transcribe(turn.audio_path, language=turn.language)
            self.audit.append(
                Event(
                    "stt.completed",
                    turn.trace_id,
                    turn.call_id,
                    turn_id,
                    details={
                        "chars": len(transcript),
                        "words": len(transcript.split()),
                        "requested_language": turn.language,
                    },
                )
            )
            history = self.histories.setdefault(turn.call_id, [])
            history.append(ChatMessage("user", transcript))
            history[:] = history[-self.max_history_messages :]
            self.audit.append(
                Event(
                    "ai.chat.started",
                    turn.trace_id,
                    turn.call_id,
                    turn_id,
                    details={"history_messages": len(history)},
                )
            )
            reply = normalize_english_output(
                await self.brain.reply(messages=history, system_prompt=self.system_prompt)
            )
            if reply is None:
                self.audit.append(
                    Event(
                        "ai.chat.rejected_non_english",
                        turn.trace_id,
                        turn.call_id,
                        turn_id,
                    )
                )
                self.audit.append(
                    Event("ai.chat.english_retry", turn.trace_id, turn.call_id, turn_id)
                )
                reply = normalize_english_output(
                    await self.brain.reply(
                        messages=history,
                        system_prompt=(
                            f"{self.system_prompt}\n\n"
                            "Translate or answer the user's request in English only. "
                            "Your entire response must use ASCII English text."
                        ),
                    )
                )
                if reply is None:
                    self.audit.append(
                        Event("ai.chat.english_recovery", turn.trace_id, turn.call_id, turn_id)
                    )
                    # A fresh one-message context prevents a non-English model response from
                    # anchoring later attempts while retaining the configured assistant role.
                    reply = normalize_english_output(
                        await self.brain.reply(
                            messages=[ChatMessage("user", transcript)],
                            system_prompt=(
                                f"{self.system_prompt}\n\n"
                                "Recovery mode: respond to the user's latest request only. "
                                "Use concise ASCII English text only; do not use any other script."
                            ),
                        )
                    )
                    if reply is None:
                        self.audit.append(
                            Event(
                                "ai.chat.english_strict_recovery",
                                turn.trace_id,
                                turn.call_id,
                                turn_id,
                            )
                        )
                        reply = normalize_english_output(
                            await self.brain.reply(
                                messages=[
                                    ChatMessage(
                                        "user",
                                        "Write exactly one short ASCII English sentence that "
                                        "helpfully responds to this user request: " + transcript,
                                    )
                                ],
                                system_prompt=(
                                    "You are an English voice assistant. Output exactly one "
                                    "short, helpful sentence in ASCII English. Do not use any "
                                    "other writing system, markdown, or introductions."
                                ),
                            )
                        )
                        if reply is None:
                            reply = fallback_reply()
            original_reply_characters = len(reply)
            reply = limit_voice_reply(reply, self.max_voice_reply_characters)
            if len(reply) != original_reply_characters:
                self.audit.append(
                    Event(
                        "ai.chat.reply_truncated",
                        turn.trace_id,
                        turn.call_id,
                        turn_id,
                        details={
                            "original_chars": original_reply_characters,
                            "delivered_chars": len(reply),
                        },
                    )
                )
            history.append(ChatMessage("assistant", reply))
            history[:] = history[-self.max_history_messages :]
            self.audit.append(
                Event(
                    "ai.chat.completed",
                    turn.trace_id,
                    turn.call_id,
                    turn_id,
                    details={"chars": len(reply), "output_language": self.output_language},
                )
            )
            output = self.output_dir / turn.call_id / f"{turn_id}.ogg"
            self.audit.append(Event("tts.started", turn.trace_id, turn.call_id, turn_id))
            duration_ms = await self.synthesizer.synthesize(
                reply, output, language=self.output_language
            )
            self.audit.append(
                Event(
                    "tts.completed",
                    turn.trace_id,
                    turn.call_id,
                    turn_id,
                    details={"duration_ms": duration_ms},
                )
            )
            if self.persist_transcripts:
                self.audit.record_conversation_turn(
                    occurred_at=time(),
                    trace_id=turn.trace_id,
                    call_id=turn.call_id,
                    turn_id=turn_id,
                    input_audio_path=turn.audio_path,
                    input_language=turn.language,
                    transcript=transcript,
                    reply=reply,
                    output_audio_path=output,
                    output_duration_ms=duration_ms,
                )
                self.audit.append(
                    Event("conversation.persisted", turn.trace_id, turn.call_id, turn_id)
                )
            self.audit.append(
                Event(
                    "turn.completed",
                    turn.trace_id,
                    turn.call_id,
                    turn_id,
                    details={"elapsed_ms": round((monotonic() - started) * 1000)},
                )
            )
            return AssistantTurn(
                turn.call_id, turn.trace_id, transcript, reply, output, duration_ms
            )
        except Exception as exc:
            self.audit.append(
                Event(
                    "turn.failed",
                    turn.trace_id,
                    turn.call_id,
                    turn_id,
                    "error",
                    {"error_type": type(exc).__name__},
                )
            )
            raise
