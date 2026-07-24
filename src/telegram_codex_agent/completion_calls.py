"""Durable, privacy-safe completion-call messages shared by the worker and voice service."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, ValidationError
from redis.asyncio import Redis

from telegram_codex_agent.core.config import CompletionCallConfig
from telegram_codex_agent.integrations.ajil import AjilClient

TerminalState = Literal["completed", "failed", "cancelled", "interrupted"]
TerminalCategory = Literal[
    "success",
    "cancelled",
    "interrupted",
    "rate_limit",
    "timeout",
    "authentication",
    "failure",
]

_PERSIAN_TEXT = re.compile(r"[\u0600-\u06ff]")
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]+")
_WHITESPACE = re.compile(r"\s+")
_SENSITIVE_ASSIGNMENT = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|token|secret|password)"
    r"(\s*[:=]\s*)([^\s,;]+)"
)
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_URL = re.compile(r"https?://\S+", re.IGNORECASE)
_RATE_LIMIT = re.compile(
    r"\b(429|rate.?limit|quota|usage.?limit|weekly.?limit|too many requests|"
    r"resource exhausted|insufficient[_ ]quota)\b",
    re.IGNORECASE,
)
_TIMEOUT = re.compile(r"\b(timeout|timed out|deadline exceeded)\b", re.IGNORECASE)
_AUTHENTICATION = re.compile(
    r"\b(401|403|unauthori[sz]ed|forbidden|authentication|invalid credential)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class TerminalJobContext:
    job_id: str
    state: TerminalState
    objective: str = ""
    result_summary: str = ""
    error_code: str = ""
    error_message: str = ""

    @property
    def diagnostic_text(self) -> str:
        return " ".join((self.error_code, self.error_message)).strip()

    @property
    def category(self) -> TerminalCategory:
        if self.state == "completed":
            return "success"
        if self.state == "cancelled":
            return "cancelled"
        if self.state == "interrupted":
            return "interrupted"
        if _RATE_LIMIT.search(self.diagnostic_text):
            return "rate_limit"
        if _TIMEOUT.search(self.diagnostic_text):
            return "timeout"
        if _AUTHENTICATION.search(self.diagnostic_text):
            return "authentication"
        return "failure"


class CompletionCallRequest(BaseModel):
    version: int = 1
    job_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    target_user_id: int = Field(gt=0)
    terminal_state: TerminalState
    category: TerminalCategory
    message: str = Field(min_length=1, max_length=500)
    repeat_count: int = Field(default=3, ge=3, le=3)
    created_at: str

    def redis_fields(self) -> dict[str, str]:
        return {"payload": self.model_dump_json()}

    @classmethod
    def from_redis_fields(
        cls, fields: dict[str | bytes, str | bytes]
    ) -> CompletionCallRequest:
        raw = fields.get("payload", fields.get(b"payload", ""))
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="strict")
        return cls.model_validate_json(raw)


def _safe_fragment(value: str, maximum: int) -> str:
    clean = _CONTROL_CHARACTERS.sub(" ", value)
    clean = _SENSITIVE_ASSIGNMENT.sub(r"\1\2[REDACTED]", clean)
    clean = _BEARER.sub("Bearer [REDACTED]", clean)
    clean = _URL.sub("[link omitted]", clean)
    clean = _WHITESPACE.sub(" ", clean).strip()
    return clean[:maximum].rstrip(" ,;:-")


def repeated_notification_text(message: str, repeat_count: int) -> str:
    if repeat_count != 3:
        raise ValueError("completion call messages must repeat exactly three times")
    clean = _safe_fragment(message, 500)
    if not clean:
        raise ValueError("completion call message is empty")
    return " ".join(clean for _ in range(repeat_count))


def _fallback_message(context: TerminalJobContext) -> str:
    variants: dict[TerminalCategory, tuple[str, ...]] = {
        "success": (
            "Your Codex task finished successfully. You can review the result in Telegram.",
            "Codex completed the task successfully. The final result is ready in Telegram.",
            "The requested Codex work is complete. Please check Telegram for the result.",
        ),
        "cancelled": (
            "The Codex task was cancelled. Open Telegram if you want to review or restart it.",
            "Codex stopped because the task was cancelled. You can continue from Telegram.",
            "The current Codex task has been cancelled. Please check Telegram for its status.",
        ),
        "interrupted": (
            "The Codex task was interrupted before completion. Please check Telegram.",
            "Codex stopped unexpectedly and the task is incomplete. Review the logs in Telegram.",
            "The task was interrupted. Open Telegram to inspect the status and continue.",
        ),
        "rate_limit": (
            "Codex reached the account usage limit. Please check Telegram before trying again.",
            "The task stopped because the Codex rate limit was reached. Review the status in Telegram.",
            "Codex cannot continue because the current usage limit was reached. Please check Telegram.",
        ),
        "timeout": (
            "The Codex task timed out before it could finish. Please inspect the logs in Telegram.",
            "Codex exceeded the allowed execution time. Open Telegram to review the task.",
            "The task stopped after a timeout. Please check Telegram for the details.",
        ),
        "authentication": (
            "Codex stopped because authentication failed. Please check the configuration in Telegram.",
            "The task could not continue due to an authentication error. Review Telegram for details.",
            "Codex encountered an access error and stopped. Please inspect the status in Telegram.",
        ),
        "failure": (
            "The Codex task stopped because of an error. Please check Telegram for the details.",
            "Codex could not complete the task. Open Telegram to inspect the error and logs.",
            "The task ended with an error. Please review its status in Telegram.",
        ),
    }
    digest = hashlib.sha256(context.job_id.encode("utf-8")).digest()
    choices = variants[context.category]
    return choices[digest[0] % len(choices)]


def _normalize_generated_message(
    text: str,
    *,
    maximum: int,
    fallback: str,
) -> str:
    clean = _safe_fragment(text.strip().strip("\"'`*"), maximum)
    clean = re.sub(r"^(?:message|notification)\s*:\s*", "", clean, flags=re.IGNORECASE)
    if not clean or _PERSIAN_TEXT.search(clean):
        return fallback
    if clean[-1] not in ".!?":
        clean += "."
    return clean


async def generate_terminal_message(
    client: AjilClient,
    context: TerminalJobContext,
    *,
    maximum_characters: int,
) -> tuple[str, Literal["ajil", "fallback"]]:
    """Ask Ajil for one short message and retain a deterministic safe fallback."""

    fallback = _fallback_message(context)
    objective = _safe_fragment(context.objective, 180) or "Not provided"
    result = _safe_fragment(context.result_summary, 220) or "Not provided"
    error = _safe_fragment(context.error_message, 220) or "Not provided"
    prompt = (
        "Write one natural English telephone notification for the owner of a Codex task. "
        f"The notification must be at most {maximum_characters} characters, plain text, and one "
        "or two short sentences. State why the task ended and tell the owner to check Telegram "
        "when useful. Never include secrets, paths, URLs, stack traces, markdown, greetings, or "
        "technical implementation details. Do not repeat the message; the calling system handles "
        "repetition. Vary the wording naturally across similar situations.\n\n"
        f"Terminal state: {context.state}\n"
        f"Reason category: {context.category}\n"
        f"Safe error type: {_safe_fragment(context.error_code, 80) or 'None'}\n"
        f"Safe error summary: {error}\n"
        f"Task summary: {objective}\n"
        f"Result summary: {result}"
    )
    try:
        response = await client.chat(
            [
                {
                    "role": "system",
                    "content": (
                        "You produce concise English operational voice notifications. "
                        "Follow the requested terminal state exactly and return only the message."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.8,
        )
        raw = client._content(response.data)
        message = _normalize_generated_message(
            raw,
            maximum=maximum_characters,
            fallback=fallback,
        )
        return message, "ajil" if message != fallback else "fallback"
    except Exception:
        return fallback, "fallback"


async def publish_completion_call(
    redis: Redis,
    config: CompletionCallConfig,
    request: CompletionCallRequest,
) -> bool:
    """Atomically deduplicate one terminal job and append its call request."""

    deduplication_key = f"telegram_codex_agent:completion_call:queued:{request.job_id}"
    script = """
    if redis.call('SET', KEYS[1], '1', 'NX', 'EX', ARGV[1]) then
      return redis.call(
        'XADD', KEYS[2], 'MAXLEN', '~', ARGV[2], '*', 'payload', ARGV[3]
      )
    end
    return ''
    """
    result = await redis.eval(
        script,
        2,
        deduplication_key,
        config.stream,
        config.queue_retention_seconds,
        config.max_queue_length,
        request.model_dump_json(),
    )
    return bool(result)


def build_completion_request(
    context: TerminalJobContext,
    *,
    target_user_id: int,
    message: str,
    repeat_count: int,
) -> CompletionCallRequest:
    return CompletionCallRequest(
        job_id=context.job_id,
        target_user_id=target_user_id,
        terminal_state=context.state,
        category=context.category,
        message=message,
        repeat_count=repeat_count,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def decode_request_json(raw: str) -> CompletionCallRequest:
    """Test and diagnostics helper with a stable validation error boundary."""

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("completion call payload is not valid JSON") from exc
    try:
        return CompletionCallRequest.model_validate(payload)
    except ValidationError as exc:
        raise ValueError("completion call payload does not match the schema") from exc
