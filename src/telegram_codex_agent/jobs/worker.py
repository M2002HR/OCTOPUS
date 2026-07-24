from __future__ import annotations

import asyncio
import logging
import socket

from redis.asyncio import Redis, from_url
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from telegram_codex_agent.core.config import Settings
from telegram_codex_agent.db.models import Job, JobEventRow, Message
from telegram_codex_agent.db.session import create_engine, create_session_factory
from telegram_codex_agent.integrations.ajil import AjilClient
from telegram_codex_agent.jobs.models import JobState
from telegram_codex_agent.jobs.queue import RedisStreamJobQueue

logger = logging.getLogger(__name__)


class Worker:
    """Recoverable direct-chat worker. Complex plans are deliberately held for Codex/tool executors."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.worker_id = f"{socket.gethostname()}-{id(self):x}"
        self.engine = create_engine(settings.database)
        self.sessions = create_session_factory(self.engine)
        self.redis: Redis = from_url(settings.redis.url, decode_responses=True)
        self.queue = RedisStreamJobQueue(self.redis, settings.redis.stream, settings.redis.consumer_group)
        self.stop_event = asyncio.Event()

    async def run(self) -> None:
        await self.queue.initialize()
        async for message_id, job_id in self.queue.consume(self.worker_id):
            try:
                await self._process(job_id)
                await self.queue.acknowledge(message_id)
            except Exception:
                logger.exception("worker failed job", extra={"job_id": job_id})

    async def close(self) -> None:
        await self.redis.aclose()
        await self.engine.dispose()

    async def _process(self, job_id: str) -> None:
        async with self.sessions() as session:
            job = await session.get(Job, job_id, with_for_update=True)
            if job is None:
                return
            if job.state == JobState.CANCEL_REQUESTED.value:
                await self._transition(session, job, JobState.CANCELLED, "cancelled before execution")
                await session.commit()
                return
            await self._transition(session, job, JobState.NORMALIZING, "normalizing request")
            await self._transition(session, job, JobState.CONTEXT_RESOLUTION, "resolving context")
            await self._transition(session, job, JobState.MEMORY_RETRIEVAL, "retrieving memory")
            await self._transition(session, job, JobState.CLASSIFYING, "classifying intent")
            await self._transition(session, job, JobState.PLANNING, "planning response")
            await self._transition(session, job, JobState.PLANNED, "plan ready")
            await self._transition(session, job, JobState.RUNNING, "running direct chat")
            await session.commit()
            objective = job.objective
            conversation_id = job.conversation_id
        client = AjilClient(self.settings.ajil)
        try:
            response = await client.chat([{"role": "system", "content": "Respond helpfully in Persian."}, {"role": "user", "content": objective}])
            content = client._content(response.data)
        finally:
            await client.aclose()
        async with self.sessions() as session:
            job = await session.get(Job, job_id, with_for_update=True)
            if job is None:
                return
            if job.state == JobState.CANCEL_REQUESTED.value:
                await self._transition(session, job, JobState.CANCELLED, "cancelled before report")
            else:
                session.add(Message(conversation_id=conversation_id, role="assistant", content_type="text", text=content))
                job.result_summary = content
                await self._transition(session, job, JobState.REPORTING, "reporting result")
                await self._transition(session, job, JobState.COMPLETED, "completed")
            await session.commit()

    @staticmethod
    async def _transition(session: AsyncSession, job: Job, target: JobState, message: str) -> None:
        rows = await session.scalars(select(JobEventRow.sequence).where(JobEventRow.job_id == job.id))
        job.state = target.value
        session.add(JobEventRow(job_id=job.id, sequence=max(rows, default=0) + 1, event_type=f"job.{target.value}", level="info", message=message))
