# System architecture

OCTOPUS is a personal Telegram control plane for an owner-operated development machine. It
combines a Bot API UI, durable jobs, Codex App Server, Ajil Unified AI Gateway, persistent memory,
workspace/browser/artifact workflows, and a preserved Telethon voice/message subsystem.

## Context and responsibility

```text
Owner
  |
  +-- Telegram Bot API (normal control plane)
  |     -> settings, workspace, session, jobs, logs, files
  |
  +-- primary Telethon account (private-call compatibility plane)
        -> inbound/outbound voice, private messages, completion calls

Telegram Bot / API
  -> PostgreSQL source of truth
  -> Redis job stream
  -> worker / orchestrator
       +-> Codex App Server (primary execution brain)
       +-> Ajil UAG (planning/direct chat/STT/status wording)
       +-> selected host workspace and its tools
       +-> artifact handoff back to Telegram
```

The Bot and Telethon account have different credentials, protocols, processes, and capabilities.
Bot API is suited to menus/files/messages but cannot place private user-account calls. Telethon
owns those calls. They share Ajil and policy but never share a network client.

## Runtime services

| Service | Role | Persistence/network |
| --- | --- | --- |
| `postgres` | Users, chats, projects, conversations, messages, jobs, events, threads, artifacts, memory, leases | pgvector PostgreSQL volume; localhost port |
| `redis` | Job delivery, live progress, usage/catalog cache, completion-call stream/dedup | AOF Redis volume; DB 1 for agent, DB 0 for Ajil |
| `ajil_gateway` | OpenAI-compatible chat, STT, vision/provider routing, health | Pinned `modules/ajil_uag`; internal network + localhost port |
| `agent-migrate` | Alembic upgrade before control services | One-shot dependency |
| `agent-api` | Health/readiness, redacted config, projects, jobs/events, enqueue/cancel | Localhost HTTP |
| `agent-bot` | Aiogram polling UI, commands, settings, Telegram delivery | Host network for proxy/Codex access |
| `agent-worker` | Leases, planner, Codex/Ajil execution, events, artifacts, recovery | Host network and mounted workspaces |
| `voice-agent` | Sole primary Telethon owner, calls/messages/completion-call consumer | Dedicated runtime volume and Compose network |
| media sidecars | UDP capture through GOST/SSH/HTTP CONNECT | Shared voice namespace, no public relay port |

Optional profiles expose local Bot API, Prometheus, and Grafana. The scheduler entry point is
reserved but intentionally disabled.

## Configuration boundary

`config/agent.yaml` contains all checked-in non-secret policy. The root `.env` contains secrets and
machine/deployment overrides. Loading order is:

```text
Pydantic defaults <- config/agent.yaml <- ${ENV:-default} expansion <- existing process/.env values
```

The voice compatibility package reads its environment contract directly but from the same root
`.env`. Compose applies container-specific URLs/mounts without creating another environment file.

## Bot ingress and normalization

Aiogram authorizes the user/chat, normalizes text/voice/photo/document/video input, downloads media
to deterministic paths, computes hashes, and calls `JobService`. The service transactionally:

1. upserts user/chat/project context;
2. persists the incoming message;
3. creates a job with selected project/session and preference snapshots;
4. commits PostgreSQL;
5. publishes the job ID to the Redis Stream.

If Redis publish fails, the durable job remains discoverable/recoverable; Redis is not the source
of truth. Telegram input never directly supplies a trusted cwd.

## Persistent domain model

Core PostgreSQL entities:

- `User`: numeric Telegram identity, profile, active flag, preferences;
- `Chat`: Telegram chat identity/type;
- `Project`: trusted root and run/test/lint/build/browser policy;
- `Conversation`: user/chat/project session and summary;
- `Message`: normalized role/content/file metadata;
- `Job`: objective, state, attempts, policy, result/error, worker heartbeat, Codex IDs;
- `JobStep`: ordered planned/executed work;
- `JobEvent`: ordered durable lifecycle/progress/evidence;
- `CodexThread`: user/conversation/project App Server continuity and usage;
- `Artifact`: path, kind, MIME, size, SHA-256, Telegram ID, retention;
- `MemoryRecord`: scoped explicit/derived memory;
- worker lease/approval records defined by the migration/repository layer.

Alembic owns schema changes. Redis Streams and JSONL are transport/observability, not relational
backups.

## Job state and delivery

```text
received
  -> normalizing
  -> context_resolution
  -> memory_retrieval
  -> classifying
  -> planning
  -> planned
  -> queued
  -> running <-> waiting_external
  -> verifying
  -> reporting
  -> completed

active state -> cancel_requested -> cancelled
active state -> failed
interrupted -> recovering -> running | failed | cancelled
```

