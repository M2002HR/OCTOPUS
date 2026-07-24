import asyncio

from telegram_codex_agent.integrations.codex import CodexAppServer


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
