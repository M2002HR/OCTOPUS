from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from aiogram import Bot, Dispatcher, Router
from aiogram.filters import Command
from aiogram.types import Message

from telegram_codex_agent.core.config import Settings
from telegram_codex_agent.telegram.formatting import as_html, split_telegram_text

logger = logging.getLogger(__name__)
InputHandler = Callable[[Message], Awaitable[str]]


class TelegramBotService:
    """Small Bot API boundary; application work is delegated through a normalized handler."""

    def __init__(self, settings: Settings, handler: InputHandler) -> None:
        self.settings = settings
        self.handler = handler
        self.bot = Bot(settings.telegram.bot_token) if settings.telegram.bot_token else None
        self.dispatcher = Dispatcher()
        self.router = Router()
        self.dispatcher.include_router(self.router)
        self._install_routes()

    def _allowed(self, message: Message) -> bool:
        configured = self.settings.telegram.allowed_user_ids
        return not configured or (
            message.from_user is not None and message.from_user.id in configured
        )

    async def _reply(self, message: Message, text: str) -> None:
        for chunk in split_telegram_text(as_html(text), self.settings.telegram.max_message_length):
            await message.answer(chunk)

    def _install_routes(self) -> None:
        @self.router.message(Command("start"))
        async def start(message: Message) -> None:
            if not self._allowed(message):
                return
            await self._reply(
                message,
                "سلام. من برای گفتگو، پروژه‌ها، کد، فایل، صوت و بررسی مرورگر آماده‌ام. /help را بزنید.",
            )

        @self.router.message(Command("help"))
        async def help_command(message: Message) -> None:
            if not self._allowed(message):
                return
            await self._reply(
                message,
                "دستورها: /status، /projects، /project، /new، /jobs، /job، /stop، /retry، /artifacts، /memory، /remember، /forget، /mode، /voice، /browser، /codex، /logs و /config",
            )

        @self.router.message()
        async def handle_message(message: Message) -> None:
            if not self._allowed(message):
                logger.warning(
                    "rejected unauthorized Telegram update",
                    extra={"telegram_user_id": message.from_user.id if message.from_user else None},
                )
                return
            try:
                await self._reply(message, await self.handler(message))
            except Exception:
                logger.exception("Telegram input handling failed")
                await self._reply(message, "خطای داخلی رخ داد؛ جزئیات برای بررسی ثبت شد.")

    async def run_polling(self) -> None:
        if self.bot is None:
            raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")
        await self.dispatcher.start_polling(self.bot)
