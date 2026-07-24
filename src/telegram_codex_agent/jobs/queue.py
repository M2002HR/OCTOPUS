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

    @staticmethod
    def _decode(messages: object) -> list[tuple[str, str]]:
        decoded: list[tuple[str, str]] = []
        if not isinstance(messages, (list, tuple)):
            return decoded
        for item in messages:
            if not isinstance(item, (list, tuple)) or len(item) != 2:
                continue
            message_id, fields = item
            if not isinstance(fields, dict):
                continue
            raw_job_id = fields.get("job_id", fields.get(b"job_id"))
            if raw_job_id is None:
                raise KeyError("job_id")
            if isinstance(message_id, bytes):
                message_id = message_id.decode()
            if isinstance(raw_job_id, bytes):
                raw_job_id = raw_job_id.decode()
            decoded.append((str(message_id), str(raw_job_id)))
        return decoded

    async def claim_stale(
        self,
        consumer: str,
        *,
        min_idle_ms: int,
        count: int = 10,
    ) -> list[tuple[str, str]]:
        """Transfer abandoned pending entries to the current worker.

        PostgreSQL's job lease remains the authority for whether execution may
        resume. Claiming the stream entry alone never grants execution rights.
        """
        result = await self.redis.xautoclaim(
            self.stream,
            self.group,
            consumer,
            min_idle_ms,
            "0-0",
            count=count,
        )
        return self._decode(result[1] if isinstance(result, (list, tuple)) and len(result) > 1 else [])

    async def consume(
        self,
        consumer: str,
        block_ms: int = 1000,
        stale_idle_ms: int = 60_000,
    ) -> AsyncIterator[tuple[str, str]]:
        while True:
            for pending in await self.claim_stale(
                consumer,
                min_idle_ms=stale_idle_ms,
            ):
                yield pending
            records = await self.redis.xreadgroup(
                self.group, consumer, {self.stream: ">"}, count=1, block=block_ms
            )
            for _, messages in records:
                for item in self._decode(messages):
                    yield item

    async def acknowledge(self, message_id: str) -> None:
        await self.redis.xack(self.stream, self.group, message_id)

    async def publish_event(self, job_id: str, event: dict[str, object]) -> None:
        await self.redis.publish(
            f"telegram_codex_agent.job.{job_id}", json.dumps(event, ensure_ascii=False)
        )
