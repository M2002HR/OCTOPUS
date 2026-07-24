from __future__ import annotations

import asyncio
import sys

from redis.asyncio import from_url
from sqlalchemy import text

from telegram_codex_agent.api.app import HealthRegistry
from telegram_codex_agent.core.config import Settings, load_settings
from telegram_codex_agent.db.session import create_engine
from telegram_codex_agent.integrations.ajil import AjilClient
from telegram_codex_agent.telegram.bot import TelegramBotService


async def _reply(_: object) -> str:
    return "پیام دریافت شد. مسیر پردازش شغل در حال راه‌اندازی است."


async def run_bot() -> None:
    service = TelegramBotService(load_settings(), _reply)
    await service.run_polling()


def health_registry(settings: Settings) -> HealthRegistry:
    async def ajil() -> dict[str, object]:
        client = AjilClient(settings.ajil)
        try:
            return {"ok": (await client.health()).get("status") == "ok"}
        finally:
            await client.aclose()

    async def database() -> dict[str, object]:
        engine = create_engine(settings.database)
        try:
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
            return {"ok": True}
        finally:
            await engine.dispose()

    async def redis() -> dict[str, object]:
        client = from_url(settings.redis.url, decode_responses=True)
        try:
            return {"ok": bool(await client.ping())}
        finally:
            await client.aclose()

    return HealthRegistry({"ajil": ajil, "database": database, "redis": redis})


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "bot":
        asyncio.run(run_bot())
    elif command in {"worker", "scheduler"}:
        raise SystemExit(f"{command} runtime is available after the persistent worker bootstrap")
    else:
        raise SystemExit("usage: python -m telegram_codex_agent.runtime {bot|worker|scheduler}")


if __name__ == "__main__":
    main()
