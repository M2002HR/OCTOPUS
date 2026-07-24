from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from telegram_codex_agent.db.models import Job, JobEventRow, WorkerLease
from telegram_codex_agent.jobs.models import JobEvent, JobRecord, JobState, utcnow


class JobRepository:
    """PostgreSQL source of truth for jobs; every state event shares its transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, record: JobRecord) -> None:
        self.session.add(
            Job(
                id=record.id,
                conversation_id=record.conversation_id,
                project_id=record.project_id,
                parent_job_id=record.parent_job_id,
                request_message_id=record.request_message_id,
                intent=record.intent.value,
                objective=record.objective,
                state=record.state.value,
                priority=record.priority,
                attempt=record.attempt,
                max_attempts=record.max_attempts,
                execution_mode=record.execution_mode,
                metadata_json=record.metadata,
            )
        )
        await self.session.flush()

    async def transition(self, job_id: str, state: JobState, event: JobEvent) -> None:
        job = await self.session.get(Job, job_id, with_for_update=True)
        if job is None:
            raise KeyError(job_id)
        job.state = state.value
        if state == JobState.QUEUED:
            job.queued_at = utcnow()
        elif state == JobState.RUNNING and job.started_at is None:
            job.started_at = utcnow()
        elif state == JobState.COMPLETED:
            job.completed_at = utcnow()
        elif state == JobState.CANCELLED:
            job.cancelled_at = utcnow()
        self.session.add(
            JobEventRow(
                job_id=job_id,
                sequence=event.sequence,
                event_type=event.event_type,
                level=event.level,
                message=event.message,
                data_json=event.data,
            )
        )
        await self.session.flush()

    async def claim(self, job_id: str, worker_id: str, lease_seconds: int) -> bool:
        job = await self.session.get(Job, job_id, with_for_update=True)
        if job is None or job.state not in {JobState.QUEUED.value, JobState.RECOVERING.value}:
            return False
        now = utcnow()
        lease = await self.session.scalar(
            select(WorkerLease).where(WorkerLease.job_id == job_id).with_for_update()
        )
        if lease and lease.expires_at > now and lease.worker_id != worker_id:
            return False
        if lease is None:
            lease = WorkerLease(
                job_id=job_id,
                worker_id=worker_id,
                expires_at=now + timedelta(seconds=lease_seconds),
            )
            self.session.add(lease)
        else:
            lease.worker_id = worker_id
            lease.heartbeat_at = now
            lease.expires_at = now + timedelta(seconds=lease_seconds)
        job.worker_id = worker_id
        job.heartbeat_at = now
        await self.session.flush()
        return True

    async def heartbeat(self, job_id: str, worker_id: str, lease_seconds: int) -> bool:
        lease = await self.session.scalar(
            select(WorkerLease).where(WorkerLease.job_id == job_id).with_for_update()
        )
        if lease is None or lease.worker_id != worker_id:
            return False
        now = utcnow()
        lease.heartbeat_at = now
        lease.expires_at = now + timedelta(seconds=lease_seconds)
        job = await self.session.get(Job, job_id, with_for_update=True)
        if job:
            job.heartbeat_at = now
        return True
