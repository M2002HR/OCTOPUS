import asyncio

from telegram_codex_agent.integrations.codex import CodexAppServer
from telegram_codex_agent.jobs.worker import Worker


def test_extracts_only_final_agent_messages() -> None:
    events = [
        {"method": "item/completed", "params": {"item": {"type": "userMessage", "text": "ignore"}}},
        {"method": "item/completed", "params": {"item": {"type": "agentMessage", "text": "one"}}},
        {"method": "item/completed", "params": {"item": {"type": "agentMessage", "text": "two"}}},
    ]
    assert CodexAppServer._assistant_text(events) == "one\ntwo"


def test_default_approval_never_grants_unknown_request() -> None:
    decision = asyncio.run(CodexAppServer._default_approval("unknown/request", {}))
    assert decision == {"decision": "cancel"}


def test_final_answer_excludes_intermediate_commentary() -> None:
    events = [
        {
            "method": "item/completed",
            "params": {
                "item": {
                    "type": "agentMessage",
                    "phase": "commentary",
                    "text": "I am inspecting the repository.",
                }
            },
        },
        {
            "method": "item/completed",
            "params": {
                "item": {
                    "type": "agentMessage",
                    "phase": "final_answer",
                    "text": "Inspection complete.",
                }
            },
        },
    ]

    assert CodexAppServer._assistant_text(events) == "Inspection complete."


def test_public_codex_commentary_is_streamed_but_reasoning_and_final_are_not() -> None:
    commentary = {
        "item": {
            "type": "agentMessage",
            "phase": "commentary",
            "text": "Checking the API token=private-value now.",
        }
    }
    final = {
        "item": {
            "type": "agentMessage",
            "phase": "final_answer",
            "text": "Done.",
        }
    }
    reasoning = {"item": {"type": "reasoning", "text": "private reasoning"}}

    assert Worker._codex_agent_message("item/completed", commentary) == (
        "Checking the API token=[REDACTED] now."
    )
    assert Worker._codex_agent_message("item/completed", final) == ""
    assert Worker._codex_agent_message("item/completed", reasoning) == ""


def test_codex_token_usage_is_normalized_for_status_and_history() -> None:
    usage = Worker._normalize_token_usage(
        {
            "last": {
                "inputTokens": 100,
                "cachedInputTokens": 80,
                "outputTokens": 20,
                "reasoningOutputTokens": 5,
                "totalTokens": 125,
            },
            "total": {
                "inputTokens": 1000,
                "cachedInputTokens": 800,
                "outputTokens": 200,
                "reasoningOutputTokens": 50,
                "totalTokens": 1250,
            },
            "modelContextWindow": 128000,
        }
    )

    assert usage["last"]["totalTokens"] == 125
    assert usage["total"]["totalTokens"] == 1250
    assert usage["modelContextWindow"] == 128000
