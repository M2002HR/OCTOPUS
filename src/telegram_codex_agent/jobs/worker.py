from __future__ import annotations

import asyncio
import base64
import logging
import re
import socket
from pathlib import Path
from time import monotonic
from typing import Any

from redis.asyncio import Redis, from_url
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from telegram_codex_agent.core.config import CodexConfig, Settings
from telegram_codex_agent.core.errors import AjilUnavailableError
from telegram_codex_agent.db.models import (
    ApprovalRecord,
    Chat,
    CodexThread,
    Conversation,
    Job,
    JobEventRow,
    MemoryRecord,
    Message,
    Project,
)
from telegram_codex_agent.db.repositories import JobRepository
from telegram_codex_agent.db.session import create_engine, create_session_factory
from telegram_codex_agent.integrations.ajil import AjilClient
from telegram_codex_agent.integrations.codex import (
    CodexAppServer,
    CodexProtocolError,
    CodexThreadHandle,
)
from telegram_codex_agent.jobs.models import (
    ExecutionPlan,
    ExecutionTarget,
    IntentType,
    JobState,
    PlannedStep,
    utcnow,
)
from telegram_codex_agent.jobs.queue import RedisStreamJobQueue
from telegram_codex_agent.memory import MemoryService
from telegram_codex_agent.projects import ProjectRegistry

logger = logging.getLogger(__name__)
_TELEGRAM_FILE_DIRECTIVE = re.compile(r"\[\[telegram_file:([^\]\n]+)\]\]")


