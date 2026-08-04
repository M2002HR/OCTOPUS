# OCTOPUS

**A durable Telegram-based control plane for AI-assisted software engineering.**

OCTOPUS lets a trusted owner operate development workspaces, persistent Codex sessions, browser checks, files, voice flows, and long-running jobs from Telegram. It combines a user-facing bot with a durable backend, queue-based workers, AI-provider orchestration, and a separate Telethon voice service.

> Designed as a single-owner engineering system with explicit trust boundaries—not as a public multi-tenant sandbox.

## Engineering highlights

- Durable job processing with **PostgreSQL**, **Redis Streams**, leases, heartbeats, cancellation, and restart recovery
- Persistent project and session management for Codex App Server
- Telegram Bot API interface plus a separately owned Telethon voice process
- AI routing, STT, vision, and status generation through Ajil Unified AI Gateway
- File, screenshot, image, document, video metadata, and reply-context handling
- Scoped conversation, user, project, and outcome memory
- Browser-driven project inspection with returned screenshots
- Structured health checks, audit events, privacy boundaries, and integration-test harnesses
- Containerized deployment with Docker Compose and operational documentation

## Technology

`Python 3.12` · `FastAPI` · `PostgreSQL` · `Redis Streams` · `Docker Compose` · `Alembic` · `Telegram Bot API` · `Telethon` · `PyTgCalls` · `Playwright` · `FFmpeg` · `Edge TTS` · `pytest` · `mypy` · `Ruff`

## Architecture

```text
Telegram Bot
  │
  ├── project/session commands
  ├── files, media, logs, history
  └── job control
        │
        ▼
PostgreSQL ── durable state and audit records
        │
        ▼
Redis Streams ── queued work and live events
        │
        ▼
Worker / Orchestrator
  ├── Codex App Server
  ├── Ajil Unified AI Gateway
  ├── trusted workspaces and browser tools
  └── artifact delivery

Terminal job event
  ▼
Completion-call stream
  ▼
Telethon voice agent ── STT / chat / TTS / hangup
```

PostgreSQL is the source of truth. Redis is used for delivery, live events, bounded caches, and completion-call dispatch.

## Key capabilities

### Durable execution

Jobs and events survive process restarts. Workers use leases and heartbeats, support cancellation, and recover interrupted work without relying on an in-memory queue.

### Workspace-aware AI sessions

The owner can discover approved projects, create or resume persistent Codex sessions, inspect current state, choose model/reasoning settings, and submit natural-language engineering tasks.

### Operational visibility

The bot exposes job status, logs, history, token usage, health information, diffs, reviews, and browser screenshots. Public progress is separated from private model reasoning.

### Voice and private-account integration

A dedicated Telethon process owns the primary private account session. It handles approved calls and compatibility messages without sharing the session with the worker process.

## Quick start

### Prerequisites

- Linux
- Docker Compose v2
- FFmpeg
- Python 3.12 for native development
- Authenticated Codex runtime
- Telegram Bot and Telethon credentials
- Ajil provider credentials

### Run with Docker Compose

```bash
git submodule update --init --recursive
cp .env.example .env
chmod 600 .env
# Add secrets and approved IDs to .env and config/agent.yaml.

docker compose --profile agent config --quiet
docker compose --profile agent build
docker compose --profile agent up -d
docker compose --profile agent ps
```

Health checks:

```bash
curl --noproxy '*' -fsS http://127.0.0.1:18090/ready
curl --noproxy '*' -fsS http://127.0.0.1:8080/health
```

## Typical Telegram workflow

1. Send `/start`.
2. Select an approved project with `/projects`.
3. Create or resume a persistent session.
4. Review model, reasoning, permissions, and service-tier settings.
5. Submit an engineering task.
6. Follow safe progress events.
7. Inspect history, jobs, logs, diffs, or screenshots.
8. Retrieve generated artifacts through Telegram.

## Main command groups

| Area | Commands |
| --- | --- |
| Navigation | `/start`, `/projects`, `/project`, `/new`, `/resume` |
| State | `/status`, `/usage`, `/history`, `/jobs`, `/job`, `/logs` |
| Control | `/stop`, `/permissions`, `/model`, `/reasoning`, `/fast` |
| Inspection | `/diff`, `/review`, `/browser` |
| Memory | `/remember`, `/memory`, `/forget` |
| Settings | `/config`, `/language`, `/completion_call` |

See [docs/TELEGRAM_COMMANDS.md](docs/TELEGRAM_COMMANDS.md) for the complete command contract.

## Repository structure

| Path | Purpose |
| --- | --- |
| `src/telegram_codex_agent/` | Bot API, jobs, worker, sessions, memory, projects, Codex/Ajil integration |
| `src/voice_agent/` | Telethon calls/messages, VAD, STT/TTS, audit, completion consumer |
| `modules/ajil_uag/` | Pinned Ajil Unified AI Gateway submodule |
| `alembic/` | PostgreSQL schema migrations |
| `config/agent.yaml` | Non-secret policy and allowlist configuration |
| `scripts/` | Bootstrap, diagnostics, deployment, media relay, approved live tests |
| `tests/`, `tests_agent/` | Control-plane and voice-agent test suites |
| `docs/` | Architecture, operations, deployment, testing, and handoff guides |

## Development verification

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e '.[dev]'

.venv/bin/ruff check src tests tests_agent scripts
.venv/bin/mypy src
.venv/bin/pytest -q
docker compose --profile agent config --quiet
git diff --check
```

External Codex, Ajil, Telegram, Playwright, and two-account call tests are opt-in and require approved identities and content-safe evidence.

## Security model

OCTOPUS intentionally grants broad access to one trusted owner. Its controls reduce accidental misuse but do not provide strong isolation for untrusted users.

Never commit:

- `.env` files or API tokens
- Telegram session files
- Codex authentication material
- proxy or relay credentials
- private transcripts, screenshots, or live audio
- runtime artifacts containing user content

## Documentation

- [Documentation index](docs/README.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Configuration](docs/configuration.md)
- [Deployment](docs/DEPLOYMENT.md)
- [Operations runbook](docs/RUNBOOK.md)
- [Completion calls](docs/completion-calls.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Maintainer handoff](docs/HANDOFF.md)

## Project status

OCTOPUS is an actively developed personal engineering platform. It demonstrates durable backend design, queue-based orchestration, AI-service integration, Telegram automation, voice infrastructure, and production-minded operational controls.