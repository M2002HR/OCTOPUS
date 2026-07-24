from __future__ import annotations

import logging
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Any

from aiogram import Bot, Dispatcher, Router
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramNetworkError
from aiogram.filters import Command
from aiogram.types import Message

from telegram_codex_agent.core.config import Settings
from telegram_codex_agent.telegram.formatting import as_html, split_telegram_text

logger = logging.getLogger(__name__)
InputHandler = Callable[[Message], Awaitable[str]]


class HttpProxyAiohttpSession(AiohttpSession):
    """HTTP CONNECT proxy support without requiring aiohttp-socks.

    aiogram routes every proxy URL through its optional SOCKS connector.  The
    deployment proxy here is standard HTTP CONNECT, which aiohttp supports per
    request natively.
    """

    def __init__(self, proxy_url: str) -> None:
        super().__init__()
        self.proxy_url = proxy_url

    async def make_request(self, bot: Bot, method: Any, timeout: int | None = None) -> Any:
        session = await self.create_session()
        url = self.api.api_url(token=bot.token, method=method.__api_method__)
        form = self.build_form_data(bot=bot, method=method)
        try:
            async with session.post(
                url,
                data=form,
                timeout=self.timeout if timeout is None else timeout,
                proxy=self.proxy_url,
            ) as response:
                raw_result = await response.text()
        except TimeoutError as exc:
            raise TelegramNetworkError(method=method, message="Request timeout error") from exc
        except Exception as exc:
            raise TelegramNetworkError(method=method, message=f"{type(exc).__name__}: {exc}") from exc
        return self.check_response(
            bot=bot,
            method=method,
            status_code=response.status,
            content=raw_result,
        ).result

    async def stream_content(
        self,
        url: str,
        headers: dict[str, Any] | None = None,
        timeout: int = 30,
        chunk_size: int = 65_536,
        raise_for_status: bool = True,
    ) -> AsyncGenerator[bytes, None]:
        """Proxy media downloads as well as ordinary Bot API requests."""
        session = await self.create_session()
        async with session.get(
            url,
            timeout=timeout,
            headers=headers or {},
            proxy=self.proxy_url,
            raise_for_status=raise_for_status,
        ) as response:
            async for chunk in response.content.iter_chunked(chunk_size):
                yield chunk


class TelegramBotService:
    """Small Bot API boundary; application work is delegated through a normalized handler."""

    def __init__(self, settings: Settings, handler: InputHandler) -> None:
        self.settings = settings
        self.handler = handler
        self.bot = (
            Bot(
                settings.telegram.bot_token,
                session=HttpProxyAiohttpSession(settings.telegram.bot_proxy_url)
                if settings.telegram.bot_proxy_url
                else None,
            )
            if settings.telegram.bot_token
            else None
        )
        self.dispatcher = Dispatcher()
        self.router = Router()
        self.dispatcher.include_router(self.router)
        self._install_routes()

    def _allowed(self, message: Message) -> bool:
        user_ids = self.settings.telegram.allowed_user_ids
        chat_ids = self.settings.telegram.allowed_chat_ids
        user_allowed = not user_ids or (
            message.from_user is not None and message.from_user.id in user_ids
        )
        chat_allowed = not chat_ids or message.chat.id in chat_ids
        return user_allowed and chat_allowed

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
                "دستورها: /status، /projects، /project <slug>، /jobs، /job <id>، /logs <id>، /stop <id>، /codex، /config، /memory، /remember <text> و /forget <id>",
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
