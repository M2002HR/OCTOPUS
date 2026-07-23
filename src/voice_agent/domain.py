from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from time import time
from typing import Final
from uuid import uuid4


class CallState(StrEnum):
    NEW = "new"
    RINGING = "ringing"
    CONNECTING = "connecting"
    ACTIVE = "active"
    ENDED = "ended"
    FAILED = "failed"


class TurnState(StrEnum):
    RECEIVED = "received"
    TRANSCRIBING = "transcribing"
    THINKING = "thinking"
    SYNTHESIZING = "synthesizing"
    READY = "ready"
    FAILED = "failed"


VALID_CALL_TRANSITIONS: Final[dict[CallState, set[CallState]]] = {
    CallState.NEW: {CallState.RINGING, CallState.CONNECTING, CallState.FAILED},
    CallState.RINGING: {CallState.CONNECTING, CallState.ENDED, CallState.FAILED},
    CallState.CONNECTING: {CallState.ACTIVE, CallState.ENDED, CallState.FAILED},
    CallState.ACTIVE: {CallState.ENDED, CallState.FAILED},
    CallState.ENDED: set(),
    CallState.FAILED: set(),
}


@dataclass(slots=True)
class Call:
    peer_id: int
    peer_username: str | None
    id: str = field(default_factory=lambda: str(uuid4()))
    state: CallState = CallState.NEW
    created_at: float = field(default_factory=time)

    def transition(self, target: CallState) -> None:
        if target not in VALID_CALL_TRANSITIONS[self.state]:
            raise ValueError(f"invalid call transition {self.state!s} -> {target!s}")
        self.state = target


@dataclass(frozen=True, slots=True)
class AudioTurn:
    call_id: str
    audio_path: Path
    mime_type: str
    language: str | None = None
    trace_id: str = field(default_factory=lambda: str(uuid4()))


@dataclass(frozen=True, slots=True)
class AssistantTurn:
    call_id: str
    trace_id: str
    transcript: str
    reply: str
    audio_path: Path
    duration_ms: int


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: str
    content: str
