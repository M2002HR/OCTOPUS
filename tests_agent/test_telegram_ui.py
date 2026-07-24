import pytest

pytest.importorskip("aiogram")

from telegram_codex_agent.telegram.bot import TelegramBotService


def test_command_menu_exposes_codex_session_and_browser_controls() -> None:
    commands = {item.command for item in TelegramBotService._command_menu()}

    assert {
        "new",
        "resume",
        "status",
        "permissions",
        "logs",
        "language",
        "browser",
        "diff",
        "review",
    } <= commands


def test_persistent_keyboard_keeps_primary_actions_one_tap_away() -> None:
    labels = {
        button.text
        for row in TelegramBotService._main_keyboard().keyboard
        for button in row
    }

    assert {
        "🏠 Home",
        "📁 Projects",
        "💬 Sessions",
        "🌐 Browser",
        "📜 Logs",
        "🔍 Review",
        "⚙️ Settings",
        "🛑 Stop",
    } <= labels
