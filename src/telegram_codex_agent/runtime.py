from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any

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
from telegram_codex_agent.telegram.normalization import deterministic_inbox_path, sha256_file

logger = logging.getLogger(__name__)


async def extract_bot_media(message: object, settings: Settings) -> tuple[str, str, dict[str, object]]:
    """Download one Telegram attachment into the managed artifact inbox.

    The job stores only a local, content-addressed record.  Telegram file IDs
    and raw bytes never appear in a status message or in an LLM prompt.
    """
    media_kind = ""
    media: Any = None
    mime_type = "application/octet-stream"
    for kind in ("voice", "photo", "document", "video"):
        candidate = getattr(message, kind, None)
        if candidate:
            media_kind, media = kind, candidate[-1] if kind == "photo" else candidate
            mime_type = getattr(media, "mime_type", None) or (
                "image/jpeg" if kind == "photo" else "audio/ogg" if kind == "voice" else mime_type
            )
            break
    if not media_kind:
        return "", "", {}
    size = int(getattr(media, "file_size", 0) or 0)
    if size > settings.artifacts.telegram_direct_upload_max_bytes:
        raise ValueError("attachment exceeds the configured Telegram size limit")
    unique_id = str(getattr(media, "file_unique_id", "") or "attachment")
    filename = str(getattr(media, "file_name", "") or f"{media_kind}.bin")
    if media_kind == "voice":
        filename = "voice.ogg"
    elif media_kind == "photo":
        filename = "photo.jpg"
    destination = deterministic_inbox_path(
        Path(settings.artifacts.root).resolve() / "inbox",
        file_unique_id=unique_id,
        filename=filename,
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    bot = getattr(message, "bot", None)
    if bot is None:
        raise RuntimeError("Telegram Bot instance is unavailable for attachment download")
    await bot.download(media, destination=destination)
    if not destination.is_file() or destination.stat().st_size == 0:
        raise RuntimeError("Telegram attachment download did not produce a file")
    caption = str(getattr(message, "caption", "") or "").strip()
    reply = getattr(message, "reply_to_message", None)
    reply_text = str(getattr(reply, "text", "") or getattr(reply, "caption", "") or "").strip()
    objective = caption or {
        "voice": "Transcribe this voice message and answer it.",
        "photo": "Analyze this image and describe its important details.",
        "document": "Review the attached document and explain what it contains.",
        "video": "Review the attached video and explain what it contains.",
    }[media_kind]
    if reply_text:
        objective = f"[Reply context]\n{reply_text}\n\n[New request]\n{objective}"
    return objective, media_kind, {
        "attachment_kind": media_kind,
        "attachment_path": str(destination),
        "attachment_mime_type": mime_type,
        "attachment_size_bytes": destination.stat().st_size,
        "attachment_sha256": sha256_file(destination),
    }


async def run_bot() -> None:
    while True:
        settings = load_settings()
        if not settings.telegram.bot_token:
            logger.warning("Telegram bot token is absent; bot will retry after configuration reload")
            await asyncio.sleep(30)
            continue
        jobs = job_service(settings)
        await ProjectRegistry(create_session_factory(create_engine(settings.database)), settings.projects).sync()

        async def reply(message: object, jobs=jobs, settings=settings) -> str:
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
            if text == "/status":
                return "سامانه فعال است. برای مشاهدهٔ کارها /jobs و برای پروژه‌ها /projects را بزنید."
            if text == "/jobs":
                rows = await jobs.recent_jobs(from_user.id, chat.id)
                return "\n".join(f"• {row.id}: {row.state}" for row in rows) or "کاری ثبت نشده است."
            if text.startswith("/job "):
                job_id = text.removeprefix("/job ").strip()
                job = await jobs.get_for_context(from_user.id, chat.id, job_id)
                return f"{job.id}: {job.state}\n{job.result_summary or job.error_message}" if job else "کار پیدا نشد."
            if text.startswith("/logs "):
                job_id = text.removeprefix("/logs ").strip()
                job = await jobs.get_for_context(from_user.id, chat.id, job_id)
                if job is None:
                    return "کار پیدا نشد."
                events = await jobs.events(job_id)
                return "\n".join(
                    f"{row.sequence}. {row.event_type}: {row.message}"
                    for row in events[-20:]
                ) or "رخدادی ثبت نشده است."
            if text.startswith("/stop "):
                job_id = text.removeprefix("/stop ").strip()
                return "درخواست لغو ثبت شد." if await jobs.cancel_for_context(from_user.id, chat.id, job_id) else "کار قابل لغو نیست یا پیدا نشد."
            if text == "/codex":
                context = await jobs.active_context(from_user.id, chat.id)
                preferences = context[0].preferences_json if context else {}
                selected = str(preferences.get("codex_model", ""))
                effort = str(preferences.get("codex_reasoning_effort", ""))
                return f"مدل Codex: {selected or settings.codex.model}\nسطح استدلال: {effort or settings.codex.reasoning_effort}\nبرای تغییر: /codex model <model> یا /config effort <level>"
            if text.startswith("/codex model "):
                model = text.removeprefix("/codex model ").strip()
                if not model or not model.startswith("gpt-"):
                    return "نام مدل معتبر نیست."
                return "مدل پیش‌فرض شما ذخیره شد." if await jobs.set_user_preference(from_user.id, "codex_model", model) else "ابتدا یک پیام عادی بفرستید تا حساب ثبت شود."
            if text == "/config":
                context = await jobs.active_context(from_user.id, chat.id)
                preferences = context[0].preferences_json if context else {}
                return (
                    "تنظیمات اجرای شما:\n"
                    f"• مدل Codex: {preferences.get('codex_model') or settings.codex.model}\n"
                    f"• سطح استدلال: {preferences.get('codex_reasoning_effort') or settings.codex.reasoning_effort}\n"
                    f"• زبان پاسخ: {preferences.get('response_language') or settings.app.language}\n"
                    f"• رخدادهای زنده: {'روشن' if preferences.get('stream_progress', True) else 'خاموش'}\n\n"
                    "تغییرها: /config model <gpt-model> | /config effort <low|medium|high|xhigh|max|ultra> | /config language <fa|en> | /config progress <on|off>"
                )
            if text.startswith("/config model "):
                model = text.removeprefix("/config model ").strip()
                if not model.startswith("gpt-"):
                    return "نام مدل معتبر نیست."
                return "مدل ذخیره شد." if await jobs.set_user_preference(from_user.id, "codex_model", model) else "ابتدا یک پیام عادی بفرستید تا حساب ثبت شود."
            if text.startswith("/config effort "):
                effort = text.removeprefix("/config effort ").strip().casefold()
                if effort not in {"low", "medium", "high", "xhigh", "max", "ultra"}:
                    return "سطح استدلال معتبر نیست."
                return "سطح استدلال ذخیره شد." if await jobs.set_user_preference(from_user.id, "codex_reasoning_effort", effort) else "ابتدا یک پیام عادی بفرستید تا حساب ثبت شود."
            if text.startswith("/config language "):
                language = text.removeprefix("/config language ").strip().casefold()
                if language not in {"fa", "en"}:
                    return "زبان فقط fa یا en است."
                return "زبان پاسخ ذخیره شد." if await jobs.set_user_preference(from_user.id, "response_language", language) else "ابتدا یک پیام عادی بفرستید تا حساب ثبت شود."
            if text.startswith("/config progress "):
                value = text.removeprefix("/config progress ").strip().casefold()
                if value not in {"on", "off"}:
                    return "مقدار فقط on یا off است."
                return "رخدادهای زنده ذخیره شد." if await jobs.set_user_preference(from_user.id, "stream_progress", value == "on") else "ابتدا یک پیام عادی بفرستید تا حساب ثبت شود."
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
            objective, content_type, metadata = await extract_bot_media(message, settings)
            job_id = await jobs.create_from_text(
                from_user.id,
                chat.id,
                objective or text or "[empty message]",
                content_type=content_type or "text",
                metadata=metadata,
            )
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