The exact allowed transitions are enforced by the state machine. Workers claim PostgreSQL leases,
heartbeat every five seconds by default, and acknowledge Redis only after durable state/events.
Timeouts exist at App Server startup, job, step, provider, Bot, and call boundaries.

On restart, pending Redis messages are reclaimed and reconciled with PostgreSQL. Terminal
PostgreSQL state wins. Cancellation persists first and interrupts Codex second, so losing a process
does not lose user intent.

## Orchestration and brain selection

Ajil is the orchestration/direct-conversation brain; Codex is the main system-management and
development brain. A selected workspace or resumed Codex thread routes normal tasks to Codex.
Ajil supplies typed gateway operations, direct chat where appropriate, STT/vision for voice/media,
and completion-call wording.

The worker does not duplicate Codex shell/filesystem/Git/Docker logic. It gives Codex bounded,
explicit context and captures protocol events. Host full access is intentional for the owner's
development deployment.

## Codex App Server

The client supervises a JSONL JSON-RPC subprocess, initializes capabilities, starts/resumes a
thread, starts a turn, handles public notifications and deterministic approval replies, persists
thread/turn IDs, streams safe commentary, and interrupts/cleans up on cancellation. Model,
reasoning, Fast service tier, sandbox, approval, network, cwd, and language are job snapshots.

See [Codex protocol](CODEX_PROTOCOL.md).

## Telegram presentation

Bot callbacks normalize to the same command handler as slash commands. Responses use inline
keyboards for contextual choices and a persistent keyboard for top-level navigation. User-visible
state comes from PostgreSQL plus live Codex quota/catalog calls with bounded Redis caches.

Redis live events update Telegram at a configured interval. Public agent commentary is forwarded;
private reasoning and credentials are not. Long history/event output is paginated.

## Artifacts and browser work

Codex performs browser/testing work in the selected project. A reserved terminal directive points
to an artifact; the worker validates existence, containment, size, MIME, and hash, persists it, and
hands it to the Bot. The Bot never sends an arbitrary Telegram-provided host path.

See [Browser verification](PLAYWRIGHT_VERIFICATION.md).

## Memory and continuity

Conversation messages/summaries, user preferences, explicit memory, project context, job outcomes,
Codex thread identity, and token usage are stored separately and retrieved by owner/project scope.
Voice SQLite is independent from control-plane PostgreSQL. See [Memory](MEMORY.md).

## Voice and private-message subsystem

`src/voice_agent` is preserved because it has real private-call validation. `LiveVoiceAssistant`
composes:

```text
Telethon signaling
  <-> PyTgCalls/NTgCalls encrypted media
  -> PCM/VAD/turn assembly
  -> Ajil STT
  -> Ajil chat + per-call context
  -> Edge TTS/ffmpeg
  -> PyTgCalls playback
```

The same process handles allowlisted private text/voice/photo/reply messages. It has independent
SQLite/JSONL auditing and content-retention policy. See [Voice architecture](architecture.md).

## Completion-call bridge

```text
terminal Codex job
  -> Ajil safe English status
  -> Redis completion Stream + publish dedup
  -> existing voice-agent consumer
  -> numeric allowlist
  -> Edge TTS status repeated exactly 3 times
  -> primary Telethon call
  -> automatic hangup + delivered marker
```

The worker never imports/opens the primary Telethon session. Recovery uses `XAUTOCLAIM`; normal
duplicates are suppressed. Call failure cannot rewrite a completed Codex result. See
[Completion calls](completion-calls.md).

## Observability

Control-plane job events are ordered in PostgreSQL and streamed through Redis/Telegram. API health
separates liveness from readiness across Ajil/database/Redis. Voice events are appended to SQLite
WAL and content-free JSONL. Logs use structured fields and safe error classes.

Sensitive prompt/result content is visible only in protected conversation/job stores and requested
history—not the voice operational audit. No raw session string, token, call key, signaling packet,
authorization header, or private reasoning belongs in logs.

## Concurrency and failure isolation

- Bot API failure does not own or terminate an active Telethon call.
- Voice failure does not alter authoritative Codex job state.
- A single primary Telethon client prevents split call signaling.
- One active voice call and async locks prevent overlapping playback.
- Redis consumer groups permit worker/voice recovery without losing PostgreSQL state.
- Bounded queues, output caps, edit intervals, and timeouts prevent unbounded memory/process use.
- Temporary inbox/audio/browser resources are deleted in `finally` paths.

## Trust model

This is a single-owner, full-access development agent. Numeric allowlists, trusted workspace roots,
path containment, redaction, and process cleanup reduce accidental risk, but they are not a
multi-tenant security boundary. Before wider exposure, complete
[Security hardening](FUTURE_SECURITY_HARDENING.md).
