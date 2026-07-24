from pathlib import Path

from voice_agent.storage import AuditStore


def test_conversation_turns_are_queryable_by_call(tmp_path: Path) -> None:
    store = AuditStore(tmp_path / "audit.db", tmp_path / "events.jsonl")
    store.record_conversation_turn(
        occurred_at=1.0,
        trace_id="trace-1",
        call_id="call-1",
        turn_id="turn-1",
        input_audio_path=Path("input.wav"),
        input_language="en",
        transcript="Hello",
        reply="Hello, dear.",
        output_audio_path=Path("output.ogg"),
        output_duration_ms=900,
    )
    assert store.conversation_for_call("call-1") == [("Hello", "Hello, dear.")]
    store.close()
