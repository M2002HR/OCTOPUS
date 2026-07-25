import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.exceptions import TelegramNetworkError

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
    service = _service(usernames=["@We_Are_Waiting_For_Him"])

    assert service._allowed(_message("we_are_waiting_for_him"))
    assert not service._allowed(_message("another_user"))
    assert not service._allowed(_message(None))


def test_callback_actor_uses_the_same_username_policy() -> None:
    service = _service(usernames=["we_are_waiting_for_him"])

    assert service._allowed_actor(
        SimpleNamespace(id=100, username="we_are_waiting_for_him"), 200
    )
    assert not service._allowed_actor(SimpleNamespace(id=100, username="another_user"), 200)


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


@pytest.mark.asyncio
async def test_polling_retries_command_registration_after_network_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(usernames=["we_are_waiting_for_him"])
    network_error = TelegramNetworkError(method=object(), message="temporary outage")  # type: ignore[arg-type]
    bot = SimpleNamespace(
        set_my_commands=AsyncMock(side_effect=[network_error, None]),
        session=SimpleNamespace(close=AsyncMock()),
    )
    service.bot = bot  # type: ignore[assignment]
    service.dispatcher.start_polling = AsyncMock()
    sleep = AsyncMock()
    monkeypatch.setattr(asyncio, "sleep", sleep)

    await service.run_polling()

    assert bot.set_my_commands.await_count == 2
    sleep.assert_awaited_once_with(10)
    service.dispatcher.start_polling.assert_awaited_once_with(bot)
    bot.session.close.assert_awaited_once()
