from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from voice_agent.observability import Event, JsonlEventWriter


class AuditStore:
    """Durable append-only event store with a human-inspectable JSONL mirror."""

    def __init__(self, database_path: Path, jsonl_path: Path) -> None:
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(database_path)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              occurred_at REAL NOT NULL,
              trace_id TEXT NOT NULL,
              call_id TEXT,
              turn_id TEXT,
              name TEXT NOT NULL,
              status TEXT NOT NULL,
              details_json TEXT NOT NULL
            )
            """
        )
        self.connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_audit_events_trace "
            "ON audit_events(trace_id, occurred_at)"
        )
        self.connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_audit_events_call ON audit_events(call_id, occurred_at)"
        )
        # Conversation content is deliberately kept out of the JSONL event stream: the
        # event stream is easy to tail and export, while this table is queryable and can
        # be protected independently at rest.  Audio itself is not retained here.
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS conversation_turns (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              occurred_at REAL NOT NULL,
              trace_id TEXT NOT NULL,
              call_id TEXT NOT NULL,
              turn_id TEXT NOT NULL UNIQUE,
              input_audio_path TEXT NOT NULL,
              input_language TEXT,
              transcript TEXT NOT NULL,
              reply TEXT NOT NULL,
              output_audio_path TEXT NOT NULL,
              output_duration_ms INTEGER NOT NULL
            )
            """
        )
        self.connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_conversation_turns_call "
            "ON conversation_turns(call_id, occurred_at)"
        )
        self.connection.commit()
        self.jsonl = JsonlEventWriter(jsonl_path)

    def append(self, event: Event) -> None:
        payload = event.payload()
        self.connection.execute(
            """
            INSERT INTO audit_events(
              occurred_at, trace_id, call_id, turn_id, name, status, details_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.occurred_at,
                event.trace_id,
                event.call_id,
                event.turn_id,
                event.name,
                event.status,
                json.dumps(payload["details"], ensure_ascii=False, sort_keys=True),
            ),
        )
        self.connection.commit()
        self.jsonl.write(event)

    def events_for_trace(self, trace_id: str) -> list[tuple[str, str]]:
        rows = self.connection.execute(
            "SELECT name, status FROM audit_events WHERE trace_id = ? ORDER BY id", (trace_id,)
        ).fetchall()
        return [(str(name), str(status)) for name, status in rows]

    def record_conversation_turn(
        self,
        *,
        occurred_at: float,
        trace_id: str,
        call_id: str,
        turn_id: str,
        input_audio_path: Path,
        input_language: str | None,
        transcript: str,
        reply: str,
        output_audio_path: Path,
        output_duration_ms: int,
    ) -> None:
        """Persist the textual conversation and media references for later analysis."""
        self.connection.execute(
            """
            INSERT INTO conversation_turns(
              occurred_at, trace_id, call_id, turn_id, input_audio_path, input_language,
              transcript, reply, output_audio_path, output_duration_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                occurred_at,
                trace_id,
                call_id,
                turn_id,
                str(input_audio_path),
                input_language,
                transcript,
                reply,
                str(output_audio_path),
                output_duration_ms,
            ),
        )
        self.connection.commit()

    def conversation_for_call(self, call_id: str) -> list[tuple[str, str]]:
        rows = self.connection.execute(
            "SELECT transcript, reply FROM conversation_turns WHERE call_id = ? ORDER BY id",
            (call_id,),
        ).fetchall()
        return [(str(transcript), str(reply)) for transcript, reply in rows]

    def close(self) -> None:
        self.connection.close()
