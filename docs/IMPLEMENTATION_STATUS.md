# Implementation status

This file distinguishes implemented behavior from prepared schema/policy and historical prompt
requirements. Evidence must come from tests or recorded live runs.

## Implemented

### Foundation and deployment

- [x] Unified `telegram-codex-agent` package and root CLI
- [x] Single checked-in `config/agent.yaml` plus single root `.env` contract
- [x] Recursive Ajil submodule at `modules/ajil_uag`
- [x] Python 3.12 Docker images and full Compose profile
- [x] PostgreSQL/pgvector, Redis AOF, Ajil, migration, API, Bot, worker, voice, media sidecars
- [x] Alembic initial schema and repository primitives
- [x] Health/readiness/version/redacted-config/job API
- [x] Native/systemd development templates and doctor/smoke commands

### Telegram control plane

- [x] Aiogram polling adapter and command registration
- [x] Persistent/inline control-center keyboards
- [x] Numeric user/chat allowlist support
- [x] Text, voice/audio, photo/image, document, video metadata normalization
- [x] Deterministic inbox paths, hashes, and Telegram artifact uploads
- [x] Workspace discovery/registry and explicit selection
- [x] `/new`, real `/resume`, `/status`, `/usage`, `/history`, `/jobs`, `/job`, `/stop`, `/logs`
- [x] Model, reasoning, Fast, permissions, language, progress, and completion-call settings
- [x] `/diff`, `/review`, and Codex-driven browser screenshot/test/artifact tasks
- [x] Public Codex commentary streaming without private reasoning

### Jobs and Codex

- [x] Durable PostgreSQL job/message/event state
- [x] Redis Streams delivery and live events
- [x] Validated state machine, lease, heartbeat, timeout, cancellation, pending recovery
- [x] Codex App Server JSON-RPC initialization and process supervision
- [x] Thread start/resume, turn start/interrupt, event capture, cleanup
- [x] Deterministic noninteractive approval bridge
- [x] Persistent thread/turn IDs and token usage
- [x] Authenticated account weekly rate-limit reporting/cache
- [x] Catalog-backed Fast tier
- [x] Validated file directive, containment, hash, metadata, Telegram handoff

### Ajil and memory

- [x] Typed Ajil health/models/chat/responses/embedding/image/STT/TTS/orchestration client surface
- [x] Structured/fallback handling for used orchestration paths
- [x] Direct chat/provider routing and voice STT/vision integration
- [x] Scoped messages, summaries, preferences, explicit memory commands, outcomes
- [x] Project/session ownership and Codex continuity

### Telethon compatibility

- [x] Sole primary Telethon session ownership
- [x] Numeric allowlisted inbound/outbound private calls
- [x] PyTgCalls/NTgCalls media, VAD, multi-turn STT/chat/TTS
- [x] English-only voice/message STT/TTS contract and non-persona introduction
- [x] Text, voice note, photo vision, reply context, approved local image/video messages
- [x] SQLite WAL/JSONL audit and transcript retention modes
- [x] UDP-over-GOST-over-SSH-over-proxy media overlay and STUN preflight
- [x] Two-session real call/message test harnesses

### Codex completion calls

- [x] Global policy and per-user Bot opt-in
- [x] Job-time preference/target snapshot
- [x] All terminal state/category classification
- [x] Ajil-authored varied English status with validation/redaction/fallback
- [x] Atomic Redis publish dedup and bounded Stream
- [x] Primary-session allowlisted call, exact three repetitions, automatic hangup
- [x] Retry, busy handling, delivered dedup, invalid payload handling
- [x] Pending recovery on every poll after fast restart
- [x] Content-free audit and temporary media cleanup
- [x] Automated category/consumer/privacy/recovery tests
- [x] Real second-session Codex → call → recorded PCM → STT repetition → auto-hangup evidence

## Partial or policy-backed

- [~] Browser modes/configuration exist; execution relies on selected workspaces and Codex rather
  than a dedicated long-running Playwright manager.
- [~] Artifact expiry metadata exists; automatic deletion requires an external task while scheduler
  is disabled.
- [~] Memory schema supports embeddings, but current production retrieval is scoped/lexical rather
  than a proven semantic-vector pipeline.
- [~] Optional Prometheus/Grafana services exist; complete dashboards/alerts and hardened access are
  deployment work.
- [~] Webhook configuration validates, while the deployed/default Bot transport is polling.

## Deliberately unavailable/not claimed

- [ ] Multi-user/untrusted production hardening
- [ ] General unattended Telegram dialer
- [ ] Exactly-once external call delivery across a post-playback process crash
- [ ] Active scheduler service (`runtime scheduler` exits as disabled)
- [ ] Automatic desktop recording daemon
- [ ] Built-in video frame/semantic analysis in Telethon compatibility messaging
- [ ] Application-managed encryption at rest
- [ ] Exposure of private Codex chain-of-thought
- [ ] Arbitrary Telegram-provided filesystem roots or artifact paths

## Current verification baseline

The completion-call implementation was validated in the supported Python 3.12 image with 79
passing tests, full-repository Ruff, compileall, Compose configuration, service readiness, Ajil
health, Redis pending/lag checks, a real second-session terminal call, STT repetition evidence,
automatic hangup, and restart recovery. Markdown lint also passes across the documentation set.

Type checking remains explicit technical debt: host mypy 2.1.0 crashes internally before analysis;
mypy 1.19.1 completes and reports 39 pre-existing strict errors after the completion-call-specific
errors were corrected. This gate is not marked passed. Re-run and reduce the debt using the
[Test matrix](TEST_MATRIX.md) on future release commits.
