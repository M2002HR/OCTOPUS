# Operations runbook

## Start and readiness

```bash
docker compose --profile agent up -d
docker compose --profile agent ps
curl --noproxy '*' -fsS http://127.0.0.1:18090/ready
curl --noproxy '*' -fsS http://127.0.0.1:8080/health
```

Expected persistent services: PostgreSQL, Redis, Ajil, API, Bot, worker, primary voice agent, and
configured media sidecars. `agent-migrate` exits successfully after applying Alembic.

Readiness requires Ajil, database, and Redis checks true. Voice logs must show Telethon connection
and inbound service ready. Use:

```bash
docker compose --profile agent logs --tail=200 \
  agent-api agent-bot agent-worker voice-agent
```

## Daily Telegram workflow

1. `/start`
2. `/projects` and select a workspace
3. `/new` or `/resume`
4. review `/status` settings
5. send the task
6. monitor public progress
7. inspect `/history` or `/logs JOB_ID`
8. request `/browser screenshot` or artifacts when visual evidence is required

Enable `/completion_call on` only if the owner wants telephone notification for future Codex jobs.

## Inspect a job

```bash
curl --noproxy '*' http://127.0.0.1:18090/jobs/JOB_ID
curl --noproxy '*' http://127.0.0.1:18090/jobs/JOB_ID/events
docker compose --profile agent logs --tail=300 agent-worker
```

In Telegram use `/job JOB_ID`, `/logs JOB_ID`, and `/history`. Correlate job ID, Codex thread/turn
IDs, event sequence, worker ID, heartbeat, result/error, and terminal state. Do not copy raw
credentials/provider bodies into incidents.

## Cancel work

Send `/stop JOB_ID`. Confirm:

1. database state becomes `cancel_requested`;
2. worker emits cancellation/interrupt events;
3. App Server receives `turn/interrupt` when possible;
4. terminal state becomes `cancelled` or `interrupted`;
5. subprocess/browser resources stop;
6. completion call occurs only when snapshotted opt-in is true.

If the worker is unavailable, retain the persisted cancellation request and restore the worker;
do not manually mark success.

## Queue inspection and recovery

Jobs:

```bash
docker compose exec -T redis redis-cli -n 1 \
  XINFO GROUPS telegram_codex_agent.jobs
docker compose exec -T redis redis-cli -n 1 \
  XPENDING telegram_codex_agent.jobs telegram_codex_agent.workers
```

Completion calls:

```bash
docker compose exec -T redis redis-cli -n 1 \
  XINFO GROUPS telegram_codex_agent.completion_calls
docker compose exec -T redis redis-cli -n 1 \
  XPENDING telegram_codex_agent.completion_calls voice_agent.completion_calls
```

Pending during active work is normal. Persistent pending with no active consumer requires logs,
PostgreSQL state, and consumer identity inspection. Restart the affected service and let lease or
`XAUTOCLAIM` recovery reconcile it. Do not `XADD` a duplicate manually.

## Completion-call operations

Verify global policy, per-user opt-in, numeric allowlist, and one primary Telethon owner. Normal
idle state is completion Stream `pending=0`, `lag=0`.

Safe event chain:

```text
job completion_call.queued
voice completion_call.attempt
voice completion_call.requested
voice completion_call.active
voice completion_call.delivered
```

If busy/provider/network failure occurs, expect bounded retry and
`completion_call.attempt.failed`. After all attempts, `completion_call.exhausted` is terminal for
the notification; the Codex task result remains unchanged.

## Codex/Ajil diagnostics

```bash
make ajil-smoke
make codex-smoke
agentctl codex status
docker compose logs --tail=300 ajil_gateway agent-worker
```

`/usage` failing while jobs work usually indicates account-rate-limit RPC/cache trouble, not
session token usage. A rate limit/auth failure should be represented in the job and completion-call
category rather than retried forever.

## Voice and media

```bash
docker compose --profile agent ps
docker compose --profile agent exec -T voice-agent \
  python /app/scripts/media_overlay_stun_probe.py
tail -f runtime/events.jsonl
```

The STUN probe must pass in the same namespace used by PyTgCalls. Signaling connection alone does
not prove media. Never start another client with the primary session while the service is online.

## Logs and audit

- Bot/Codex job history: PostgreSQL `job_events`, visible through API/Telegram.
- Live progress: Redis and Telegram, controlled per user.
- Voice operations: `runtime/events.jsonl` plus SQLite `audit_events`.
- Voice/message content: SQLite only when `transcript_only`.
- Container stdout: structured service/application logs.

Use `info` for normal full process visibility and `debug` for deeper safe events. Neither level
exposes private reasoning or secrets.

## Backup

Back up PostgreSQL and Redis volumes before upgrades. Protect root `.env`, Codex home, Telethon
session, and relay keys separately; they must not enter repository backups. Back up voice SQLite
only when transcript retention permits it.

Test restore into a disposable deployment. PostgreSQL restoration is authoritative; Redis queues
must be reconciled against restored job states before workers start.

## Controlled update

```bash
git fetch --all --prune
git pull --ff-only
git submodule update --init --recursive
docker compose --profile agent build
docker compose --profile agent up -d
```

Recheck migrations, readiness, Codex/Ajil smoke, queues, voice owner, and one read-only Telegram
job. Recreate only affected services when an active call could otherwise be interrupted.

## Graceful shutdown

```bash
docker compose --profile agent stop \
  agent-bot agent-worker agent-api voice-agent \
  voice-media-tunnel voice-media-ssh-tunnel
docker compose --profile agent down
```

Do not delete volumes by default. A stopped worker can leave recoverable pending entries; inspect
them after restart.

## Incident priorities

1. Stop dangerous/corrupted execution using `/stop` or the worker service.
2. Preserve PostgreSQL state and safe event IDs.
3. Prevent a second Telethon owner.
4. Check Ajil/Codex/proxy health and queue consumers.
5. Restore the smallest affected service.
6. Verify cleanup, queue convergence, and a read-only smoke test.
7. Rotate credentials if any secret may have appeared in logs/files/chat.

Detailed symptom resolution is in [Troubleshooting](troubleshooting.md).
