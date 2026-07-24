from pathlib import Path

import pytest

from voice_agent.application import ConversationOrchestrator
from voice_agent.domain import AudioTurn, ChatMessage
from voice_agent.storage import AuditStore


class FakeTranscriber:
    async def transcribe(self, audio_path: Path, *, language: str | None) -> str:
        assert audio_path.name == "input.ogg"
        return "Hello"


class FakeBrain:
    async def reply(self, *, messages: list[ChatMessage], system_prompt: str) -> str:
        assert messages[-1].content == "Hello"
        return "Hello, dear."


class NonEnglishThenEnglishBrain:
    def __init__(self) -> None:
        self.calls = 0

    async def reply(self, *, messages: list[ChatMessage], system_prompt: str) -> str:
        self.calls += 1
        if self.calls == 1:
            return "\u0633\u0644\u0627\u0645"
        assert "ASCII English" in system_prompt
        return "Hello, dear."


class NonEnglishTwiceThenEnglishBrain:
    def __init__(self) -> None:
        self.calls = 0

    async def reply(self, *, messages: list[ChatMessage], system_prompt: str) -> str:
        self.calls += 1
        if self.calls < 3:
            return "\u0633\u0644\u0627\u0645"
        assert len(messages) == 1
        assert "Recovery mode" in system_prompt
        return "Please implement the reset flow and add tests."


class NonEnglishThreeTimesThenEnglishBrain:
    def __init__(self) -> None:
        self.calls = 0

    async def reply(self, *, messages: list[ChatMessage], system_prompt: str) -> str:
        self.calls += 1
        if self.calls < 4:
            return "\u0633\u0644\u0627\u0645"
        assert "Output exactly one short, helpful sentence in ASCII English" in system_prompt
        return "Please fix the mobile layout today."


class FakeSynthesizer:
    async def synthesize(self, text: str, destination: Path, *, language: str | None = None) -> int:
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
    assert result.transcript == "Hello"
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
    assert store.conversation_for_call("call-1") == [("Hello", "Hello, dear.")]
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


@pytest.mark.asyncio
async def test_orchestrator_retries_a_non_english_model_reply(tmp_path: Path) -> None:
    store = AuditStore(tmp_path / "events.db", tmp_path / "events.jsonl")
    brain = NonEnglishThenEnglishBrain()
    orchestrator = ConversationOrchestrator(
        transcriber=FakeTranscriber(),
        brain=brain,
        synthesizer=FakeSynthesizer(),
        audit=store,
        system_prompt="Always reply in English.",
        output_dir=tmp_path / "output",
    )

    result = await orchestrator.process(AudioTurn("call-1", tmp_path / "input.ogg", "audio/ogg"))

    assert result.reply == "Hello, dear."
    assert brain.calls == 2
    assert "ai.chat.english_retry" in [name for name, _ in store.events_for_trace(result.trace_id)]
    store.close()


@pytest.mark.asyncio
async def test_orchestrator_recovers_with_a_fresh_context_after_two_non_english_replies(
    tmp_path: Path,
) -> None:
    store = AuditStore(tmp_path / "events.db", tmp_path / "events.jsonl")
    brain = NonEnglishTwiceThenEnglishBrain()
    orchestrator = ConversationOrchestrator(
        transcriber=FakeTranscriber(),
        brain=brain,
        synthesizer=FakeSynthesizer(),
        audit=store,
        system_prompt="You are a project manager. Always reply in English.",
        output_dir=tmp_path / "output",
    )

    result = await orchestrator.process(AudioTurn("call-1", tmp_path / "input.ogg", "audio/ogg"))

    assert result.reply == "Please implement the reset flow and add tests."
    assert brain.calls == 3
    assert "ai.chat.english_recovery" in [
        name for name, _ in store.events_for_trace(result.trace_id)
    ]
    store.close()


@pytest.mark.asyncio
async def test_orchestrator_uses_strict_english_recovery_after_three_rejections(
    tmp_path: Path,
) -> None:
    store = AuditStore(tmp_path / "events.db", tmp_path / "events.jsonl")
    brain = NonEnglishThreeTimesThenEnglishBrain()
    orchestrator = ConversationOrchestrator(
        transcriber=FakeTranscriber(),
        brain=brain,
        synthesizer=FakeSynthesizer(),
        audit=store,
        system_prompt="You are a project manager. Always reply in English.",
        output_dir=tmp_path / "output",
    )

    result = await orchestrator.process(AudioTurn("call-1", tmp_path / "input.ogg", "audio/ogg"))

    assert result.reply == "Please fix the mobile layout today."
    assert brain.calls == 4
    assert "ai.chat.english_strict_recovery" in [
        name for name, _ in store.events_for_trace(result.trace_id)
    ]
    store.close()
