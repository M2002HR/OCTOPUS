# Operations and audit data

## Routine commands

```bash
docker compose ps
docker compose logs --tail=200 uag-gateway
tail -f runtime/events.jsonl
.venv/bin/python -c "import sqlite3; c = sqlite3.connect('runtime/voice_agent.sqlite3'); print(c.execute('SELECT name, status, count(*) FROM audit_events GROUP BY name, status ORDER BY name').fetchall())"
```

The agent emits an event for call requests, connection state, safe Telegram/PyTgCalls updates,
turn receipt, STT, AI, TTS, persistence, completion, and errors. Every event has a timestamp,
trace ID, call ID, optional turn ID, name, status, and safe metadata. JSONL is suitable for a log
collector; SQLite is suitable for indexed debugging and aggregate analysis.

## Privacy boundaries

`events.jsonl` contains no transcripts, replies, audio, call keys, signaling payloads, tokens, or
Telegram session strings. `conversation_turns`, enabled by `transcript_only`, contains transcript
and reply text and must be treated as sensitive. It records paths for diagnosis, but live-call
media is removed on shutdown. `off` prevents new transcript/reply rows while retaining operational
events.

Keep filesystem permissions restrictive. Back up the database only when policy permits it. Use
encrypted host or volume storage if encryption at rest is required, define a retention/deletion
job outside the application, and document who is allowed to query transcripts.

## Incident response

1. Stop the call with `Ctrl-C` or the process supervisor; it attempts a Telegram hangup and removes
   active-call media folders.
2. Save the relevant event trace IDs and error type, not secrets or signaling bytes.
3. Check Ajil health and its container logs.
4. Determine whether another client owns the Telegram session.
5. For media failures, give the network operator the exception class and timestamp, then check
   outbound Telegram VoIP connectivity. Do not publish credentials while debugging.

## Performance diagnosis

The event timings distinguish capture/VAD latency from STT, chat, and TTS latency. Start by
checking `VOICE_AGENT_VAD_END_SILENCE_MS`, then Ajil provider latency, then Edge TTS/ffmpeg.
Keep history bounded with `VOICE_AGENT_MAX_HISTORY_MESSAGES`. Use aggregate queries by event name
and timestamps; avoid exporting content-bearing transcript rows unless necessary.
