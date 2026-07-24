from __future__ import annotations

from datetime import datetime, timezone

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from telegram_codex_agent.db.models import (
    Chat,
    Conversation,
    Job,
    JobEventRow,
    Message,
    Project,
    User,
)
from telegram_codex_agent.jobs.models import IntentType, JobState
from telegram_codex_agent.jobs.queue import RedisStreamJobQueue


class JobService:
    """Transactional ingress: durable context/message/job first, Redis delivery second."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession], redis: Redis, stream: str, group: str) -> None:
        self.sessions = sessions
        self.queue = RedisStreamJobQueue(redis, stream, group)

    async def create_from_text(self, telegram_user_id: int, telegram_chat_id: int, text: str) -> str:
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
            message = Message(conversation_id=conversation.id, role="user", content_type="text", text=text)
            session.add(message)
            await session.flush()
            job = Job(conversation_id=conversation.id, project_id=conversation.project_id, request_message_id=message.id, intent=IntentType.UNKNOWN.value, objective=text, state=JobState.QUEUED.value)
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

    @staticmethod
    async def _next_sequence(session: AsyncSession, job_id: str) -> int:
        events = await session.scalars(select(JobEventRow.sequence).where(JobEventRow.job_id == job_id))
        return max(events, default=0) + 1
