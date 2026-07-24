# Observability, logs, audit, and retention

## Observability planes

| Plane | Store/transport | Content |
| --- | --- | --- |
| Control-plane state | PostgreSQL | Users, conversations, messages, jobs, results, threads, memory, artifacts |
| Durable job events | PostgreSQL `job_events` | Ordered lifecycle, safe commentary/tool summaries, verification |
| Live progress | Redis → Bot | Level-filtered safe events |
| Service logs | Docker/stdout | Structured operational logs and error classes |
| Voice audit | SQLite `audit_events` + JSONL | Content-free call/message/completion lifecycle |
| Voice content | SQLite turn tables | Optional transcript/reply text under `transcript_only` |
| Queue health | Redis Streams/groups | Pending, lag, delivery/recovery |

## Telegram log levels

Per-user `/logs` setting:

- `off`: no live progress; durable history remains;
- `error`: failures and terminal errors;
- `info`: full normal lifecycle, tool summaries, and public Codex commentary;
- `debug`: deepest safe public event detail.

Private chain-of-thought/reasoning, credentials, raw environments, unrestricted subprocess streams,
and provider request bodies are not forwarded at any level.

`/logs JOB_ID [PAGE]` reads ordered durable events. `/history` combines prompts/results/events for
the active owned session.

## API and service health

```bash
curl --noproxy '*' http://127.0.0.1:18090/health
curl --noproxy '*' http://127.0.0.1:18090/ready
curl --noproxy '*' http://127.0.0.1:18090/version
curl --noproxy '*' http://127.0.0.1:18090/config/redacted
curl --noproxy '*' http://127.0.0.1:8080/health
docker compose --profile agent ps
```

Liveness means the API process runs. Readiness separately checks Ajil, PostgreSQL, and Redis.
`/config/redacted` is the only configuration endpoint suitable for safe diagnostics.

## Job events

Each job event has job ID, monotonic sequence, type, level, message, safe structured data, and
timestamp. Typical flow:

```text
job.received -> job.planned -> job.queued -> job.running
  -> Codex thread/turn/tool/agentMessage events
  -> artifact/verification events
  -> job.completed | job.failed | job.cancelled | job.interrupted
  -> completion_call.* publication event when eligible
```

Heartbeat/lease events diagnose dead workers. Persisted order is authoritative; Telegram edit order
is presentation only.

## Voice events

Normal call events include service readiness, authorization/rejection, call state, media/turn
receipt, STT/chat/TTS stages, playback, persistence, hangup, cleanup, and error.

Private messages use `message.*`, including reply-context and media events. Completion calls use
`completion_call.consumer.ready`, attempt/failure, requested, active, delivered,
duplicate-suppressed, invalid-payload, and exhausted.

Completion audit stores job/call IDs, category, attempt, repeat count, duration, numeric target, and
error type. It deliberately excludes the generated spoken status.

Routine voice inspection:

```bash
tail -f runtime/events.jsonl
.venv/bin/python -c \
  "import sqlite3; c=sqlite3.connect('runtime/voice_agent.sqlite3'); print(c.execute('SELECT name,status,count(*) FROM audit_events GROUP BY name,status ORDER BY name').fetchall())"
```

## Redis queue monitoring

```bash
docker compose exec -T redis redis-cli -n 1 \
  XINFO GROUPS telegram_codex_agent.jobs
docker compose exec -T redis redis-cli -n 1 \
  XPENDING telegram_codex_agent.jobs telegram_codex_agent.workers
docker compose exec -T redis redis-cli -n 1 \
  XINFO GROUPS telegram_codex_agent.completion_calls
docker compose exec -T redis redis-cli -n 1 \
  XPENDING telegram_codex_agent.completion_calls voice_agent.completion_calls
```

Idle healthy queues normally have no pending and no lag. A pending entry during active execution is
normal. Recovery claims stale entries and reconciles database/dedup state.

## Privacy boundaries

Content-bearing sensitive stores:

- PostgreSQL messages, job objectives/results, conversation summaries, memory;
- SQLite `conversation_turns` and `message_turns` when enabled;
- artifact files and ignored live-test media;
- Codex home/browser profile outside application storage.

Content-free/safe-by-design operational stores:

- voice JSONL;
- redacted service logs;
- completion-call audit;
- API redacted configuration.

Paths, URLs, error strings, and custom metadata still require sanitization because they can embed
secrets. The application never persists call encryption keys, signaling bytes, session strings,
Bot/provider tokens, proxy passwords, or authorization headers.

## Retention and backup

`artifacts.retention_days` and `expires_at` describe artifact policy, but the disabled scheduler
means an external cleanup job is required. PostgreSQL, Redis AOF, SQLite, JSONL, artifacts, and
ignored runtime media each need explicit retention.

`VOICE_AGENT_RECORDING_MODE=off` prevents new transcript/reply rows while retaining operational
events. Both modes delete live call media during cleanup.

Back up content only when policy allows it. Use encrypted storage, least-privilege database access,
and tested restore. Never put backups into Git.

## Performance diagnosis

- Bot delays: Telegram proxy/API latency and progress edit throttle.
- Queue delays: Redis lag, worker availability, PostgreSQL leases.
- Codex delays: App Server startup, model/reasoning/Fast choice, tool subprocesses, quota.
- Ajil delays: router candidates, provider retries/timeouts.
- Voice response delays: VAD end silence, STT, chat, TTS, media playback.
- Completion-call delays: Ajil wording, active-call busy retries, TTS, answer/connect time.

Correlate timestamps rather than increasing timeouts blindly.

## Incident handling

1. Stop dangerous work with `/stop` or stop the smallest affected service.
2. Preserve job/call IDs, event sequences, timestamps, queue state, and error classes.
3. Check readiness and single primary Telethon ownership.
4. Rotate any credential suspected of exposure.
5. Restore service and let deterministic recovery reconcile state.
6. Verify cleanup, queues, and a read-only smoke task.

See [Runbook](RUNBOOK.md) and [Troubleshooting](troubleshooting.md).
