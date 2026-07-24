from __future__ import annotations

import logging
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramNetworkError
from aiogram.filters import Command
from aiogram.types import (
    BotCommand,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

from telegram_codex_agent.core.config import Settings
from telegram_codex_agent.telegram.formatting import as_html, split_telegram_text

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class BotResponse:
    text: str
    inline_buttons: list[list[tuple[str, str]]] = field(default_factory=list)
    show_main_keyboard: bool = False


InputHandler = Callable[[Message, str | None, int | None], Awaitable[BotResponse | str]]


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
                default=DefaultBotProperties(parse_mode=ParseMode.HTML),
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

    @staticmethod
    def _main_keyboard() -> ReplyKeyboardMarkup:
        return ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="🏠 Home"), KeyboardButton(text="📊 Status")],
                [KeyboardButton(text="📁 Projects"), KeyboardButton(text="💬 Sessions")],
                [KeyboardButton(text="🌐 Browser"), KeyboardButton(text="📜 Logs")],
                [KeyboardButton(text="🧾 Jobs"), KeyboardButton(text="📚 History")],
                [KeyboardButton(text="🔍 Review"), KeyboardButton(text="⚙️ Settings")],
                [KeyboardButton(text="🛑 Stop")],
            ],
            resize_keyboard=True,
            is_persistent=True,
            input_field_placeholder="Send a task to Codex…",
        )

    async def _reply(self, message: Message, response: BotResponse | str) -> None:
        payload = response if isinstance(response, BotResponse) else BotResponse(str(response))
        chunks = split_telegram_text(as_html(payload.text), self.settings.telegram.max_message_length)
        inline_markup = (
            InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text=label, callback_data=data) for label, data in row]
                    for row in payload.inline_buttons
                ]
            )
            if payload.inline_buttons
            else None
        )
        for index, chunk in enumerate(chunks):
            markup: InlineKeyboardMarkup | ReplyKeyboardMarkup | None = None
            if index == len(chunks) - 1:
                markup = inline_markup or (self._main_keyboard() if payload.show_main_keyboard else None)
            await message.answer(chunk, reply_markup=markup)
        if inline_markup is not None and payload.show_main_keyboard:
            await message.answer("Quick controls are ready below.", reply_markup=self._main_keyboard())

    async def _dispatch_input(
        self, message: Message, command: str | None = None, actor_user_id: int | None = None
    ) -> None:
        try:
            await self._reply(message, await self.handler(message, command, actor_user_id))
        except Exception:
            logger.exception("Telegram input handling failed")
            await self._reply(message, "Internal error. The diagnostic details were recorded.")

    def _install_routes(self) -> None:
        @self.router.message(Command("start"))
        async def start(message: Message) -> None:
            if not self._allowed(message):
                return
            await self._dispatch_input(message, "/home")

        @self.router.message(Command("help"))
        async def help_command(message: Message) -> None:
            if not self._allowed(message):
                return
            await self._dispatch_input(message, "/help")

        @self.router.callback_query()
        async def handle_callback(callback: CallbackQuery) -> None:
            message = callback.message
            user_ids = self.settings.telegram.allowed_user_ids
            chat_ids = self.settings.telegram.allowed_chat_ids
            allowed = (
                isinstance(message, Message)
                and (not user_ids or callback.from_user.id in user_ids)
                and (not chat_ids or message.chat.id in chat_ids)
            )
            if not allowed or not isinstance(message, Message):
                await callback.answer("Not allowed", show_alert=True)
                return
            await callback.answer()
            await self._dispatch_input(
                message,
                callback.data or "/home",
                actor_user_id=callback.from_user.id,
            )

        @self.router.message()
        async def handle_message(message: Message) -> None:
            if not self._allowed(message):
                logger.warning(
                    "rejected unauthorized Telegram update",
                    extra={"telegram_user_id": message.from_user.id if message.from_user else None},
                )
                return
            await self._dispatch_input(message)

    @staticmethod
    def _command_menu() -> list[BotCommand]:
        return [
            BotCommand(command="start", description="Open the Octopus control center"),
            BotCommand(command="new", description="Start a fresh Codex session"),
            BotCommand(command="resume", description="Resume a saved Codex session"),
            BotCommand(command="status", description="Show the active Codex context"),
            BotCommand(command="usage", description="Show Codex weekly account limit"),
            BotCommand(command="history", description="Show active session history and logs"),
            BotCommand(command="projects", description="Choose a workspace under Code"),
            BotCommand(command="jobs", description="View recent and running jobs"),
            BotCommand(command="logs", description="Configure live logs or inspect a job"),
            BotCommand(command="permissions", description="Set Codex permission mode"),
            BotCommand(command="model", description="Choose the Codex model"),
            BotCommand(command="reasoning", description="Choose reasoning effort"),
            BotCommand(command="fast", description="Toggle Codex Fast mode"),
            BotCommand(command="language", description="Choose input and response language"),
            BotCommand(command="browser", description="Browser checks and screenshots"),
            BotCommand(command="diff", description="Inspect uncommitted changes"),
            BotCommand(command="review", description="Review the working tree"),
            BotCommand(command="config", description="Open all settings"),
            BotCommand(command="memory", description="List saved agent memory"),
            BotCommand(command="help", description="Show command help"),
        ]

    async def run_polling(self) -> None:
        if self.bot is None:
            raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")
        await self.bot.set_my_commands(self._command_menu())
        await self.dispatcher.start_polling(self.bot)
