from __future__ import annotations

import asyncio
import logging
import sys

from redis.asyncio import from_url
from sqlalchemy import text

from telegram_codex_agent.api.app import HealthRegistry
from telegram_codex_agent.core.config import Settings, load_settings
from telegram_codex_agent.db.session import create_engine, create_session_factory
from telegram_codex_agent.integrations.ajil import AjilClient
from telegram_codex_agent.jobs.service import JobService
from telegram_codex_agent.jobs.worker import Worker
from telegram_codex_agent.memory import MemoryService
from telegram_codex_agent.projects import ProjectRegistry
from telegram_codex_agent.telegram.bot import TelegramBotService

logger = logging.getLogger(__name__)


async def run_bot() -> None:
    while True:
        settings = load_settings()
        if not settings.telegram.bot_token:
            logger.warning("Telegram bot token is absent; bot will retry after configuration reload")
            await asyncio.sleep(30)
            continue
        jobs = job_service(settings)
        await ProjectRegistry(create_session_factory(create_engine(settings.database)), settings.projects).sync()

        async def reply(message: object, jobs=jobs) -> str:
            text = str(getattr(message, "text", "") or getattr(message, "caption", "")).strip()
            from_user = getattr(message, "from_user", None)
            chat = getattr(message, "chat", None)
            if from_user is None or chat is None:
                return "پیام فاقد شناسهٔ کاربر یا گفت‌وگو است."
            if text == "/projects":
                projects = await jobs.list_projects()
                return "\n".join(f"• {row['slug']} — {row['name']}" for row in projects) or "پروژهٔ فعالی ثبت نشده است."
            if text.startswith("/project "):
                slug = text.removeprefix("/project ").strip()
                return "پروژه انتخاب شد." if await jobs.select_project(from_user.id, chat.id, slug) else "پروژه پیدا نشد؛ /projects را ببینید."
            context = await jobs.active_context(from_user.id, chat.id)
            memory = MemoryService(jobs.sessions)
            if text.startswith("/remember "):
                if context is None:
                    return "ابتدا یک پیام عادی بفرستید تا گفتگو ساخته شود."
                content = text.removeprefix("/remember ").strip()
                memory_id = await memory.remember(
                    context[0].id,
                    content,
                    conversation_id=context[1].id,
                    project_id=context[1].project_id,
                )
                return f"ثبت شد. شناسهٔ حافظه: {memory_id}"
            if text == "/memory":
                if context is None:
                    return "حافظه‌ای برای این گفتگو وجود ندارد."
                rows = await memory.list(context[0].id)
                return "\n".join(f"• {row.id}: {row.content[:140]}" for row in rows) or "حافظه‌ای ثبت نشده است."
            if text.startswith("/forget "):
                if context is None:
                    return "شناسهٔ حافظه نامعتبر است."
                memory_id = text.removeprefix("/forget ").strip()
                return "حذف شد." if await memory.forget(context[0].id, memory_id) else "حافظه پیدا نشد."
            job_id = await jobs.create_from_text(from_user.id, chat.id, text or "[media message]")
            return f"درخواست ثبت شد و در حال پردازش است. شناسهٔ کار: {job_id}"

        service = TelegramBotService(settings, reply)
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


def job_service(settings: Settings) -> JobService:
    engine = create_engine(settings.database)
    return JobService(create_session_factory(engine), from_url(settings.redis.url, decode_responses=True), settings.redis.stream, settings.redis.consumer_group)


async def run_worker() -> None:
    worker = Worker(load_settings())
    try:
        await worker.run()
    finally:
        await worker.close()


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "bot":
        asyncio.run(run_bot())
    elif command == "worker":
        asyncio.run(run_worker())
    elif command == "scheduler":
        raise SystemExit("scheduler is not enabled yet")
    else:
        raise SystemExit("usage: python -m telegram_codex_agent.runtime {bot|worker|scheduler}")


if __name__ == "__main__":
    main()
