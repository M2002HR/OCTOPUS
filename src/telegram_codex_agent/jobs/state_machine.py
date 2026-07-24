from __future__ import annotations

from collections.abc import Callable

from telegram_codex_agent.core.errors import JobCancelledError
from telegram_codex_agent.jobs.models import JobEvent, JobRecord, JobState, utcnow

_ACTIVE = {
    JobState.NORMALIZING,
    JobState.CONTEXT_RESOLUTION,
    JobState.MEMORY_RETRIEVAL,
    JobState.CLASSIFYING,
    JobState.PLANNING,
    JobState.PLANNED,
    JobState.QUEUED,
    JobState.RUNNING,
    JobState.WAITING_EXTERNAL,
    JobState.VERIFYING,
    JobState.REPORTING,
    JobState.RECOVERING,
}
_ALLOWED: dict[JobState, set[JobState]] = {
    JobState.RECEIVED: {JobState.NORMALIZING, JobState.FAILED, JobState.CANCELLED},
    JobState.NORMALIZING: {JobState.CONTEXT_RESOLUTION, JobState.CANCEL_REQUESTED, JobState.FAILED},
    JobState.CONTEXT_RESOLUTION: {
        JobState.MEMORY_RETRIEVAL,
        JobState.CANCEL_REQUESTED,
        JobState.FAILED,
    },
    JobState.MEMORY_RETRIEVAL: {JobState.CLASSIFYING, JobState.CANCEL_REQUESTED, JobState.FAILED},
    JobState.CLASSIFYING: {
        JobState.PLANNING,
        JobState.PLANNED,
        JobState.CANCEL_REQUESTED,
        JobState.FAILED,
    },
    JobState.PLANNING: {JobState.PLANNED, JobState.CANCEL_REQUESTED, JobState.FAILED},
    JobState.PLANNED: {
        JobState.QUEUED,
        JobState.RUNNING,
        JobState.CANCEL_REQUESTED,
        JobState.FAILED,
    },
    JobState.QUEUED: {
        JobState.RUNNING,
        JobState.RECOVERING,
        JobState.CANCEL_REQUESTED,
        JobState.FAILED,
    },
    JobState.RUNNING: {
        JobState.WAITING_EXTERNAL,
        JobState.VERIFYING,
        JobState.REPORTING,
        JobState.RECOVERING,
        JobState.CANCEL_REQUESTED,
        JobState.FAILED,
    },
    JobState.WAITING_EXTERNAL: {JobState.RUNNING, JobState.CANCEL_REQUESTED, JobState.FAILED},
    JobState.VERIFYING: {
        JobState.REPORTING,
        JobState.RECOVERING,
        JobState.CANCEL_REQUESTED,
        JobState.FAILED,
    },
    JobState.REPORTING: {JobState.COMPLETED, JobState.FAILED, JobState.CANCEL_REQUESTED},
    JobState.CANCEL_REQUESTED: {JobState.CANCELLED, JobState.FAILED},
    JobState.RECOVERING: {JobState.RUNNING, JobState.FAILED, JobState.CANCELLED},
    JobState.INTERRUPTED: {JobState.RECOVERING, JobState.FAILED, JobState.CANCELLED},
    JobState.COMPLETED: set(),
    JobState.FAILED: set(),
    JobState.CANCELLED: set(),
}


class JobStateMachine:
    def __init__(self, job: JobRecord, emit: Callable[[JobEvent], None] | None = None) -> None:
        self.job = job
        self.events: list[JobEvent] = []
        self._emit = emit

    def transition(self, state: JobState, message: str, **data: object) -> JobEvent:
        if state not in _ALLOWED[self.job.state]:
            raise ValueError(f"invalid job transition {self.job.state} -> {state}")
        previous = self.job.state
        self.job.state = state
        now = utcnow()
        if state == JobState.QUEUED:
            self.job.queued_at = now
        elif state == JobState.RUNNING and self.job.started_at is None:
            self.job.started_at = now
        elif state == JobState.COMPLETED:
            self.job.completed_at = now
        elif state == JobState.CANCELLED:
            self.job.cancelled_at = now
        event = JobEvent(
            job_id=self.job.id,
            sequence=len(self.events) + 1,
            event_type=f"job.{state}",
            message=message,
            data={"from": previous, **data},
        )
        self.events.append(event)
        if self._emit:
            self._emit(event)
        return event

    def heartbeat(self, worker_id: str) -> JobEvent:
        self.job.worker_id = worker_id
        self.job.heartbeat_at = utcnow()
        event = JobEvent(
            job_id=self.job.id,
            sequence=len(self.events) + 1,
            event_type="job.heartbeat",
            message="worker heartbeat",
        )
        self.events.append(event)
        if self._emit:
            self._emit(event)
        return event

    def raise_if_cancelled(self) -> None:
        if self.job.state == JobState.CANCEL_REQUESTED:
            raise JobCancelledError(f"job {self.job.id} is cancelled")
