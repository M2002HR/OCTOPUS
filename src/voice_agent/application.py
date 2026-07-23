from __future__ import annotations

from pathlib import Path
from time import monotonic, time
from uuid import uuid4

from voice_agent.domain import AssistantTurn, AudioTurn, ChatMessage
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
        max_history_messages: int = 12,
        persist_transcripts: bool = True,
    ) -> None:
        self.transcriber = transcriber
        self.brain = brain
        self.synthesizer = synthesizer
        self.audit = audit
        self.system_prompt = system_prompt
        self.output_dir = output_dir
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
                    details={"chars": len(transcript)},
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
            reply = await self.brain.reply(messages=history, system_prompt=self.system_prompt)
            history.append(ChatMessage("assistant", reply))
            history[:] = history[-self.max_history_messages :]
            self.audit.append(
                Event(
                    "ai.chat.completed",
                    turn.trace_id,
                    turn.call_id,
                    turn_id,
                    details={"chars": len(reply)},
                )
            )
            output = self.output_dir / turn.call_id / f"{turn_id}.ogg"
            self.audit.append(Event("tts.started", turn.trace_id, turn.call_id, turn_id))
            duration_ms = await self.synthesizer.synthesize(reply, output)
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
