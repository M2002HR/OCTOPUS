from __future__ import annotations

from typing import Any

import pytest

from telegram_codex_agent.completion_calls import (
    CompletionCallRequest,
    TerminalJobContext,
    build_completion_request,
    generate_terminal_message,
    publish_completion_call,
    repeated_notification_text,
)
from telegram_codex_agent.core.config import CompletionCallConfig


class FakeAjilClient:
    def __init__(self, content: str = "", *, raises: bool = False) -> None:
        self.content = content
        self.raises = raises
        self.messages: list[dict[str, Any]] = []

    async def chat(self, messages: list[dict[str, Any]], **_: Any) -> Any:
        self.messages = messages
        if self.raises:
            raise RuntimeError("Ajil unavailable")
        return type(
            "Response",
            (),
            {
                "data": {
                    "choices": [{"message": {"content": self.content}}],
                }
            },
        )()

    @staticmethod
    def _content(data: dict[str, Any]) -> str:
        return str(data["choices"][0]["message"]["content"])


class FakeRedis:
    def __init__(self, result: object = "1-0") -> None:
        self.result = result
        self.arguments: tuple[object, ...] = ()

    async def eval(self, *arguments: object) -> object:
        self.arguments = arguments
        return self.result


@pytest.mark.parametrize(
    ("state", "diagnostic", "category"),
    [
        ("completed", "", "success"),
        ("cancelled", "", "cancelled"),
        ("interrupted", "", "interrupted"),
        ("failed", "HTTP 429 rate limit reached", "rate_limit"),
        ("failed", "step timed out", "timeout"),
        ("failed", "401 unauthorized", "authentication"),
        ("failed", "subprocess failed", "failure"),
    ],
)
def test_terminal_category_covers_all_end_reasons(
    state: str,
    diagnostic: str,
    category: str,
) -> None:
    context = TerminalJobContext(
        job_id="job_123",
        state=state,  # type: ignore[arg-type]
        error_message=diagnostic,
    )

    assert context.category == category


def test_notification_text_repeats_the_exact_message_three_times() -> None:
    message = "The Codex task finished successfully."

    repeated = repeated_notification_text(message, 3)

    assert repeated.count(message) == 3
    with pytest.raises(ValueError, match="exactly three"):
        repeated_notification_text(message, 2)


async def test_ajil_generates_one_safe_english_message() -> None:
    client = FakeAjilClient(
        "Codex reached the weekly limit. Please check Telegram."
    )
    context = TerminalJobContext(
        job_id="job_limit",
        state="failed",
        error_code="RateLimitError",
        error_message="HTTP 429: api_key=should-not-leave-this-host",
    )

    message, source = await generate_terminal_message(
        client,  # type: ignore[arg-type]
        context,
        maximum_characters=240,
    )

    assert source == "ajil"
    assert message == "Codex reached the weekly limit. Please check Telegram."
    prompt = str(client.messages[-1]["content"])
    assert "should-not-leave-this-host" not in prompt
    assert "[REDACTED]" in prompt


async def test_ajil_failure_keeps_completion_call_available() -> None:
    context = TerminalJobContext(job_id="job_failed", state="failed")

    message, source = await generate_terminal_message(
        FakeAjilClient(raises=True),  # type: ignore[arg-type]
        context,
        maximum_characters=240,
    )

    assert source == "fallback"
    assert "Telegram" in message


def test_completion_request_rejects_unsafe_ids_and_wrong_repeat_count() -> None:
    valid = CompletionCallRequest(
        job_id="job_safe-1",
        target_user_id=123,
        terminal_state="completed",
        category="success",
        message="Task complete.",
        repeat_count=3,
        created_at="2026-07-24T00:00:00+00:00",
    )

    assert CompletionCallRequest.from_redis_fields(valid.redis_fields()) == valid
    with pytest.raises(ValueError):
        valid.model_copy(update={"job_id": "../escape"}).model_dump_json()
        CompletionCallRequest.model_validate(
            {**valid.model_dump(), "job_id": "../escape"}
        )
    with pytest.raises(ValueError):
        CompletionCallRequest.model_validate(
            {**valid.model_dump(), "repeat_count": 2}
        )


async def test_publish_uses_atomic_deduplication_script() -> None:
    context = TerminalJobContext(job_id="job_publish", state="completed")
    request = build_completion_request(
        context,
        target_user_id=123,
        message="Task complete.",
        repeat_count=3,
    )
    redis = FakeRedis()

    published = await publish_completion_call(
        redis,  # type: ignore[arg-type]
        CompletionCallConfig(),
        request,
    )

    assert published is True
    assert "completion_call:queued:job_publish" in str(redis.arguments)
    assert "telegram_codex_agent.completion_calls" in redis.arguments
