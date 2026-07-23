from __future__ import annotations

from dataclasses import dataclass

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl import types

from voice_agent.config import Settings


class TelegramSafetyError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class TelegramPeer:
    user_id: int
    username: str | None


class TelethonSession:
    """Owns the existing authorized Telethon string session without exposing it in logs."""

    def __init__(self, settings: Settings) -> None:
        settings.validate_telegram()
        proxy: dict[str, object] | None = None
        if settings.telegram_proxy_enabled:
            proxy = {
                "proxy_type": settings.telegram_proxy_type,
                "addr": settings.telegram_proxy_host,
                "port": settings.telegram_proxy_port,
                "rdns": settings.telegram_proxy_rdns,
            }
            if settings.telegram_proxy_username:
                proxy["username"] = settings.telegram_proxy_username
            if settings.telegram_proxy_password:
                proxy["password"] = settings.telegram_proxy_password
        self.client = TelegramClient(
            StringSession(settings.telegram_string_session),
            settings.telegram_api_id,
            settings.telegram_api_hash,
            proxy=proxy,
        )
        self.allowed_peer_ids = settings.allowed_peer_ids

    async def connect(self) -> None:
        await self.client.connect()
        if not await self.client.is_user_authorized():
            raise TelegramSafetyError("configured Telethon session is not authorized")

    async def close(self) -> None:
        await self.client.disconnect()

    async def resolve_allowed_user(self, username: str) -> TelegramPeer:
        entity = await self.client.get_entity(username)
        if not isinstance(entity, types.User) or entity.bot or entity.deleted:
            raise TelegramSafetyError("target must be an active, non-bot Telegram user")
        if entity.id not in self.allowed_peer_ids:
            raise TelegramSafetyError("resolved target is not in VOICE_AGENT_ALLOWED_PEER_IDS")
        return TelegramPeer(entity.id, entity.username)
