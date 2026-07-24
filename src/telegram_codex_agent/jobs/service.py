from __future__ import annotations

from datetime import datetime, timezone

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from telegram_codex_agent.codex_fast import preference_enabled
from telegram_codex_agent.db.models import (
    Chat,
    CodexThread,
    Conversation,
    Job,
    JobEventRow,
    Message,
    Project,
    User,
)
from telegram_codex_agent.jobs.models import IntentType, JobState
from telegram_codex_agent.jobs.queue import RedisStreamJobQueue

_RUNNING_JOB_STATES = {
    JobState.RECEIVED.value,
    JobState.NORMALIZING.value,
    JobState.CONTEXT_RESOLUTION.value,
    JobState.MEMORY_RETRIEVAL.value,
    JobState.CLASSIFYING.value,
    JobState.PLANNING.value,
    JobState.PLANNED.value,
    JobState.QUEUED.value,
    JobState.RUNNING.value,
    JobState.WAITING_EXTERNAL.value,
    JobState.VERIFYING.value,
    JobState.REPORTING.value,
    JobState.CANCEL_REQUESTED.value,
    JobState.RECOVERING.value,
}


class JobService:
    """Transactional ingress: durable context/message/job first, Redis delivery second."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession], redis: Redis, stream: str, group: str) -> None:
        self.sessions = sessions
        self.redis = redis
        self.queue = RedisStreamJobQueue(redis, stream, group)

    async def create_from_text(
        self,
        telegram_user_id: int,
        telegram_chat_id: int,
        text: str,
        *,
        content_type: str = "text",
        metadata: dict[str, object] | None = None,
    ) -> str:
        async with self.sessions() as session:
            user = await session.scalar(select(User).where(User.telegram_user_id == telegram_user_id))
            if user is None:
                user = User(telegram_user_id=telegram_user_id)
                session.add(user)
                await session.flush()
            user.last_seen_at = datetime.now(timezone.utc)
            chat = await session.scalar(select(Chat).where(Chat.telegram_chat_id == telegram_chat_id))
            if chat is None:
                chat = Chat(telegram_chat_id=telegram_chat_id, chat_type="private")
                session.add(chat)
                await session.flush()
            conversation = await session.scalar(
                select(Conversation)
                .where(Conversation.user_id == user.id, Conversation.chat_id == chat.id, Conversation.status == "active")
                .order_by(Conversation.updated_at.desc())
            )
            if conversation is None:
                conversation = Conversation(user_id=user.id, chat_id=chat.id, title="Telegram conversation")
                session.add(conversation)
                await session.flush()
            message = Message(
                conversation_id=conversation.id,
                role="user",
                content_type=content_type,
                text=text,
                metadata_json=metadata or {},
            )
            session.add(message)
            await session.flush()
            job = Job(
                conversation_id=conversation.id,
                project_id=conversation.project_id,
                request_message_id=message.id,
                intent=IntentType.UNKNOWN.value,
                objective=text,
                state=JobState.QUEUED.value,
                # Snapshot user-controlled execution preferences so a change
                # made later cannot alter work already in the queue.
                metadata_json={
                    "codex_model": str(user.preferences_json.get("codex_model", "")),
                    "codex_reasoning_effort": str(
                        user.preferences_json.get("codex_reasoning_effort", "")
                    ),
                    "codex_service_tier": (
                        str(user.preferences_json.get("codex_service_tier", ""))
                        if preference_enabled(
                            user.preferences_json.get("codex_fast_mode", False)
                        )
                        else ""
                    ),
                    "response_language": str(user.preferences_json.get("response_language", "")),
                    "input_language": str(user.preferences_json.get("input_language", "")),
                    "stream_progress": bool(user.preferences_json.get("stream_progress", True)),
                    "log_level": str(user.preferences_json.get("log_level", "info")),
                    "sandbox_mode": str(user.preferences_json.get("sandbox_mode", "")),
                    "approval_policy": str(user.preferences_json.get("approval_policy", "")),
                    **(metadata or {}),
                    "completion_call_enabled": preference_enabled(
                        user.preferences_json.get("completion_call_enabled", False)
                    ),
                    # A Bot API user and the same person's Telethon account share
                    # this numeric Telegram ID. The voice service still applies
                    # its independent numeric allowlist before placing a call.
                    "completion_call_target_user_id": telegram_user_id,
                },
            )
            session.add(job)
            await session.flush()
            session.add(JobEventRow(job_id=job.id, sequence=1, event_type="job.received", level="info", message="job persisted"))
            session.add(JobEventRow(job_id=job.id, sequence=2, event_type="job.queued", level="info", message="queued for durable delivery"))
            await session.commit()
            job_id = job.id
        await self.queue.publish(job_id)
        return job_id

    async def list_projects(self) -> list[dict[str, str]]:
        async with self.sessions() as session:
            rows = await session.scalars(select(Project).where(Project.is_active.is_(True)).order_by(Project.slug))
            return [{"slug": row.slug, "name": row.name, "description": row.description} for row in rows]

    async def active_context(self, telegram_user_id: int, telegram_chat_id: int) -> tuple[User, Conversation] | None:
        async with self.sessions() as session:
            user = await session.scalar(select(User).where(User.telegram_user_id == telegram_user_id))
            chat = await session.scalar(select(Chat).where(Chat.telegram_chat_id == telegram_chat_id))
            if user is None or chat is None:
                return None
            conversation = await session.scalar(
                select(Conversation)
                .where(Conversation.user_id == user.id, Conversation.chat_id == chat.id, Conversation.status == "active")
                .order_by(Conversation.updated_at.desc())
            )
            return (user, conversation) if conversation is not None else None

    async def set_user_preference(self, telegram_user_id: int, key: str, value: object) -> bool:
        return await self.set_user_preferences(telegram_user_id, {key: value})

    async def set_user_preferences(
        self,
        telegram_user_id: int,
        updates: dict[str, object],
    ) -> bool:
        async with self.sessions() as session:
            user = await session.scalar(select(User).where(User.telegram_user_id == telegram_user_id))
            if user is None:
                return False
            user.preferences_json = {**user.preferences_json, **updates}
            await session.commit()
            return True

    async def new_conversation(self, telegram_user_id: int, telegram_chat_id: int) -> str | None:
        async with self.sessions() as session:
            user = await session.scalar(select(User).where(User.telegram_user_id == telegram_user_id))
            chat = await session.scalar(select(Chat).where(Chat.telegram_chat_id == telegram_chat_id))
            if user is None or chat is None:
                return None
            current = await session.scalar(
                select(Conversation)
                .where(
                    Conversation.user_id == user.id,
                    Conversation.chat_id == chat.id,
                    Conversation.status == "active",
                )
                .order_by(Conversation.updated_at.desc())
            )
            project_id = current.project_id if current else None
            if current:
                current.status = "closed"
                threads = await session.scalars(
                    select(CodexThread).where(
                        CodexThread.conversation_id == current.id
                    )
                )
                for thread in threads:
                    thread.status = "idle"
            conversation = Conversation(
                user_id=user.id,
                chat_id=chat.id,
                project_id=project_id,
                title="New Codex session",
            )
            session.add(conversation)
            await session.commit()
            return conversation.id

    async def list_codex_sessions(
        self, telegram_user_id: int, telegram_chat_id: int, limit: int = 12
    ) -> list[dict[str, object]]:
        async with self.sessions() as session:
            rows = await session.execute(
                select(CodexThread, Conversation, Project)
                .join(Conversation, CodexThread.conversation_id == Conversation.id)
                .join(User, Conversation.user_id == User.id)
                .join(Chat, Conversation.chat_id == Chat.id)
                .outerjoin(Project, CodexThread.project_id == Project.id)
                .where(
                    User.telegram_user_id == telegram_user_id,
                    Chat.telegram_chat_id == telegram_chat_id,
                )
                .order_by(CodexThread.updated_at.desc())
                .limit(limit)
            )
            result: list[dict[str, object]] = []
            for thread, conversation, project in rows:
                latest_job = await session.scalar(
                    select(Job)
                    .where(Job.conversation_id == conversation.id)
                    .order_by(Job.created_at.desc())
                    .limit(1)
                )
                latest_state = latest_job.state if latest_job else ""
                if latest_state in _RUNNING_JOB_STATES:
                    activity = "running"
                elif latest_state:
                    activity = f"idle · last {latest_state}"
                else:
                    activity = "idle · no tasks"
                usage = thread.metadata_json.get("token_usage", {})
                result.append(
                    {
                    "id": thread.id,
                    "thread_id": thread.codex_thread_id,
                    "project": project.name if project else "No project",
                    "model": thread.model,
                    "selected": conversation.status == "active",
                    "activity": activity,
                    "latest_job_id": latest_job.id if latest_job else "",
                    "latest_job_state": latest_state,
                    "usage": usage if isinstance(usage, dict) else {},
                    "updated_at": thread.updated_at,
                    }
                )
            return result

    async def current_codex_session(
        self,
        telegram_user_id: int,
        telegram_chat_id: int,
    ) -> dict[str, object] | None:
        sessions = await self.list_codex_sessions(
            telegram_user_id,
            telegram_chat_id,
            limit=100,
        )
        return next((row for row in sessions if row["selected"]), None)

    async def session_history(
        self,
        telegram_user_id: int,
        telegram_chat_id: int,
        session_id: str | None = None,
        *,
        job_limit: int = 10,
        event_limit: int = 25,
    ) -> dict[str, object] | None:
        async with self.sessions() as session:
            statement = (
                select(CodexThread, Conversation, Project)
                .join(Conversation, CodexThread.conversation_id == Conversation.id)
                .join(User, Conversation.user_id == User.id)
                .join(Chat, Conversation.chat_id == Chat.id)
                .outerjoin(Project, CodexThread.project_id == Project.id)
                .where(
                    User.telegram_user_id == telegram_user_id,
                    Chat.telegram_chat_id == telegram_chat_id,
                )
            )
            if session_id:
                statement = statement.where(CodexThread.id == session_id)
            else:
                statement = statement.where(Conversation.status == "active")
            row = (
                await session.execute(
                    statement.order_by(CodexThread.updated_at.desc()).limit(1)
                )
            ).first()
            if row is None:
                return None
            thread, conversation, project = row
            jobs = list(
                await session.scalars(
                    select(Job)
                    .where(Job.conversation_id == conversation.id)
                    .order_by(Job.created_at.desc())
                    .limit(job_limit)
                )
            )
            job_rows: list[dict[str, object]] = []
            for job in jobs:
                events = list(
                    await session.scalars(
                        select(JobEventRow)
                        .where(JobEventRow.job_id == job.id)
                        .order_by(JobEventRow.sequence.desc())
                        .limit(event_limit)
                    )
                )
                events.reverse()
                job_rows.append(
                    {
                        "id": job.id,
                        "state": job.state,
                        "objective": job.objective,
                        "result": job.result_summary or job.error_message,
                        "created_at": job.created_at,
                        "completed_at": job.completed_at,
                        "events": events,
                    }
                )
            usage = thread.metadata_json.get("token_usage", {})
            return {
                "id": thread.id,
                "thread_id": thread.codex_thread_id,
                "project": project.name if project else "No project",
                "model": thread.model,
                "selected": conversation.status == "active",
                "usage": usage if isinstance(usage, dict) else {},
                "jobs": job_rows,
            }

    async def resume_codex_session(
        self, telegram_user_id: int, telegram_chat_id: int, session_id: str
    ) -> bool:
        async with self.sessions() as session:
            target = await session.scalar(
                select(CodexThread)
                .join(Conversation, CodexThread.conversation_id == Conversation.id)
                .join(User, Conversation.user_id == User.id)
                .join(Chat, Conversation.chat_id == Chat.id)
                .where(
                    CodexThread.id == session_id,
                    User.telegram_user_id == telegram_user_id,
                    Chat.telegram_chat_id == telegram_chat_id,
                )
            )
            if target is None:
                return False
            conversation = await session.get(Conversation, target.conversation_id)
            if conversation is None:
                return False
            active_rows = await session.scalars(
                select(Conversation).where(
                    Conversation.user_id == conversation.user_id,
                    Conversation.chat_id == conversation.chat_id,
                    Conversation.status == "active",
                )
            )
            for row in active_rows:
                row.status = "closed"
                threads = await session.scalars(
                    select(CodexThread).where(
                        CodexThread.conversation_id == row.id
                    )
                )
                for thread in threads:
                    thread.status = "idle"
            conversation.status = "active"
            target.status = "active"
            await session.commit()
            return True

    async def recent_jobs(self, telegram_user_id: int, telegram_chat_id: int, limit: int = 10) -> list[Job]:
        async with self.sessions() as session:
            rows = await session.scalars(
                select(Job)
                .join(Conversation, Job.conversation_id == Conversation.id)
                .join(User, Conversation.user_id == User.id)
                .join(Chat, Conversation.chat_id == Chat.id)
                .where(User.telegram_user_id == telegram_user_id, Chat.telegram_chat_id == telegram_chat_id)
                .order_by(Job.created_at.desc())
                .limit(limit)
            )
            return list(rows)

    async def select_project(self, telegram_user_id: int, telegram_chat_id: int, slug: str) -> bool:
        async with self.sessions() as session:
            user = await session.scalar(select(User).where(User.telegram_user_id == telegram_user_id))
            chat = await session.scalar(select(Chat).where(Chat.telegram_chat_id == telegram_chat_id))
            project = await session.scalar(select(Project).where(Project.slug == slug, Project.is_active.is_(True)))
            if user is None or chat is None or project is None:
                return False
            conversation = await session.scalar(
                select(Conversation)
                .where(Conversation.user_id == user.id, Conversation.chat_id == chat.id, Conversation.status == "active")
                .order_by(Conversation.updated_at.desc())
            )
            if conversation is None:
                conversation = Conversation(user_id=user.id, chat_id=chat.id, title="Telegram conversation")
                session.add(conversation)
            conversation.project_id = project.id
            await session.commit()
            return True

    async def get(self, job_id: str) -> Job | None:
        async with self.sessions() as session:
            return await session.get(Job, job_id)

    async def get_for_context(
        self, telegram_user_id: int, telegram_chat_id: int, job_id: str
    ) -> Job | None:
        """Return a job only when it belongs to the requesting Telegram context."""
        async with self.sessions() as session:
            return await session.scalar(
                select(Job)
                .join(Conversation, Job.conversation_id == Conversation.id)
                .join(User, Conversation.user_id == User.id)
                .join(Chat, Conversation.chat_id == Chat.id)
                .where(
                    Job.id == job_id,
                    User.telegram_user_id == telegram_user_id,
                    Chat.telegram_chat_id == telegram_chat_id,
                )
            )

    async def events(self, job_id: str) -> list[JobEventRow]:
        async with self.sessions() as session:
            rows = await session.scalars(
                select(JobEventRow)
                .where(JobEventRow.job_id == job_id)
                .order_by(JobEventRow.sequence)
            )
            return list(rows)

    async def cancel(self, job_id: str) -> bool:
        async with self.sessions() as session:
            job = await session.get(Job, job_id, with_for_update=True)
            if job is None or job.state in {JobState.COMPLETED.value, JobState.FAILED.value, JobState.CANCELLED.value}:
                return False
            job.state = JobState.CANCEL_REQUESTED.value
            session.add(JobEventRow(job_id=job.id, sequence=await self._next_sequence(session, job.id), event_type="job.cancel_requested", level="info", message="cancellation requested"))
            await session.commit()
            return True

    async def cancel_for_context(
        self, telegram_user_id: int, telegram_chat_id: int, job_id: str
    ) -> bool:
        if await self.get_for_context(telegram_user_id, telegram_chat_id, job_id) is None:
            return False
        return await self.cancel(job_id)

    @staticmethod
    async def _next_sequence(session: AsyncSession, job_id: str) -> int:
        events = await session.scalars(select(JobEventRow.sequence).where(JobEventRow.job_id == job_id))
        return max(events, default=0) + 1
