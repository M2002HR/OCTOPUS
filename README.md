# Telegram Voice Agent

## Telegram Codex platform

The repository now also contains `src/telegram_codex_agent`: a persistent Bot
API agent that uses PostgreSQL, Redis Streams, Ajil, and the local Codex App
Server. It is deliberately separate from the proven private-call service
below, so Bot API work cannot disrupt Telegram voice calls.

```bash
docker compose --profile agent up -d
curl --noproxy '*' http://127.0.0.1:18090/ready
```

Choose an explicit project with `/projects` then `/project <slug>` before a
code task. Detailed operations are in [docs/RUNBOOK.md](docs/RUNBOOK.md).

The Bot control center mirrors the core Codex CLI workflow:

- `/new` creates a fresh Codex conversation in the selected workspace.
- `/resume` lists saved threads and resumes the selected App Server thread.
- `/status`, `/permissions`, `/model`, and `/reasoning` expose the active execution context.
- `/fast`, `/fast on`, `/fast off`, and `/fast status` control the catalog-backed
  Codex Fast service tier for future jobs; the same control is available in Settings.
- `/status` includes the selected thread's live state, persisted token/context usage,
  and the current Codex account quota.
- `/history` shows the active session's prompts, results, and paginated durable job logs.
- `/usage` reads the authenticated Codex account's weekly limit, remaining
  percentage, and reset time. It is independent of the selected session.
- `/language` changes voice transcription and AI response language while keeping the control UI in English.
- `/logs` controls live `error`, `info`, `debug`, or `off` progress; `/logs <job-id>` shows the durable event history.
- `/diff` and `/review` run read-only Codex inspections.
- `/browser` runs the workspace's Chrome Lab/browser workflow and returns screenshots or reports to Telegram.

The persistent keyboard keeps workspaces, sessions, browser tools, jobs, logs,
review, settings, and cancellation one tap away. Telegram's slash-command menu
is registered automatically when the Bot starts. With a workspace selected,
Codex is the primary execution brain and Ajil remains the orchestration/direct
conversation layer.

At `info` or `debug`, Telegram receives Codex's public intermediate
`agentMessage` commentary as well as lifecycle and tool summaries. Private
reasoning items and raw credentials are never forwarded.

The `/resume` picker distinguishes the selected thread from execution state:
`RUNNING` means a job is in flight; `IDLE · last completed`, `IDLE · last
failed`, or `IDLE · no tasks` means the thread has no active work. Every row
also links directly to that thread's history.

Telegram Voice Agent is a modular, auditable assistant for one-to-one Telegram calls. It
uses the existing Telethon string session, PyTgCalls/NTgCalls for private-call media, Ajil
Unified AI Gateway for speech-to-text and conversation, and Edge TTS for response speech.

The project is deliberately safe by default:

- No outbound call is automatic.
- A call is allowed only after an explicit command and numeric peer allowlist check.
- The assistant introduces itself as automated by default.
- Secrets are read only from the root `.env`, are never committed, and are redacted from
  structured event payloads.

## Quick start

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
python scripts/bootstrap_env.py  # creates .env once; never prints secret values
.venv/bin/pytest -q

# Start Ajil from the root configuration.
docker compose up -d --wait uag-gateway

# Verify the complete STT -> AI -> TTS pipeline without a call.
UAG_BASE_URL=http://127.0.0.1:18081 \
  .venv/bin/telegram-voice-agent process-file runtime/verification/edge-smoke.ogg --language en
```

To run the persistent inbound assistant, set `VOICE_AGENT_INBOUND_ENABLED=true`, set
`VOICE_AGENT_INBOUND_USERNAME`, and ensure its resolved numeric ID is in
`VOICE_AGENT_ALLOWED_PEER_IDS`. The username is resolved once at startup; every other caller is
rejected.

```bash
docker compose --profile agent up -d voice-agent
docker compose logs -f voice-agent
```

## UDP media overlay

This host blocks direct outbound UDP, while Telegram calls require it for media. The private
overlay captures the voice-agent namespace's UDP and carries it through an SSH connection. That
SSH connection uses the required HTTP CONNECT proxy on port 3128.

```bash
python3 scripts/provision_media_relay.py
docker compose --profile agent up -d --build
```

The remote relay binds only to loopback; no public relay port is opened. See
[docs/media-overlay.md](docs/media-overlay.md) for topology, security, configuration, and the
STUN preflight procedure.

## Private messages

The persistent service also handles text, voice notes, and photos from the one configured user.
Replies are text by default, with explicit `/voice` and `/text` overrides. It can send only
approved existing images/videos from a local manifest; it never generates media. See
[docs/messaging.md](docs/messaging.md).

Read [docs/README.md](docs/README.md) before running a live call. It contains the architecture,
configuration reference, deployment guide, testing workflow, operational runbook, and known
Telegram VoIP networking constraints.

## Project layout

| Path | Purpose |
| --- | --- |
| `src/voice_agent/` | Domain, application orchestration, adapters, VoIP engine, CLI |
| `vendor/Ajil_Unified_AI_Gateway/` | Pinned Ajil submodule, including its nested modules |
| `tests/` | Fast isolated unit and adapter-contract tests |
| `docs/` | Complete operator and developer documentation |
| `runtime/` | Ignored local database, JSONL events, temporary WAV turns, and generated Ogg files |
| `.env` | Sole runtime configuration source; local only |

## Verification status

The local suite runs Ruff, strict mypy, and pytest. The deployment smoke test exercises real
Edge TTS, Ajil STT, Ajil chat, and Ogg/Opus output. A successful media call additionally needs
exclusive ownership of the Telethon authorization and outbound access to Telegram's call
reflectors; see [VoIP troubleshooting](docs/troubleshooting.md#telegram-voip-handshake-and-media).
