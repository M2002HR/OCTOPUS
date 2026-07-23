from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from time import time
from typing import Any, cast

SENSITIVE_KEYS = frozenset(
    {"authorization", "api_key", "api_hash", "token", "session", "password", "access_hash"}
)


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if key.casefold() in SENSITIVE_KEYS else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class Event:
    name: str
    trace_id: str
    call_id: str | None = None
    turn_id: str | None = None
    status: str = "ok"
    details: dict[str, Any] = field(default_factory=dict)
    occurred_at: float = field(default_factory=time)

    def payload(self) -> dict[str, Any]:
        return cast(dict[str, Any], redact(asdict(self)))


class JsonlEventWriter:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, event: Event) -> None:
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event.payload(), ensure_ascii=False, sort_keys=True) + "\n")


def get_logger(name: str = "voice_agent") -> logging.Logger:
    return logging.getLogger(name)
