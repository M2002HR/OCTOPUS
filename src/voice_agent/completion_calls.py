"""Redis-backed completion-call consumer owned by the single Telethon voice process."""

from __future__ import annotations

import asyncio
import logging
import socket
from collections.abc import Awaitable, Callable

from redis.asyncio import Redis, from_url
from redis.exceptions import ResponseError

from telegram_codex_agent.completion_calls import CompletionCallRequest
from voice_agent.observability import Event
from voice_agent.storage import AuditStore

logger = logging.getLogger(__name__)
CompletionCallHandler = Callable[[CompletionCallRequest], Awaitable[None]]


class CompletionCallConsumer:
    """Consume each queued terminal notification with bounded retries."""

    def __init__(
        self,
        *,
        redis_url: str,
        stream: str,
        consumer_group: str,
        retry_attempts: int,
        retry_delay_seconds: int,
        audit: AuditStore,
        handler: CompletionCallHandler,
        redis: Redis | None = None,
    ) -> None:
        self.redis = redis or from_url(  # type: ignore[no-untyped-call]
            redis_url,
            decode_responses=True,
        )
        self._owns_redis = redis is None
        self.stream = stream
        self.consumer_group = consumer_group
        self.consumer_name = f"{socket.gethostname()}-{id(self):x}"
        self.retry_attempts = retry_attempts
        self.retry_delay_seconds = retry_delay_seconds
        self.audit = audit
        self.handler = handler
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is not None:
            return
        try:
            await self.redis.xgroup_create(
                self.stream,
                self.consumer_group,
                id="0-0",
                mkstream=True,
            )
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise
        self._task = asyncio.create_task(
            self._run(),
            name="completion-call-consumer",
        )
        self.audit.append(
            Event(
                "completion_call.consumer.ready",
                "completion-call-consumer",
                details={"stream": self.stream},
            )
        )

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
        if self._owns_redis:
            await self.redis.aclose()

    async def _run(self) -> None:
        while True:
            # Retry recovery on every idle poll. A fast process restart may
            # initially find a pending delivery younger than the claim window;
            # checking only once would strand that call indefinitely.
            await self._recover_pending()
            rows = await self.redis.xreadgroup(
                self.consumer_group,
                self.consumer_name,
                {self.stream: ">"},
                count=1,
                block=5_000,
            )
            for _, messages in rows:
                for message_id, fields in messages:
                    await self._handle(message_id, fields)

    async def _recover_pending(self) -> None:
        start_id = "0-0"
        while True:
            claimed = await self.redis.xautoclaim(
                self.stream,
                self.consumer_group,
                self.consumer_name,
                min_idle_time=30_000,
                start_id=start_id,
                count=10,
            )
            if not isinstance(claimed, (list, tuple)) or len(claimed) < 2:
                return
            next_id = claimed[0]
            messages = claimed[1]
            for message_id, fields in messages:
                await self._handle(message_id, fields)
            if not messages or next_id in {"0-0", b"0-0"}:
                return
            start_id = next_id.decode() if isinstance(next_id, bytes) else str(next_id)

    async def _handle(
        self,
        message_id: str | bytes,
        fields: dict[str | bytes, str | bytes],
    ) -> None:
        try:
            request = CompletionCallRequest.from_redis_fields(fields)
        except Exception as exc:
            logger.warning("discarding invalid completion-call payload", exc_info=True)
            self.audit.append(
                Event(
                    "completion_call.payload.invalid",
                    "completion-call-consumer",
                    status="error",
                    details={"error_type": type(exc).__name__},
                )
            )
            await self.redis.xack(self.stream, self.consumer_group, message_id)
            return

        delivered_key = (
            f"telegram_codex_agent:completion_call:delivered:{request.job_id}"
        )
        if await self.redis.exists(delivered_key):
            await self.redis.xack(self.stream, self.consumer_group, message_id)
            self.audit.append(
                Event(
                    "completion_call.duplicate_suppressed",
                    request.job_id,
                    details={"category": request.category},
                )
            )
            return

        for attempt in range(1, self.retry_attempts + 1):
            try:
                self.audit.append(
                    Event(
                        "completion_call.attempt",
                        request.job_id,
                        details={
                            "attempt": attempt,
                            "category": request.category,
                            "target_user_id": request.target_user_id,
                        },
                    )
                )
                await self.handler(request)
                await self.redis.set(delivered_key, "1", ex=2_592_000)
                await self.redis.xack(self.stream, self.consumer_group, message_id)
                self.audit.append(
                    Event(
                        "completion_call.delivered",
                        request.job_id,
                        details={
                            "attempt": attempt,
                            "category": request.category,
                            "repeat_count": request.repeat_count,
                            "target_user_id": request.target_user_id,
                        },
                    )
                )
                return
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception(
                    "completion call attempt failed",
                    extra={"job_id": request.job_id, "attempt": attempt},
                )
                self.audit.append(
                    Event(
                        "completion_call.attempt.failed",
                        request.job_id,
                        status="error",
                        details={
                            "attempt": attempt,
                            "error_type": type(exc).__name__,
                            "target_user_id": request.target_user_id,
                        },
                    )
                )
                if attempt < self.retry_attempts:
                    await asyncio.sleep(self.retry_delay_seconds)

        # The original task result is already available through the Bot. An
        # exhausted call must not poison the stream forever.
        await self.redis.xack(self.stream, self.consumer_group, message_id)
        self.audit.append(
            Event(
                "completion_call.exhausted",
                request.job_id,
                status="error",
                details={
                    "attempts": self.retry_attempts,
                    "target_user_id": request.target_user_id,
                },
            )
        )
