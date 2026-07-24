from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from telegram_codex_agent.completion_calls import CompletionCallRequest
from voice_agent.completion_calls import CompletionCallConsumer
from voice_agent.storage import AuditStore


class FakeRedis:
    def __init__(self) -> None:
        self.acknowledged: list[object] = []
        self.values: dict[str, str] = {}

    async def exists(self, key: str) -> bool:
        return key in self.values

    async def set(self, key: str, value: str, **_: object) -> None:
        self.values[key] = value

    async def xack(self, _stream: str, _group: str, message_id: object) -> None:
        self.acknowledged.append(message_id)


def request() -> CompletionCallRequest:
    return CompletionCallRequest(
        job_id="job_consumer",
        target_user_id=123,
        terminal_state="completed",
        category="success",
        message="The task completed successfully.",
        repeat_count=3,
        created_at="2026-07-24T00:00:00+00:00",
    )


async def test_consumer_retries_then_acknowledges_delivery(tmp_path: Path) -> None:
    redis = FakeRedis()
    audit = AuditStore(tmp_path / "audit.db", tmp_path / "events.jsonl")
    attempts = 0

    async def handler(_: CompletionCallRequest) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("temporary call failure")

    consumer = CompletionCallConsumer(
        redis_url="redis://unused",
        stream="completion-calls",
        consumer_group="voice",
        retry_attempts=3,
        retry_delay_seconds=0,
        audit=audit,
        handler=handler,
        redis=redis,  # type: ignore[arg-type]
    )

    await consumer._handle("1-0", request().redis_fields())

    assert attempts == 2
    assert redis.acknowledged == ["1-0"]
    assert audit.events_for_trace("job_consumer") == [
        ("completion_call.attempt", "ok"),
        ("completion_call.attempt.failed", "error"),
        ("completion_call.attempt", "ok"),
        ("completion_call.delivered", "ok"),
    ]
    assert "The task completed successfully." not in (
        tmp_path / "events.jsonl"
    ).read_text(encoding="utf-8")
    audit.close()


async def test_consumer_discards_invalid_payload_without_calling_handler(
    tmp_path: Path,
) -> None:
    redis = FakeRedis()
    audit = AuditStore(tmp_path / "audit.db", tmp_path / "events.jsonl")
    called = False

    async def handler(_: CompletionCallRequest) -> None:
        nonlocal called
        called = True

    consumer = CompletionCallConsumer(
        redis_url="redis://unused",
        stream="completion-calls",
        consumer_group="voice",
        retry_attempts=1,
        retry_delay_seconds=0,
        audit=audit,
        handler=handler,
        redis=redis,  # type: ignore[arg-type]
    )

    await consumer._handle("2-0", {"payload": "{}"})

    assert called is False
    assert redis.acknowledged == ["2-0"]
    audit.close()


async def test_consumer_recovers_delivery_that_was_too_fresh_on_startup(
    tmp_path: Path,
) -> None:
    class RecoveryRedis(FakeRedis):
        def __init__(self) -> None:
            super().__init__()
            self.recovery_checks = 0
            self.reads = 0

        async def xautoclaim(self, *_: object, **__: object) -> tuple[object, ...]:
            self.recovery_checks += 1
            if self.recovery_checks == 2:
                return ("0-0", [("3-0", request().redis_fields())], [])
            return ("0-0", [], [])

        async def xreadgroup(self, *_: object, **__: object) -> list[object]:
            self.reads += 1
            if self.reads == 1:
                return []
            raise asyncio.CancelledError

    redis = RecoveryRedis()
    audit = AuditStore(tmp_path / "audit.db", tmp_path / "events.jsonl")
    calls = 0

    async def handler(_: CompletionCallRequest) -> None:
        nonlocal calls
        calls += 1

    consumer = CompletionCallConsumer(
        redis_url="redis://unused",
        stream="completion-calls",
        consumer_group="voice",
        retry_attempts=1,
        retry_delay_seconds=0,
        audit=audit,
        handler=handler,
        redis=redis,  # type: ignore[arg-type]
    )

    with pytest.raises(asyncio.CancelledError):
        await consumer._run()

    assert redis.recovery_checks == 2
    assert calls == 1
    assert redis.acknowledged == ["3-0"]
    audit.close()
