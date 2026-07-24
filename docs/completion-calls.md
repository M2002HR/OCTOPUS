# Codex completion calls

Completion calls are opt-in telephone notifications for terminal Codex jobs. When enabled for a
Bot user, the primary Telethon account calls that same Telegram identity after an eligible job
stops, speaks a short status exactly three times, and hangs up.

## User contract

Use `/completion_call`, `/completion_call on`, `/completion_call off`, or
**Settings → Completion call**. The preference is stored per Telegram user and is disabled by
default. It is snapshotted when a job is created, so changing it does not retroactively alter a
job already in the queue.

The global `CODEX_COMPLETION_CALLS_ENABLED` policy must also be true. The target numeric Telegram
ID must be in `VOICE_AGENT_ALLOWED_PEER_IDS`. The feature applies only to jobs that use Codex:
direct Ajil chat does not create a completion call.

Terminal state and category mapping:

| Job outcome | Spoken category |
| --- | --- |
| Completed | `success` |
| User cancellation | `cancelled` |
| Worker/process interruption | `interrupted` |
| Codex account or provider limit | `rate_limit` |
| Execution or provider timeout | `timeout` |
| Authentication failure | `authentication` |
| Any other failure | `failure` |

Ajil receives a content-minimized terminal context and writes one concise English message. The
prompt encourages natural variation, so equivalent outcomes need not use identical wording. The
result is validated, length-limited, stripped of control characters, and rejected if it contains
Persian text. A category-specific English fallback is used when Ajil is unavailable or returns an
invalid result.

## End-to-end flow

```text
Codex turn stops
  -> worker commits authoritative terminal job state in PostgreSQL
  -> worker generates one safe message through Ajil
  -> atomic Redis SET-NX deduplication + XADD
  -> voice-agent consumer group receives the request
  -> target numeric ID is checked against the Telethon allowlist
  -> Edge TTS renders message + message + message in English
  -> primary Telethon/PyTgCalls session places and plays the call
  -> post-playback guard expires
  -> hangup and temporary-audio cleanup
  -> delivered marker + XACK
```

The worker never opens `TELEGRAM_STRING_SESSION`. Only the existing `voice-agent` process owns the
primary session. This is essential: two simultaneous MTProto clients using the same authorization
can split private-call updates and leave Telegram at “Exchanging encryption keys.”

## Delivery semantics

PostgreSQL remains the job source of truth; completion notification failure never changes the
Codex job result. Redis DB 1 carries a separate durable Stream:

- stream: `telegram_codex_agent.completion_calls`
- consumer group: `voice_agent.completion_calls`
- publish deduplication: one request per job for the configured retention period
- delivery marker: suppresses normal duplicate calls after success
- retries: bounded attempts with a configured delay
- recovery: `XAUTOCLAIM` checks stale pending entries on every consumer poll
- trimming: approximate maximum stream length, default 10,000

Delivery is intentionally at-least-once across a crash boundary. If the voice process dies after
Telegram heard the message but before the delivered marker is stored, recovery may repeat the
call. Avoiding that last duplicate would require a distributed transaction with Telegram, which
Telegram does not offer. The design prefers a recoverable notification over silent loss.

If a normal inbound/outbound call is already active, the attempt fails as busy and follows the
bounded retry policy. Synthesis failures, busy retries, cancellation, hangup, and normal delivery
all clean their temporary audio directory.

## Configuration

| Variable/policy | Default | Meaning |
| --- | ---: | --- |
| `CODEX_COMPLETION_CALLS_ENABLED` | `true` | Global feature availability; per-user opt-in is still required |
| `CODEX_COMPLETION_CALL_STREAM` | `telegram_codex_agent.completion_calls` | Redis Stream |
| `CODEX_COMPLETION_CALL_CONSUMER_GROUP` | `voice_agent.completion_calls` | Voice consumer group |
| `CODEX_COMPLETION_CALL_REDIS_URL` | host-specific | Voice consumer Redis DB; Compose injects `redis://redis:6379/1` |
| `CODEX_COMPLETION_CALL_RETRY_ATTEMPTS` | `3` | Total call attempts |
| `CODEX_COMPLETION_CALL_RETRY_DELAY_SEC` | `10` | Seconds between attempts |
| `CODEX_COMPLETION_CALL_POST_PLAYBACK_SEC` | `2` | Playback guard before hangup |
| `voice.completion_calls.repeat_count` | `3` | Fixed by schema to exactly three |
| `voice.completion_calls.max_message_characters` | `240` | Ajil/fallback message limit |
| `voice.completion_calls.queue_retention_seconds` | `2592000` | Publish/delivery dedup retention |
| `voice.completion_calls.max_queue_length` | `10000` | Approximate Stream cap |

Changing the stream/group must be coordinated between the worker policy and voice environment.
Changing the allowlist or voice environment requires a `voice-agent` restart.

## Observability and privacy

The PostgreSQL job event log records safe events such as `completion_call.queued`,
`completion_call.duplicate`, `completion_call.failed`, and `completion_call.skipped`. The voice
SQLite/JSONL audit records:

- `completion_call.consumer.ready`
- `completion_call.attempt`
- `completion_call.attempt.failed`
- `completion_call.requested`
- `completion_call.active`
- `completion_call.delivered`
- `completion_call.duplicate_suppressed`
- `completion_call.payload.invalid`
- `completion_call.exhausted`

The spoken message, objective, result, stack trace, credentials, and URLs are not written to the
voice audit. Audit metadata is limited to job/call IDs, category, attempt, target numeric ID,
repeat count, duration, and error class.

## Verification

Automated coverage lives in `tests_agent/test_completion_calls.py` and
`tests/test_completion_call_consumer.py`. It covers every category, redaction, Ajil fallback,
exact repetition, schema validation, atomic publish/deduplication, retry, invalid payloads, audit
privacy, and fast-restart pending recovery.

The opt-in live harness is `scripts/completion_call_live_test.py`. It uses the second Telethon
session as the Bot user and call recipient while the primary session remains exclusively owned by
`voice-agent`. It:

1. enables the preference through the real Bot UI;
2. selects a workspace and submits a real Codex job;
3. answers the primary-session call from the second account;
4. records the received PCM;
5. confirms automatic hangup;
6. sends the recording through STT with bounded retry;
7. verifies repeated transcript n-grams.

Never run the harness against an unapproved username. Preserve only content-safe summaries and
ignored runtime media.

## Operator checks

```bash
docker compose --profile agent logs --tail=200 agent-worker voice-agent
docker compose exec -T redis redis-cli -n 1 \
  XPENDING telegram_codex_agent.completion_calls voice_agent.completion_calls
docker compose exec -T redis redis-cli -n 1 \
  XINFO GROUPS telegram_codex_agent.completion_calls
```

Healthy idle state is `pending=0`, `lag=0`, a ready voice service, and a live primary Telethon
connection. See [Troubleshooting](troubleshooting.md#codex-completion-call) for failure handling.
