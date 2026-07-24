from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from redis.asyncio import Redis


class InMemoryJobQueue:
    """Deterministic queue adapter used by unit tests and local no-Redis development."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[str] = asyncio.Queue()

    async def publish(self, job_id: str) -> None:
        await self._queue.put(job_id)

    async def consume(self) -> AsyncIterator[str]:
        while True:
            yield await self._queue.get()


class RedisStreamJobQueue:
    """At-least-once delivery over Redis Streams; PostgreSQL stays authoritative."""

    def __init__(self, redis: Redis, stream: str, group: str) -> None:
        self.redis = redis
        self.stream = stream
        self.group = group

    async def initialize(self) -> None:
        try:
            await self.redis.xgroup_create(self.stream, self.group, id="0", mkstream=True)
        except Exception as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def publish(self, job_id: str) -> None:
        await self.redis.xadd(self.stream, {"job_id": job_id})

    async def consume(self, consumer: str, block_ms: int = 1000) -> AsyncIterator[tuple[str, str]]:
        while True:
            records = await self.redis.xreadgroup(
                self.group, consumer, {self.stream: ">"}, count=1, block=block_ms
            )
            for _, messages in records:
                for message_id, fields in messages:
                    raw_job_id = fields.get("job_id", fields.get(b"job_id"))
                    if raw_job_id is None:
                        raise KeyError("job_id")
                    job_id = raw_job_id.decode() if isinstance(raw_job_id, bytes) else raw_job_id
                    yield (
                        message_id.decode() if isinstance(message_id, bytes) else message_id,
                        str(job_id),
                    )

    async def acknowledge(self, message_id: str) -> None:
        await self.redis.xack(self.stream, self.group, message_id)

    async def publish_event(self, job_id: str, event: dict[str, object]) -> None:
        await self.redis.publish(
            f"telegram_codex_agent.job.{job_id}", json.dumps(event, ensure_ascii=False)
        )
