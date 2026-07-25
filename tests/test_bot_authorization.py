from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from telegram_codex_agent.core.config import TelegramConfig
from telegram_codex_agent.telegram.bot import TelegramBotService


async def _unused_handler(*_args: object) -> str:
    return "unused"


def _service(*, usernames: list[str]) -> TelegramBotService:
    settings = SimpleNamespace(
        telegram=TelegramConfig(
            allowed_usernames=usernames,
            bot_token_env="TEST_TELEGRAM_BOT_TOKEN",
        ),
    )
    return TelegramBotService(settings, _unused_handler)  # type: ignore[arg-type]


def _message(username: str | None) -> SimpleNamespace:
    return SimpleNamespace(
        from_user=SimpleNamespace(id=100, username=username),
        chat=SimpleNamespace(id=200),
    )


def test_username_allowlist_accepts_only_configured_username() -> None:
    service = _service(usernames=["@We_Arew_Waiting_For_Him"])

    assert service._allowed(_message("we_arew_waiting_for_him"))
    assert not service._allowed(_message("another_user"))
    assert not service._allowed(_message(None))


def test_username_allowlist_rejects_duplicate_or_empty_entries() -> None:
    with pytest.raises(ValueError, match="duplicates"):
        TelegramConfig(allowed_usernames=["owner", "@OWNER"])
    with pytest.raises(ValueError, match="empty"):
        TelegramConfig(allowed_usernames=["  "])


@pytest.mark.asyncio
async def test_unauthorized_message_receives_denial_response() -> None:
    message = SimpleNamespace(answer=AsyncMock())

    await TelegramBotService._reject_message(message)  # type: ignore[arg-type]

    message.answer.assert_awaited_once_with("شما دسترسی ندارید.")