class Worker:
    """Durable job executor with PostgreSQL leases and cancellable Codex turns."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.worker_id = f"{socket.gethostname()}-{id(self):x}"
        self.engine = create_engine(settings.database)
        self.sessions = create_session_factory(self.engine)
        self.redis: Redis = from_url(settings.redis.url, decode_responses=True)
        self.queue = RedisStreamJobQueue(self.redis, settings.redis.stream, settings.redis.consumer_group)
        self.stop_event = asyncio.Event()

    async def run(self) -> None:
        await ProjectRegistry(self.sessions, self.settings.projects, self.settings.workspace).sync()
        await self.queue.initialize()
        async for message_id, job_id in self.queue.consume(
            self.worker_id,
            stale_idle_ms=max(1_000, self.settings.jobs.lease_seconds * 1_000),
        ):
            try:
                if await self._process(job_id):
                    await self.queue.acknowledge(message_id)
            except Exception:
                logger.exception("worker failed job", extra={"job_id": job_id})

    async def close(self) -> None:
        await self.redis.aclose()
        await self.engine.dispose()

    async def _process(self, job_id: str) -> bool:
        """Claim before work; stale duplicate stream deliveries become harmless no-ops."""
        async with self.sessions() as session:
            repository = JobRepository(session)
            job = await session.get(Job, job_id, with_for_update=True)
            if job is None:
                return True
            if job.state in {
                JobState.COMPLETED.value,
                JobState.FAILED.value,
                JobState.CANCELLED.value,
                JobState.INTERRUPTED.value,
            }:
                return True
            if job.state == JobState.CANCEL_REQUESTED.value:
                await self._transition(session, job, JobState.CANCELLED, "cancelled before execution")
                await session.commit()
                return True
            if job.state == JobState.RECEIVED.value:  # compatibility with jobs written before v0.2
                await self._transition(session, job, JobState.NORMALIZING, "normalizing legacy request")
            else:
                previous_state = job.state
                claimed = await repository.claim(job_id, self.worker_id, self.settings.jobs.lease_seconds)
                if not claimed:
                    return False
                if previous_state not in {
                    JobState.QUEUED.value,
                    JobState.RECOVERING.value,
                }:
                    await self._transition(
                        session,
                        job,
                        JobState.RECOVERING,
                        "recovering work after an expired worker lease",
                        {"previous_state": previous_state},
                    )
                await self._transition(session, job, JobState.NORMALIZING, "normalizing request")
            await session.commit()

        try:
            await self._deliver_progress(job_id, "📥 Job claimed by the Octopus worker.")
            plan, conversation_id, project_path = await self._prepare(job_id)
            await self._deliver_progress(
                job_id,
                f"🧭 Context resolved and execution plan selected: {plan.primary_executor.value}.",
            )
            content = await self._execute(job_id, plan, project_path)
            await self._deliver_progress(job_id, "✅ Executor finished; persisting and delivering the result.")
            await self._complete(job_id, conversation_id, content)
        except _Cancelled:
            await self._cancel(job_id, "cancelled while executing")
        except Exception as exc:
            logger.exception("job execution failed", extra={"job_id": job_id})
            await self._fail(job_id, exc)
        return True

    async def _prepare(self, job_id: str) -> tuple[ExecutionPlan, str, Path | None]:
        async with self.sessions() as session:
            job = await session.get(Job, job_id, with_for_update=True)
            if job is None:
                raise KeyError(job_id)
            await self._raise_if_cancelled(session, job)
            await self._transition(session, job, JobState.CONTEXT_RESOLUTION, "resolving conversation and project context")
            project_path: Path | None = None
            if job.project_id:
                project = await session.get(Project, job.project_id)
                if project is None or not project.is_active:
                    raise ValueError("selected project is unavailable")
                project_path = Path(project.root_path).resolve()
                if not project_path.is_dir():
                    raise ValueError("selected project root is unavailable on this host")
            await self._transition(session, job, JobState.MEMORY_RETRIEVAL, "retrieving relevant memory")
            if str(job.metadata_json.get("attachment_kind", "")) == "voice":
                await self._transition(session, job, JobState.WAITING_EXTERNAL, "transcribing voice attachment")
                job.objective = await self._transcribe_attachment(job)
                await self._event_in_session(
                    session,
                    job.id,
                    "attachment.voice.transcribed",
                    "voice attachment transcribed",
                    {"chars": len(job.objective)},
                )
            conversation = await session.get(Conversation, job.conversation_id)
            if conversation is not None and self.settings.memory.enabled:
                memories = await MemoryService(self.sessions).retrieve(
                    conversation.user_id,
                    job.objective,
                    conversation_id=job.conversation_id,
                    project_id=job.project_id,
                    limit=self.settings.memory.retrieval_limit,
                )
                job.metadata_json = {
                    **job.metadata_json,
                    "memory_context": [row.content[:1000] for row in memories],
                }
            await self._transition(session, job, JobState.CLASSIFYING, "classifying requested work")
            intent = self._classify(job.objective)
            job.intent = intent.value
            await self._transition(session, job, JobState.PLANNING, "building deterministic execution plan")
            plan = self._plan(job.objective, intent, bool(project_path))
            job.planner_output_json = plan.model_dump(mode="json")
            job.verification_policy_json = plan.verification.model_dump(mode="json")
            await self._transition(session, job, JobState.PLANNED, "plan persisted", {"executor": plan.primary_executor.value})
            await self._transition(session, job, JobState.RUNNING, "starting executor")
            await session.commit()
            return plan, job.conversation_id, project_path

    async def _execute(self, job_id: str, plan: ExecutionPlan, project_path: Path | None) -> str:
        if plan.primary_executor == ExecutionTarget.CODEX:
            if project_path is None:
                return "Select a registered workspace before running Codex."
            return await self._execute_codex(job_id, project_path)
        if plan.primary_executor == ExecutionTarget.NONE:
            return "Open /projects and select a workspace with /project <slug> first."
        await self._deliver_progress(job_id, "🧠 Ajil is handling the direct conversational step.")
        return await self._execute_chat(job_id)

    async def _execute_chat(self, job_id: str) -> str:
        objective = await self._objective(job_id)
        language = await self._response_language(job_id)
        attachment = await self._attachment_metadata(job_id)
        client = AjilClient(self.settings.ajil)
        try:
            user_content: object = objective
            if attachment.get("attachment_kind") == "photo":
                image_path = Path(str(attachment.get("attachment_path", "")))
                if not image_path.is_file():
                    raise RuntimeError("photo attachment is no longer available")
                encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
                mime_type = str(attachment.get("attachment_mime_type") or "image/jpeg")
                user_content = [
                    {"type": "text", "text": objective},
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{encoded}"}},
                ]
            response = await client.chat(
                [
                    {
                        "role": "system",
                        "content": (
                            "You are a helpful assistant. Reply in English."
                            if language == "en"
                            else "You are a helpful assistant. Reply in Persian unless the user asks for another language."
                        ),
                    },
                    {"role": "user", "content": user_content},
                ]
            )
            return client._content(response.data)
        except (AjilUnavailableError, ValueError) as exc:
            raise RuntimeError(f"Ajil chat execution failed: {exc}") from exc
        finally:
            await client.aclose()

    async def _execute_codex(self, job_id: str, project_path: Path) -> str:
        objective = await self._objective(job_id)
        codex_config = await self._codex_config(job_id)
        response_language = await self._response_language(job_id)
        last_activity_delivery = 0.0

        async def event(method: str, params: dict[str, Any]) -> None:
            nonlocal last_activity_delivery
            if method == "turn/started":
                turn = params.get("turn") or {}
                await self._record_codex_ids(job_id, str(params.get("threadId", "")), str(turn.get("id", "")))
            if method in {"turn/completed", "error"}:
                await self._event(job_id, f"codex.{method.replace('/', '.')}", "Codex event received")
            activity = self._codex_activity(method, params)
            if activity:
                await self._event(job_id, "codex.activity", activity, {"source_event": method})
                now = monotonic()
                if now - last_activity_delivery >= self.settings.telegram.progress_edit_interval_seconds:
                    last_activity_delivery = now
                    await self._deliver_progress(job_id, f"🔎 {activity}")

        async with CodexAppServer(
            codex_config,
            on_event=event,
            approval_decider=lambda method, params: self._decide_approval(job_id, method, params),
        ) as codex:
            saved_thread = await self._resumable_thread(job_id)
            if saved_thread is not None:
                try:
                    thread = await codex.resume_thread(saved_thread.codex_thread_id, project_path)
                    await self._event(
                        job_id,
                        "codex.thread.resumed",
                        "Codex thread resumed",
                        {"thread_id": thread.id},
                    )
                    await self._deliver_progress(
                        job_id,
                        "↩️ Codex resumed the existing session for this workspace.",
                    )
                except CodexProtocolError:
                    logger.warning(
                        "persisted Codex thread could not be resumed; starting a new thread",
                        extra={"job_id": job_id, "thread_id": saved_thread.codex_thread_id},
                    )
                    thread = await codex.start_thread(project_path)
            else:
                thread = await codex.start_thread(project_path)
            await self._record_codex_thread(job_id, thread)
            task = asyncio.create_task(
                codex.run_turn(
                    thread,
                    self._codex_prompt(objective, project_path, response_language),
                    timeout=float(self.settings.jobs.step_timeout_seconds),
                )
            )
            while not task.done():
                done, _ = await asyncio.wait({task}, timeout=self.settings.jobs.heartbeat_seconds)
                if done:
                    break
                if await self._cancel_requested(job_id):
                    for thread_id, turn_id in codex.active_turns.values():
                        await codex.interrupt(thread_id, turn_id)
                    try:
                        await task
                    except CodexProtocolError:
                        pass
                    raise _Cancelled()
                await self._heartbeat(job_id)
            result = await task
        if result.status != "completed":
            raise RuntimeError(result.error or f"Codex turn ended with {result.status}")
        if not result.text:
            raise RuntimeError("Codex completed without a final response")
        return result.text

    async def _complete(self, job_id: str, conversation_id: str, content: str) -> None:
        telegram_chat_id: int | None = None
        deliverables: list[Path] = []
        async with self.sessions() as session:
            job = await session.get(Job, job_id, with_for_update=True)
            if job is None:
                return
            if job.state == JobState.CANCEL_REQUESTED.value:
                await self._transition(session, job, JobState.CANCELLED, "cancelled before report")
            else:
                roots = [Path(self.settings.artifacts.root).resolve()]
                if job.project_id:
                    project = await session.get(Project, job.project_id)
                    if project:
                        roots.append(Path(project.root_path).resolve())
                content, deliverables = self._extract_deliverables(content, roots)
                session.add(Message(conversation_id=conversation_id, role="assistant", content_type="text", text=content))
                job.result_summary = content
                await self._transition(session, job, JobState.REPORTING, "reporting result")
                await self._transition(session, job, JobState.COMPLETED, "completed")
                conversation = await session.get(Conversation, conversation_id)
                if conversation is not None:
                    chat = await session.get(Chat, conversation.chat_id)
                    telegram_chat_id = chat.telegram_chat_id if chat else None
                    if self.settings.memory.enabled:
                        session.add(
                            MemoryRecord(
                                user_id=conversation.user_id,
                                conversation_id=conversation.id,
                                project_id=job.project_id,
                                memory_type="outcome",
                                title="job outcome",
                                content=f"Objective: {job.objective}\nResult: {content}"[:20_000],
                                importance=35,
                            )
                        )
            await session.commit()
        if telegram_chat_id is not None:
            await self._deliver(telegram_chat_id, content)
            for path in deliverables:
                await self._deliver_file(telegram_chat_id, path)

    async def _deliver(self, telegram_chat_id: int, content: str) -> None:
        """Best-effort Bot API delivery. Database completion remains authoritative."""
        if not self.settings.telegram.bot_token:
            return
        try:
            from aiogram import Bot

            from telegram_codex_agent.telegram.bot import HttpProxyAiohttpSession
            from telegram_codex_agent.telegram.formatting import as_html, split_telegram_text

            bot = Bot(
                self.settings.telegram.bot_token,
                session=HttpProxyAiohttpSession(self.settings.telegram.bot_proxy_url)
                if self.settings.telegram.bot_proxy_url
                else None,
            )
            try:
                for chunk in split_telegram_text(as_html(content), self.settings.telegram.max_message_length):
                    await bot.send_message(telegram_chat_id, chunk)
            finally:
                await bot.session.close()
        except Exception as exc:
            from aiogram.exceptions import TelegramBadRequest

            if isinstance(exc, TelegramBadRequest):
                logger.warning(
                    "Telegram rejected delivery to an unavailable chat",
                    extra={"job_chat_id": telegram_chat_id},
                )
                return
            logger.exception("failed to deliver completed job to Telegram", extra={"job_chat_id": telegram_chat_id})

    async def _deliver_file(self, telegram_chat_id: int, path: Path) -> None:
        if not self.settings.telegram.bot_token:
            return
        try:
            from aiogram import Bot
            from aiogram.types import FSInputFile

            from telegram_codex_agent.telegram.bot import HttpProxyAiohttpSession

            bot = Bot(
                self.settings.telegram.bot_token,
                session=HttpProxyAiohttpSession(self.settings.telegram.bot_proxy_url)
                if self.settings.telegram.bot_proxy_url
                else None,
            )
            try:
                upload = FSInputFile(path)
                if path.suffix.casefold() in {".png", ".jpg", ".jpeg", ".webp"}:
                    await bot.send_photo(telegram_chat_id, upload, caption=f"Artifact: {path.name}")
                else:
                    await bot.send_document(telegram_chat_id, upload, caption=f"Artifact: {path.name}")
            finally:
                await bot.session.close()
        except Exception as exc:
            from aiogram.exceptions import TelegramBadRequest

            if isinstance(exc, TelegramBadRequest):
                logger.warning(
                    "Telegram rejected artifact delivery to an unavailable chat",
                    extra={"job_chat_id": telegram_chat_id, "artifact_name": path.name},
                )
                return
            logger.exception(
                "failed to deliver job artifact to Telegram",
                extra={"job_chat_id": telegram_chat_id, "artifact_name": path.name},
            )

    def _extract_deliverables(self, content: str, roots: list[Path]) -> tuple[str, list[Path]]:
        deliverables: list[Path] = []
        for raw_path in _TELEGRAM_FILE_DIRECTIVE.findall(content):
            candidate = Path(raw_path.strip()).resolve()
            if (
                candidate.is_file()
                and candidate.stat().st_size <= self.settings.artifacts.telegram_direct_upload_max_bytes
                and any(candidate.is_relative_to(root) for root in roots)
            ):
                deliverables.append(candidate)
        clean = _TELEGRAM_FILE_DIRECTIVE.sub("", content).strip()
        return clean or "Task completed; requested artifacts are attached.", deliverables

    async def _deliver_progress(self, job_id: str, content: str) -> None:
        """Publish safe lifecycle updates while a Codex turn is running.

        The database event trail is the source of truth; Telegram delivery is
        deliberately best-effort so a transient proxy failure cannot affect
        the job itself.
        """
        async with self.sessions() as session:
            job = await session.get(Job, job_id)
            if job is None or not bool(job.metadata_json.get("stream_progress", True)):
                return
            configured_level = str(job.metadata_json.get("log_level", "info")).casefold()
            if configured_level in {"off", "error", "warning"}:
                return
            conversation = await session.get(Conversation, job.conversation_id)
            chat = await session.get(Chat, conversation.chat_id) if conversation else None
            telegram_chat_id = chat.telegram_chat_id if chat else None
        if telegram_chat_id is not None:
            await self._deliver(telegram_chat_id, content)

    async def _cancel(self, job_id: str, message: str) -> None:
        async with self.sessions() as session:
            job = await session.get(Job, job_id, with_for_update=True)
            if job and job.state not in {JobState.CANCELLED.value, JobState.COMPLETED.value}:
                if job.state != JobState.CANCEL_REQUESTED.value:
                    job.state = JobState.CANCEL_REQUESTED.value
                await self._transition(session, job, JobState.CANCELLED, message)
                await session.commit()

    async def _fail(self, job_id: str, exc: Exception) -> None:
        telegram_chat_id: int | None = None
        async with self.sessions() as session:
            job = await session.get(Job, job_id, with_for_update=True)
            if job is None:
                return
            if job.state == JobState.CANCEL_REQUESTED.value:
                await self._transition(session, job, JobState.CANCELLED, "cancelled after executor error")
            elif job.state not in {JobState.COMPLETED.value, JobState.CANCELLED.value, JobState.FAILED.value}:
                job.error_code = type(exc).__name__
                job.error_message = str(exc)[:8000]
                await self._transition(session, job, JobState.FAILED, "execution failed", {"error": str(exc)[:1000]})
                conversation = await session.get(Conversation, job.conversation_id)
                if conversation is not None:
                    chat = await session.get(Chat, conversation.chat_id)
                    telegram_chat_id = chat.telegram_chat_id if chat else None
            await session.commit()
        if telegram_chat_id is not None:
            await self._deliver(
                telegram_chat_id,
                f"The task could not be completed. Use /logs {job_id} for its safe lifecycle log.",
            )

    async def _objective(self, job_id: str) -> str:
        async with self.sessions() as session:
            job = await session.get(Job, job_id)
            if job is None:
                raise KeyError(job_id)
            return job.objective

    async def _attachment_metadata(self, job_id: str) -> dict[str, object]:
        async with self.sessions() as session:
            job = await session.get(Job, job_id)
            return dict(job.metadata_json) if job else {}

    async def _resumable_thread(self, job_id: str) -> CodexThread | None:
        async with self.sessions() as session:
            job = await session.get(Job, job_id)
            if job is None:
                return None
            return await session.scalar(
                select(CodexThread)
                .where(
                    CodexThread.conversation_id == job.conversation_id,
                    CodexThread.project_id == job.project_id,
                    CodexThread.status == "active",
                )
                .order_by(CodexThread.updated_at.desc())
            )

    async def _transcribe_attachment(self, job: Job) -> str:
        path = Path(str(job.metadata_json.get("attachment_path", ""))).resolve()
        artifact_root = Path(self.settings.artifacts.root).resolve()
        if not path.is_file() or not path.is_relative_to(artifact_root):
            raise RuntimeError("voice attachment path is unavailable or outside the artifact root")
        client = AjilClient(self.settings.ajil)
        try:
            response = await client.transcribe(path, language=self.settings.voice.stt_language)
            transcript = str(response.data.get("text", "")).strip()
            if not transcript:
                raise RuntimeError("transcription returned no text")
            return transcript
        finally:
            await client.aclose()

    async def _codex_config(self, job_id: str) -> CodexConfig:
        async with self.sessions() as session:
            job = await session.get(Job, job_id)
            metadata = job.metadata_json if job else {}
            requested_model = str(metadata.get("codex_model", "")).strip()
            requested_effort = str(metadata.get("codex_reasoning_effort", "")).strip()
            requested_sandbox = str(metadata.get("sandbox_mode", "")).strip()
            requested_approval = str(metadata.get("approval_policy", "")).strip()
            updates: dict[str, object] = {
                "model": requested_model or self.settings.codex.model,
                "reasoning_effort": requested_effort or self.settings.codex.reasoning_effort,
            }
            if requested_sandbox in {"read-only", "workspace-write", "danger-full-access"}:
                updates["sandbox_mode"] = requested_sandbox
            if requested_approval in {"never", "on-request", "untrusted"}:
                updates["approval_policy"] = requested_approval
            return self.settings.codex.model_copy(
                update=updates
            )

    async def _response_language(self, job_id: str) -> str:
        async with self.sessions() as session:
            job = await session.get(Job, job_id)
            configured = str((job.metadata_json if job else {}).get("response_language", "")).casefold()
            return configured if configured in {"fa", "en"} else self.settings.app.language

    async def _cancel_requested(self, job_id: str) -> bool:
        async with self.sessions() as session:
            job = await session.get(Job, job_id)
            return job is None or job.state == JobState.CANCEL_REQUESTED.value

    async def _raise_if_cancelled(self, session: AsyncSession, job: Job) -> None:
        if job.state == JobState.CANCEL_REQUESTED.value:
            await self._transition(session, job, JobState.CANCELLED, "cancelled before planning")
            await session.commit()
            raise _Cancelled()

    async def _heartbeat(self, job_id: str) -> None:
        async with self.sessions() as session:
            repository = JobRepository(session)
            if await repository.heartbeat(job_id, self.worker_id, self.settings.jobs.lease_seconds):
                await self._event_in_session(session, job_id, "job.heartbeat", "worker lease renewed")
                await session.commit()

    async def _record_codex_thread(self, job_id: str, thread: CodexThreadHandle) -> None:
        async with self.sessions() as session:
            job = await session.get(Job, job_id, with_for_update=True)
            if job is None:
                return
            job.codex_thread_id = thread.id
            existing = await session.scalar(
                select(CodexThread).where(CodexThread.codex_thread_id == thread.id)
            )
            if existing is None:
                conversation = await session.get(Conversation, job.conversation_id)
                if conversation is not None:
                    session.add(
                        CodexThread(
                            user_id=conversation.user_id,
                            conversation_id=job.conversation_id,
                            project_id=job.project_id,
                            codex_thread_id=thread.id,
                            cwd=thread.cwd,
                            model=thread.model,
                            approval_policy=self.settings.codex.approval_policy,
                            sandbox_mode=self.settings.codex.sandbox_mode,
                        )
                    )
            await self._event_in_session(session, job_id, "codex.thread.started", "Codex thread started", {"thread_id": thread.id})
            await session.commit()
        await self._deliver_progress(job_id, "⌛ Codex started a workspace session. I will send the verified result here.")

    async def _record_codex_ids(self, job_id: str, thread_id: str, turn_id: str) -> None:
        if not turn_id:
            return
        async with self.sessions() as session:
            job = await session.get(Job, job_id, with_for_update=True)
            if job:
                job.codex_thread_id = thread_id or job.codex_thread_id
                job.codex_turn_id = turn_id
                await self._event_in_session(session, job_id, "codex.turn.started", "Codex turn started", {"turn_id": turn_id})
                await session.commit()
        await self._deliver_progress(job_id, "🛠 Codex is working on the requested task now.")

    async def _decide_approval(self, job_id: str, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Persist every unexpected privilege request before returning a safe denial.

        Jobs use Codex's ``never`` approval policy by default.  If a future
        Codex version still asks, the request is auditable and cannot gain a
        broad filesystem or network grant merely because it originated in a
        Telegram message.
        """
        if method == "item/permissions/requestApproval":
            response: dict[str, Any] = {"permissions": {"fileSystem": None, "network": None}, "scope": "turn"}
            decision = "deny_permissions"
        else:
            response = {"decision": "decline" if method in {"item/commandExecution/requestApproval", "item/fileChange/requestApproval"} else "cancel"}
            decision = response["decision"]
        async with self.sessions() as session:
            session.add(
                ApprovalRecord(
                    job_id=job_id,
                    codex_request_id=str(params.get("approvalId") or params.get("itemId") or "unknown"),
                    approval_type=method,
                    request_json=params,
                    decision=decision,
                    scope="turn",
                    auto_approved=False,
                )
            )
            await self._event_in_session(session, job_id, "codex.approval.denied", "Codex approval request denied by project policy", {"method": method})
            await session.commit()
        return response

    async def _event(self, job_id: str, event_type: str, message: str, data: dict[str, object] | None = None) -> None:
        async with self.sessions() as session:
            await self._event_in_session(session, job_id, event_type, message, data)
            await session.commit()

    @staticmethod
    async def _event_in_session(session: AsyncSession, job_id: str, event_type: str, message: str, data: dict[str, object] | None = None) -> None:
        sequences = await session.scalars(select(JobEventRow.sequence).where(JobEventRow.job_id == job_id))
        session.add(JobEventRow(job_id=job_id, sequence=max(sequences, default=0) + 1, event_type=event_type, level="info", message=message, data_json=data or {}))

    @classmethod
    async def _transition(cls, session: AsyncSession, job: Job, target: JobState, message: str, data: dict[str, object] | None = None) -> None:
        job.state = target.value
        if target == JobState.RUNNING and job.started_at is None:
            job.started_at = utcnow()
        elif target in {JobState.COMPLETED, JobState.FAILED}:
            job.completed_at = utcnow()
        elif target == JobState.CANCELLED:
            job.cancelled_at = utcnow()
        await cls._event_in_session(session, job.id, f"job.{target.value}", message, data)

    @staticmethod
    def _classify(text: str) -> IntentType:
        lowered = text.casefold()
        code_words = (
            "code", "repo", "project", "implement", "fix", "test", "bug",
            "docker", "container", "service", "system", "shell", "terminal", "log", "git",
        )
        return IntentType.CODE_TASK if any(word in lowered for word in code_words) else IntentType.CHAT

    @staticmethod
    def _codex_activity(method: str, params: dict[str, Any]) -> str:
        """Map App Server events to a safe user-visible activity summary.

        We deliberately do not forward private reasoning, raw command strings,
        file contents, or process output: those may contain credentials.  The
        durable event log keeps the event type for diagnosis while Telegram
        receives only an operational status summary.
        """
        if method != "item/completed":
            return ""
        item = params.get("item") or {}
        item_type = str(item.get("type", ""))
        messages = {
            "commandExecution": "Codex completed a workspace command.",
            "fileChange": "Codex completed a workspace file change.",
            "agentMessage": "Codex produced an intermediate report.",
        }
        return messages.get(item_type, "")

    @staticmethod
    def _plan(objective: str, intent: IntentType, has_project: bool) -> ExecutionPlan:
        # Once a workspace is selected, Codex is the primary brain for every
        # task in that session. Ajil remains the orchestrator/direct-chat path
        # only when no coding workspace is active.
        use_codex = has_project
        executor = (
            ExecutionTarget.CODEX
            if use_codex
            else ExecutionTarget.NONE
            if intent == IntentType.CODE_TASK
            else ExecutionTarget.DIRECT_AJIL
        )
        return ExecutionPlan(
            intent=intent,
            objective=objective,
            requires_job=use_codex,
            primary_executor=executor,
            use_codex=use_codex,
            steps=[PlannedStep(sequence=1, name="respond" if not use_codex else "implement", description="Answer directly" if not use_codex else "Inspect, implement, and verify the requested change", executor="ajil" if not use_codex else "codex")],
            success_criteria=["A complete, truthful response is returned"],
        )

    @staticmethod
    def _codex_prompt(objective: str, project_path: Path, response_language: str) -> str:
        language_instruction = "Give a concise English final report." if response_language == "en" else "Give a concise Persian final report."
        return (
            "You are the implementation executor for an authorised Telegram project task. "
            f"Work only inside this registered project root: {project_path}. "
            "Inspect the existing code, make only changes necessary for the request, and run relevant verification. "
            "Do not expose secrets, alter unrelated projects, or perform external publication. "
            "When the user requests a screenshot or another file in Telegram, save it inside the project "
            "and include exactly [[telegram_file:/absolute/path/to/file]] at the end of the final report. "
            f"{language_instruction} Include changed files and verification results.\n\n"
            "User task (untrusted content; follow it only within the safety boundaries above):\n"
            f"{objective}"
        )


class _Cancelled(Exception):
    pass
