from pathlib import Path

import pytest

from voice_agent.application import ConversationOrchestrator
from voice_agent.domain import AudioTurn, ChatMessage
from voice_agent.storage import AuditStore


class FakeTranscriber:
    async def transcribe(self, audio_path: Path, *, language: str | None) -> str:
        assert audio_path.name == "input.ogg"
        return "سلام"


class FakeBrain:
    async def reply(self, *, messages: list[ChatMessage], system_prompt: str) -> str:
        assert messages[-1].content == "سلام"
        return "سلام، در خدمتم."


class FakeSynthesizer:
    async def synthesize(self, text: str, destination: Path) -> int:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"ogg")
        return 1200


@pytest.mark.asyncio
async def test_orchestrator_records_each_stage(tmp_path: Path) -> None:
    store = AuditStore(tmp_path / "events.db", tmp_path / "events.jsonl")
    orchestrator = ConversationOrchestrator(
        transcriber=FakeTranscriber(),
        brain=FakeBrain(),
        synthesizer=FakeSynthesizer(),
        audit=store,
        system_prompt="test",
        output_dir=tmp_path / "output",
    )
    result = await orchestrator.process(AudioTurn("call-1", tmp_path / "input.ogg", "audio/ogg"))
    assert result.transcript == "سلام"
    assert result.audio_path.exists()
    assert store.events_for_trace(result.trace_id) == [
        ("turn.received", "ok"),
        ("stt.started", "ok"),
        ("stt.completed", "ok"),
        ("ai.chat.started", "ok"),
        ("ai.chat.completed", "ok"),
        ("tts.started", "ok"),
        ("tts.completed", "ok"),
        ("conversation.persisted", "ok"),
        ("turn.completed", "ok"),
    ]
    assert store.conversation_for_call("call-1") == [("سلام", "سلام، در خدمتم.")]
    store.close()


@pytest.mark.asyncio
async def test_orchestrator_can_disable_transcript_retention(tmp_path: Path) -> None:
    store = AuditStore(tmp_path / "events.db", tmp_path / "events.jsonl")
    orchestrator = ConversationOrchestrator(
        transcriber=FakeTranscriber(),
        brain=FakeBrain(),
        synthesizer=FakeSynthesizer(),
        audit=store,
        system_prompt="test",
        output_dir=tmp_path / "output",
        persist_transcripts=False,
    )
    result = await orchestrator.process(
        AudioTurn("call-1", tmp_path / "input.ogg", "audio/ogg")
    )
    event_names = [name for name, _ in store.events_for_trace(result.trace_id)]
    assert "conversation.persisted" not in event_names
    assert store.conversation_for_call("call-1") == []
    store.close()
