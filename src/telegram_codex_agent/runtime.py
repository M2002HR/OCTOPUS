from __future__ import annotations

import asyncio
import logging
import re
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
from telegram_codex_agent.telegram.bot import BotResponse, TelegramBotService
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
        await ProjectRegistry(
            create_session_factory(create_engine(settings.database)),
            settings.projects,
            settings.workspace,
        ).sync()

        async def reply(
            message: object,
            command_override: str | None = None,
            actor_user_id: int | None = None,
            jobs=jobs,
            settings=settings,
        ) -> BotResponse | str:
            text = command_override or str(
                getattr(message, "text", "") or getattr(message, "caption", "")
            ).strip()
            from_user = getattr(message, "from_user", None)
            chat = getattr(message, "chat", None)
            user_id = actor_user_id or (from_user.id if from_user is not None else None)
            if user_id is None or chat is None:
                return "The message has no Telegram user or chat identifier."
            aliases = {
                "🏠 Home": "/home",
                "📊 Status": "/status",
                "📁 Projects": "/projects",
                "💬 Sessions": "/resume",
                "🧾 Jobs": "/jobs",
                "🌐 Browser": "/browser",
                "🔍 Review": "/review",
                "📜 Logs": "/logs",
                "⚙️ Settings": "/config",
                "🛑 Stop": "/jobs",
                "nav:home": "/home",
                "nav:projects": "/projects",
                "nav:sessions": "/resume",
                "nav:jobs": "/jobs",
                "nav:settings": "/config",
                "nav:logs": "/logs",
                "nav:permissions": "/permissions",
                "nav:model": "/model",
                "nav:reasoning": "/reasoning",
                "nav:language": "/language",
                "nav:browser": "/browser",
                "nav:review": "/review_menu",
            }
            text = aliases.get(text, text)
            if text.startswith(("/permission ", "/permision ")):
                text = "/permissions " + text.split(maxsplit=1)[1]
            elif text in {"/permission", "/permision"}:
                text = "/permissions"
            if text.startswith("/language "):
                text = "/config language " + text.removeprefix("/language ").strip()
            if text.startswith("project:"):
                text = f"/project {text.removeprefix('project:')}"
            if text.startswith("session:"):
                text = f"/resume {text.removeprefix('session:')}"
            if text.startswith("config:model:"):
                text = f"/config model {text.removeprefix('config:model:')}"
            if text.startswith("config:effort:"):
                text = f"/config effort {text.removeprefix('config:effort:')}"
            if text.startswith("config:language:"):
                text = f"/config language {text.removeprefix('config:language:')}"
            if text.startswith("logs:level:"):
                text = f"/logs level {text.removeprefix('logs:level:')}"
            if text.startswith("permission:"):
                text = f"/permissions {text.removeprefix('permission:')}"
            if text.startswith("browser:"):
                text = f"/browser {text.removeprefix('browser:')}"

            if text in {"/home", "/start"}:
                return BotResponse(
                    "Octopus is ready. Choose a workspace/session or send a task directly.\n\n"
                    "Codex handles implementation, testing, Git and system work. Ajil routes and orchestrates the request.",
                    [
                        [("📁 Workspaces", "nav:projects"), ("💬 Codex sessions", "nav:sessions")],
                        [("📊 Status", "nav:home_status"), ("📜 Live logs", "nav:logs")],
                        [("⚙️ Settings", "nav:settings"), ("🔐 Permissions", "nav:permissions")],
                        [("➕ New session", "cmd:new"), ("🧾 Jobs", "nav:jobs")],
                        [("🌐 Browser & screenshots", "nav:browser"), ("🔍 Review & diff", "nav:review")],
                    ],
                    show_main_keyboard=True,
                )
            if text == "nav:home_status":
                text = "/status"
            if text == "cmd:new":
                text = "/new"
            if text == "/help":
                return BotResponse(
                    "Codex-style commands:\n"
                    "/new — fresh session in the current workspace\n"
                    "/resume — continue an existing Codex thread\n"
                    "/status — workspace, model, permission and latest job\n"
                    "/permissions — Read Only / Workspace / Full Access\n"
                    "/model and /reasoning — execution model controls\n"
                    "/language — voice input and AI response language\n"
                    "/diff — inspect uncommitted changes\n"
                    "/review — review the working tree\n"
                    "/browser — browser checks, screenshots and artifacts\n"
                    "/stop <job-id> — interrupt active work\n"
                    "/logs — live log level; /logs <job-id> for event history\n"
                    "/projects, /jobs, /config, /memory",
                    [[("🏠 Home", "nav:home"), ("⚙️ Settings", "nav:settings")]],
                )
            if text == "/projects":
                projects = await jobs.list_projects()
                if not projects:
                    return "No Git workspaces were found under the configured Code root."
                return BotResponse(
                    "Choose a workspace. Codex will use it as its working directory:\n\n"
                    + "\n".join(f"• {row['name']}  /project {row['slug']}" for row in projects),
                    [[(f"📁 {row['name']}", f"project:{row['slug']}")] for row in projects[:20]]
                    + [[("🏠 Home", "nav:home")]],
                )
            if text.startswith("/project "):
                slug = text.removeprefix("/project ").strip()
                if await jobs.select_project(user_id, chat.id, slug):
                    return BotResponse(
                        f"Workspace selected: {slug}\nSend a task, create /new, or /resume an existing session.",
                        [[("➕ New Codex session", "cmd:new"), ("💬 Resume", "nav:sessions")]],
                    )
                return "Workspace not found. Open /projects and choose one from the list."
            if text == "/new":
                conversation_id = await jobs.new_conversation(user_id, chat.id)
                return BotResponse(
                    "Fresh Codex session created in the current workspace. Your next task starts a new thread.",
                    [[("📊 Session status", "nav:home_status"), ("💬 Previous sessions", "nav:sessions")]],
                ) if conversation_id else "Send one normal message first so your Telegram account can be registered."
            if text == "/resume":
                sessions = await jobs.list_codex_sessions(user_id, chat.id)
                if not sessions:
                    return BotResponse("There are no saved Codex sessions yet.", [[("➕ New session", "cmd:new")]])
                return BotResponse(
                    "Choose a Codex thread to continue. The next task will use thread/resume:\n\n"
                    + "\n".join(
                        f"{'●' if row['active'] else '○'} {row['project']} · {str(row['thread_id'])[:8]} · {row['model']}"
                        for row in sessions
                    ),
                    [[(f"{'●' if row['active'] else '○'} {row['project']} · {str(row['thread_id'])[:8]}", f"session:{row['id']}")]
                     for row in sessions],
                )
            if text.startswith("/resume "):
                session_id = text.removeprefix("/resume ").strip()
                return "Codex session resumed. Send the next task to continue its context." if await jobs.resume_codex_session(user_id, chat.id, session_id) else "That session was not found in this Telegram chat."
            if text == "/status":
                context = await jobs.active_context(user_id, chat.id)
                preferences = context[0].preferences_json if context else {}
                sessions = await jobs.list_codex_sessions(user_id, chat.id, limit=1)
                recent = await jobs.recent_jobs(user_id, chat.id, limit=1)
                return BotResponse(
                    "Octopus status: ONLINE\n"
                    f"Codex model: {preferences.get('codex_model') or settings.codex.model}\n"
                    f"Reasoning: {preferences.get('codex_reasoning_effort') or settings.codex.reasoning_effort}\n"
                    f"Language: {preferences.get('response_language') or settings.app.language}\n"
                    f"Permissions: {preferences.get('sandbox_mode') or settings.codex.sandbox_mode}\n"
                    f"Live logs: {preferences.get('log_level') or 'info'}\n"
                    f"Codex thread: {str(sessions[0]['thread_id'])[:12] if sessions else 'not started'}\n"
                    f"Latest job: {recent[0].state if recent else 'none'}",
                    [[("💬 Sessions", "nav:sessions"), ("🧾 Jobs", "nav:jobs")], [("🔐 Permissions", "nav:permissions"), ("⚙️ Settings", "nav:settings")]],
                )
            if text == "/jobs":
                rows = await jobs.recent_jobs(user_id, chat.id)
                if not rows:
                    return "No jobs have been submitted in this chat."
                return BotResponse(
                    "Recent jobs:\n\n" + "\n".join(f"• {row.id[:8]} · {row.state} · {row.intent}" for row in rows),
                    [[(f"{row.state} · {row.id[:8]}", f"job:{row.id}")] for row in rows[:8]]
                    + [[("🏠 Home", "nav:home")]],
                )
            if text.startswith("job:"):
                text = f"/job {text.removeprefix('job:')}"
            if text.startswith("/job "):
                job_id = text.removeprefix("/job ").strip()
                job = await jobs.get_for_context(user_id, chat.id, job_id)
                return BotResponse(
                    f"Job: {job.id}\nState: {job.state}\nIntent: {job.intent}\n\n{job.result_summary or job.error_message or 'Still running.'}",
                    [[("📜 Event log", f"joblogs:{job.id}"), ("🛑 Stop", f"jobstop:{job.id}")]],
                ) if job else "Job not found in this Telegram chat."
            if text.startswith("joblogs:"):
                text = f"/logs {text.removeprefix('joblogs:')}"
            if text.startswith("jobstop:"):
                text = f"/stop {text.removeprefix('jobstop:')}"
            if text == "/logs":
                context = await jobs.active_context(user_id, chat.id)
                preferences = context[0].preferences_json if context else {}
                level = str(preferences.get("log_level") or "info")
                return BotResponse(
                    "Live Codex/Octopus log level controls what is pushed while a job runs.\n\n"
                    f"Current level: {level}\n"
                    "INFO shows lifecycle phases, thread/turn events, commands and file changes.\n"
                    "DEBUG also retains verbose diagnostic events. ERROR sends only failures. OFF disables live updates.",
                    [[("🔴 Error", "logs:level:error"), ("🔵 Info", "logs:level:info")],
                     [("🟣 Debug", "logs:level:debug"), ("⚫ Off", "logs:level:off")],
                     [("🧾 Job history", "nav:jobs"), ("🏠 Home", "nav:home")]],
                )
            if text.startswith("/logs level "):
                level = text.removeprefix("/logs level ").strip().casefold()
                if level not in {"off", "error", "warning", "info", "debug"}:
                    return "Log level must be off, error, warning, info, or debug."
                saved = await jobs.set_user_preference(user_id, "log_level", level)
                await jobs.set_user_preference(user_id, "stream_progress", level not in {"off", "error"})
                return BotResponse(
                    f"Live log level changed to {level}.",
                    [[("📜 Log settings", "nav:logs"), ("🏠 Home", "nav:home")]],
                ) if saved else "Send one task first so your account can be registered."
            if text.startswith("/logs "):
                job_id = text.removeprefix("/logs ").strip()
                job = await jobs.get_for_context(user_id, chat.id, job_id)
                if job is None:
                    return "Job not found."
                events = await jobs.events(job_id)
                return "\n".join(
                    f"{row.sequence}. {row.event_type}: {row.message}"
                    for row in events[-40:]
                ) or "No events were recorded."
            if text.startswith("/stop "):
                job_id = text.removeprefix("/stop ").strip()
                return "Cancellation requested." if await jobs.cancel_for_context(user_id, chat.id, job_id) else "The job is already terminal or was not found."
            if text == "/permissions":
                context = await jobs.active_context(user_id, chat.id)
                preferences = context[0].preferences_json if context else {}
                current = str(preferences.get("sandbox_mode") or settings.codex.sandbox_mode)
                return BotResponse(
                    f"Current Codex permission mode: {current}\n\n"
                    "Read Only — inspect and plan only.\n"
                    "Workspace — edit and run commands inside the selected project.\n"
                    "Full Access — unrestricted host/project work for trusted tasks.",
                    [[("🔒 Read Only", "permission:read-only")],
                     [("🧰 Workspace", "permission:workspace-write")],
                     [("⚡ Full Access", "permission:danger-full-access")],
                     [("🏠 Home", "nav:home")]],
                )
            if text.startswith("/permissions "):
                mode = text.removeprefix("/permissions ").strip()
                if mode not in {"read-only", "workspace-write", "danger-full-access"}:
                    return "Unknown permission mode. Open /permissions and choose a button."
                saved = await jobs.set_user_preference(user_id, "sandbox_mode", mode)
                await jobs.set_user_preference(user_id, "approval_policy", "never")
                return f"Codex permission mode changed to {mode}." if saved else "Send one task first so your account can be registered."
            if text == "/browser":
                return BotResponse(
                    "Browser and artifact tools\n\n"
                    "Codex runs the selected workspace's browser or Chrome Lab workflow, "
                    "verifies the requested page, and sends the resulting screenshot or "
                    "artifact back to this chat.",
                    [
                        [("📸 Capture & verify", "browser:screenshot")],
                        [("🧪 Run browser tests", "browser:test")],
                        [("📎 Find latest artifact", "browser:artifact")],
                        [("📁 Choose workspace", "nav:projects"), ("🏠 Home", "nav:home")],
                    ],
                )
            if text == "/browser screenshot":
                text = (
                    "Use the selected workspace's existing Chrome Lab or browser tooling. "
                    "Open the relevant application, verify its current UI and behavior, capture "
                    "a screenshot inside the workspace, then attach that image to Telegram using "
                    "the required telegram_file directive. Do not claim success unless the image "
                    "was produced and inspected."
                )
            elif text == "/browser test":
                text = (
                    "Run the selected workspace's relevant browser or end-to-end tests. Inspect "
                    "the result, diagnose any failure, and return the exact verification summary. "
                    "If the run creates a useful screenshot or report, attach it to Telegram."
                )
            elif text == "/browser artifact":
                text = (
                    "Find the newest relevant browser screenshot or test artifact in the selected "
                    "workspace, inspect it, explain what it demonstrates, and attach it to Telegram. "
                    "Do not modify application source files."
                )
            if text == "/review_menu":
                return BotResponse(
                    "Codex review tools operate on the selected workspace without changing files.",
                    [
                        [("🧾 Uncommitted diff", "cmd:diff")],
                        [("🔍 Working-tree review", "cmd:review")],
                        [("📁 Choose workspace", "nav:projects"), ("🏠 Home", "nav:home")],
                    ],
                )
            if text == "cmd:diff":
                text = "/diff"
            elif text == "cmd:review":
                text = "/review"
            if text in {"/codex", "/model"}:
                context = await jobs.active_context(user_id, chat.id)
                preferences = context[0].preferences_json if context else {}
                selected = str(preferences.get("codex_model", ""))
                effort = str(preferences.get("codex_reasoning_effort", ""))
                return BotResponse(
                    f"Codex model: {selected or settings.codex.model}\nReasoning: {effort or settings.codex.reasoning_effort}",
                    [[
                        (
                            f"{'✓ ' if (selected or settings.codex.model) == 'gpt-5.6-terra' else ''}Terra",
                            "config:model:gpt-5.6-terra",
                        ),
                        (
                            f"{'✓ ' if (selected or settings.codex.model) == 'gpt-5.6-sol' else ''}Sol",
                            "config:model:gpt-5.6-sol",
                        ),
                    ],
                     [("🧠 Reasoning", "nav:reasoning"), ("⚙️ Settings", "nav:settings")]],
                )
            if text.startswith("/codex model ") or text.startswith("/model "):
                model = text.split(maxsplit=2)[-1].strip()
                if not model or not model.startswith("gpt-"):
                    return "Invalid model name."
                return BotResponse(
                    f"Codex model changed to {model}. It applies to new and resumed turns.",
                    [[("🤖 Model settings", "nav:model"), ("📊 Status", "nav:home_status")]],
                ) if await jobs.set_user_preference(user_id, "codex_model", model) else "Send one task first so your account can be registered."
            if text == "/config":
                context = await jobs.active_context(user_id, chat.id)
                preferences = context[0].preferences_json if context else {}
                return BotResponse(
                    "Octopus / Codex settings:\n"
                    f"Model: {preferences.get('codex_model') or settings.codex.model}\n"
                    f"Reasoning: {preferences.get('codex_reasoning_effort') or settings.codex.reasoning_effort}\n"
                    f"Response language: {preferences.get('response_language') or settings.app.language}\n"
                    f"Permissions: {preferences.get('sandbox_mode') or settings.codex.sandbox_mode}\n"
                    f"Live logs: {preferences.get('log_level') or 'info'}",
                    [[("🤖 Model", "nav:model"), ("🧠 Reasoning", "nav:reasoning")],
                     [("🌐 Language", "nav:language")],
                     [("🔐 Permissions", "nav:permissions"), ("📜 Logs", "nav:logs")],
                     [("🏠 Home", "nav:home")]],
                )
            if text.startswith("/config model "):
                model = text.removeprefix("/config model ").strip()
                if not model.startswith("gpt-"):
                    return "Invalid model name."
                return BotResponse(
                    f"Codex model changed to {model}. It applies to new and resumed turns.",
                    [[("🤖 Model settings", "nav:model"), ("📊 Status", "nav:home_status")]],
                ) if await jobs.set_user_preference(user_id, "codex_model", model) else "Send one task first."
            if text.startswith("/config effort ") or text.startswith("/reasoning "):
                effort = text.split()[-1].strip().casefold()
                if effort not in {"low", "medium", "high", "xhigh", "max", "ultra"}:
                    return "Invalid reasoning effort."
                return BotResponse(
                    f"Reasoning effort changed to {effort}.",
                    [[("🧠 Reasoning settings", "nav:reasoning"), ("📊 Status", "nav:home_status")]],
                ) if await jobs.set_user_preference(user_id, "codex_reasoning_effort", effort) else "Send one task first."
            if text == "/reasoning":
                context = await jobs.active_context(user_id, chat.id)
                preferences = context[0].preferences_json if context else {}
                current = str(
                    preferences.get("codex_reasoning_effort")
                    or settings.codex.reasoning_effort
                )
                return BotResponse(
                    f"Choose Codex reasoning effort.\nCurrent: {current}",
                    [[
                        (f"{'✓ ' if current == 'low' else ''}Low", "config:effort:low"),
                        (f"{'✓ ' if current == 'medium' else ''}Medium", "config:effort:medium"),
                    ],
                     [
                         (f"{'✓ ' if current == 'high' else ''}High", "config:effort:high"),
                         (f"{'✓ ' if current == 'xhigh' else ''}XHigh", "config:effort:xhigh"),
                     ],
                     [
                         (f"{'✓ ' if current == 'max' else ''}Max", "config:effort:max"),
                         (f"{'✓ ' if current == 'ultra' else ''}Ultra", "config:effort:ultra"),
                     ],
                     [("🤖 Model", "nav:model"), ("⚙️ Settings", "nav:settings")]],
                )
            if text == "/language":
                context = await jobs.active_context(user_id, chat.id)
                preferences = context[0].preferences_json if context else {}
                current = str(
                    preferences.get("response_language")
                    or settings.app.language
                )
                return BotResponse(
                    "Choose the agent language for voice transcription and AI responses.\n"
                    f"Current: {'English' if current == 'en' else 'Persian'}\n"
                    "The control interface itself remains English.",
                    [[
                        (f"{'✓ ' if current == 'en' else ''}English", "config:language:en"),
                        (f"{'✓ ' if current == 'fa' else ''}Persian", "config:language:fa"),
                    ],
                     [("⚙️ Settings", "nav:settings"), ("📊 Status", "nav:home_status")]],
                )
            if text.startswith("/config language "):
                language = text.removeprefix("/config language ").strip().casefold()
                if language not in {"en", "fa"}:
                    return "Language must be en or fa."
                saved = await jobs.set_user_preferences(
                    user_id,
                    {
                        "response_language": language,
                        "input_language": language,
                    },
                )
                label = "English" if language == "en" else "Persian"
                return BotResponse(
                    f"Input and response language changed to {label}.",
                    [[("🌐 Language settings", "nav:language"), ("📊 Status", "nav:home_status")]],
                ) if saved else "Send one task first."
            if text.startswith("/config progress "):
                value = text.removeprefix("/config progress ").strip().casefold()
                if value not in {"on", "off"}:
                    return "The value must be on or off."
                return "Live progress setting saved." if await jobs.set_user_preference(user_id, "stream_progress", value == "on") else "Send one task first."
            if text == "/diff":
                text = "Inspect all uncommitted changes in the selected workspace. Show a precise diff summary, risks, and verification gaps. Do not modify files."
            elif text == "/review":
                text = "Review the selected workspace working tree like Codex CLI /review. Inspect uncommitted changes, identify concrete bugs and regressions, and report findings in priority order. Do not modify files."
            context = await jobs.active_context(user_id, chat.id)
            memory = MemoryService(jobs.sessions)
            if text.startswith("/remember "):
                if context is None:
                    return "Send a normal message first to create a conversation."
                content = text.removeprefix("/remember ").strip()
                memory_id = await memory.remember(
                    context[0].id,
                    content,
                    conversation_id=context[1].id,
                    project_id=context[1].project_id,
                )
                return f"Memory saved: {memory_id}"
            if text == "/memory":
                if context is None:
                    return "This conversation has no saved memory."
                rows = await memory.list(context[0].id)
                return "\n".join(f"• {row.id}: {row.content[:140]}" for row in rows) or "No memories were saved."
            if text.startswith("/forget "):
                if context is None:
                    return "The memory identifier is invalid."
                memory_id = text.removeprefix("/forget ").strip()
                return "Memory deleted." if await memory.forget(context[0].id, memory_id) else "Memory not found."
            objective, content_type, metadata = await extract_bot_media(message, settings)
            natural_project = re.search(
                r"project\s+([A-Za-z0-9_-]+)",
                objective or text,
                flags=re.IGNORECASE,
            )
            if natural_project:
                await jobs.select_project(user_id, chat.id, natural_project.group(1).casefold())
            job_id = await jobs.create_from_text(
                user_id,
                chat.id,
                objective or text or "[empty message]",
                content_type=content_type or "text",
                metadata=metadata,
            )
            return f"Request queued and processing. Job ID: {job_id}"

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
