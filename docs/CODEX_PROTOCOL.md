# Codex App Server integration

Codex is the primary implementation, inspection, testing, Git, Docker, and browser-execution brain
for selected workspaces. OCTOPUS supervises the local Codex App Server and translates Telegram
jobs into JSON-RPC thread/turn operations; it does not shell out to one-shot `codex exec`.

## Process ownership

Each worker job starts a bounded App Server subprocess using `CODEX_BINARY app-server`. The client:

- applies the job's model, reasoning, service tier, approval, sandbox, cwd, and network policy;
- performs protocol initialization before starting work;
- reads stdout as JSONL without blocking the event loop;
- reads stderr separately with a byte cap;
- correlates request IDs with futures;
- streams notifications to the worker;
- handles server approval requests;
- interrupts active turns on cancellation;
- terminates/kills and awaits the subprocess during cleanup.

Startup, individual operations, job execution, and process shutdown are time-bounded. A worker
exception must not leave a Codex subprocess running.

## Thread and turn lifecycle

```text
new Telegram session
  -> thread/start(cwd, model, sandbox, approval, service tier)
  -> persist codex_thread_id

resumed Telegram session
  -> thread/resume(threadId, current overrides)

each task
  -> turn/start(threadId, user input, current overrides)
  -> notifications and safe commentary
  -> turn/completed or error
  -> persist turn ID, result, events, usage, and terminal job state
```

The persisted `CodexThread` binds one Telegram user/conversation/project to the App Server thread,
cwd, model, approval policy, sandbox, latest turn, status, usage metadata, and last-use timestamp.
`/new` creates fresh continuity; `/resume` selects existing continuity. A project switch starts a
new context rather than silently reusing a thread from another cwd.

## Input construction

The worker combines:

- the user's normalized objective;
- selected workspace identity and root;
- applicable explicit memory;
- normalized attachment metadata and image paths;
- current language preference;
- artifact handoff instructions when a file/screenshot is requested;
- terminal persistence/recovery context when a job is resumed.

Filesystem paths come from the project registry or deterministic inbox; arbitrary Telegram text
does not become a cwd. Secrets are not embedded into prompts.

## Events and progress

Important notifications include:

- `thread/started` and thread metadata;
- `turn/started`, `turn/completed`, and `error`;
- `thread/tokenUsage/updated`;
- item start/completion for commands, file changes, tool activity, and agent messages;
- public `agentMessage` commentary.

The worker normalizes these into ordered PostgreSQL `job_events` and publishes live safe events
through Redis. `info`/`debug` users see public commentary and lifecycle/tool summaries in Telegram.
Private reasoning items are intentionally neither displayed nor stored as user-visible
chain-of-thought.

Output is bounded by `jobs.output_byte_cap`; Telegram rendering is bounded separately by
`telegram.max_message_length`. Full safe event history remains paginated through `/logs`.

## Approval and permission bridge

The default development policy is:

```yaml
approval_policy: never
sandbox_mode: danger-full-access
network_access: true
```

Per-user settings map to read-only, workspace-write, or danger-full-access and are snapshotted on
the job. If App Server still requests command/file permission under a noninteractive policy, the
bridge returns a deterministic decline/cancel response rather than leaving the process blocked.

This is intentional single-owner development behavior, not a safe multi-user sandbox. See
[Security hardening](FUTURE_SECURITY_HARDENING.md).

## Model, reasoning, and Fast mode

The default model is `gpt-5.6-terra`; the default reasoning effort is `high`. User choices are sent
as explicit overrides to thread start/resume and turn start so a resumed thread does not silently
retain an obsolete setting.

Fast mode reads the live model catalog and stores the advertised service tier for the chosen
model. An unavailable/unsupported catalog leaves the preference unchanged. `/status` shows the
effective selection.

## Usage

Two kinds of usage are distinct:

1. `thread/tokenUsage/updated` is persisted for the selected Codex session and displayed in
   `/status` and `/history`.
2. `account/rateLimits/read` is the authenticated Codex account's weekly quota displayed by
   `/usage` and `/status`.

The account response is cached in Redis for one minute. A last-known one-day value may be shown,
explicitly labelled stale, when a fresh App Server query fails.

## Cancellation, timeout, and recovery

`/stop JOB_ID` first persists `cancel_requested`, then sends `turn/interrupt` when thread/turn IDs
are known. The worker always checks persisted cancellation between stages. Terminal states are
`completed`, `failed`, `cancelled`, and `interrupted`.

PostgreSQL leases and heartbeats detect abandoned running work. Redis consumer-group recovery
redelivers pending queue entries. The worker treats an already-terminal row as authoritative,
repairs any missing terminal completion-call publication through its deduplication key, and
acknowledges the queue item.

The recovery policy is `resume_or_fail`: resume when persisted identifiers and protocol state make
that safe; otherwise fail explicitly with evidence. It never claims success merely because a
worker restarted.

## Artifact handoff

Codex may append:

```text
[[telegram_file:/absolute/path/to/file]]
```

The worker strips the directive from the human result, resolves the file, enforces workspace/path
containment, computes SHA-256 and size, persists artifact metadata, and asks the Bot to upload it.
Missing, oversized, or out-of-scope files create safe failure events.

## Authentication and proxy

The App Server uses the mounted `CODEX_HOME` authentication state. Containers mount
`CODEX_HOME_HOST` into `/codex-home` and the local Codex runtime into `/host-codex` read-only.
`CODEX_HTTP_PROXY_URL` is independently mapped to `HTTP_PROXY`/`HTTPS_PROXY` for App Server
outbound traffic. It is not the Bot proxy, Telethon signaling proxy, Ajil proxy, or voice media
overlay.

Never commit `CODEX_ACCESS_TOKEN`, `OPENAI_API_KEY`, mounted Codex auth files, or App Server raw
authentication diagnostics.

## Diagnostics

```bash
agentctl codex status
agentctl codex smoke
docker compose --profile agent logs --tail=300 agent-worker
curl --noproxy '*' http://127.0.0.1:18090/jobs/JOB_ID
curl --noproxy '*' http://127.0.0.1:18090/jobs/JOB_ID/events
```

The smoke task is read-only and does not modify a workspace. See
[Troubleshooting](troubleshooting.md) for startup, proxy, authentication, quota, and stalled-turn
failures.
