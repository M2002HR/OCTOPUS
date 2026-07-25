# OCTOPUS — Telegram Codex Agent

OCTOPUS is a persistent personal AI control plane for an owner-operated development machine. The
owner works through Telegram; OCTOPUS selects the right workspace and persistent Codex session,
queues/recover jobs, streams safe progress, invokes Codex App Server as the primary execution
brain, uses Ajil for orchestration/STT/provider routing, returns files/screenshots, and preserves a
validated Telethon private-call/message subsystem.

The configured default model is `gpt-5.6-terra`, default reasoning is `high`, and the control/voice
defaults are English.

## What it does

- Codex CLI-style Telegram control center with inline and persistent keyboards.
- Workspace discovery beneath an explicit trusted root, normally `~/Code`.
- Persistent `/new` and `/resume` Codex App Server threads per user/project.
- Durable PostgreSQL jobs/events with Redis Streams, leases, heartbeats, cancellation, and restart
  recovery.
- Model, reasoning, Fast service tier, permission, language, live-log, and completion-call settings.
- `/status`, selected-session token usage, `/usage` authenticated weekly quota, `/history`, and
  paginated logs.
- Public Codex commentary/tool progress at `info`/`debug`; private reasoning remains private.
- Text, voice note, image, document, video metadata, reply context, and validated artifact delivery.
- Codex-driven project browser/Chrome Lab checks with screenshots returned to Telegram.
- Scoped persistent conversation/user/project/outcome memory.
- Ajil direct chat, STT, vision/provider routing, and safe terminal-status wording.
- Primary Telethon account for inbound/outbound private calls and allowlisted private messages.
- Optional completion call: after any terminal Codex outcome, call the opted-in Bot user, speak
  Ajil's English status exactly three times, then hang up.
- Structured health, audit, privacy boundaries, real two-session test harnesses, and Docker
  restart policy.

## Bot versus Telethon

| Interface | Use |
| --- | --- |
| Telegram Bot API | Normal user interface: projects, Codex sessions/tasks, settings, logs, history, memory, files |
| Primary Telethon session | Private calls, voice conversation, compatibility private messages, completion calls |
| Second Telethon session | Approved real end-to-end testing only |

The Bot does not replace Telethon because Bot API cannot place private account calls. The worker
never opens the primary Telethon session; one persistent `voice-agent` process owns it exclusively.

## Architecture

```text
Telegram Bot
  -> PostgreSQL durable state
  -> Redis job Stream
  -> worker/orchestrator
       +-> Codex App Server
       +-> Ajil Unified AI Gateway
       +-> trusted workspace/browser/tools
  -> Telegram results, logs, and artifacts

terminal Codex job
  -> Ajil safe status
  -> Redis completion-call Stream
  -> primary Telethon voice-agent
  -> status x3
  -> automatic hangup

incoming Telethon call
  -> PyTgCalls PCM/VAD
  -> Ajil STT/chat
  -> Edge TTS
  -> caller
```

PostgreSQL is the control-plane source of truth. Redis provides delivery, live events, and bounded
caches. `modules/ajil_uag` is a pinned recursive submodule.

## Quick start

Prerequisites: Linux, Docker Compose v2, FFmpeg, Python 3.12 for native development, an
authenticated Codex runtime, Telegram Bot/Telethon credentials, Ajil provider credentials, and
approved allowlists.

```bash
git submodule update --init --recursive
cp .env.example .env
chmod 600 .env
# Fill secrets and host-specific values in .env.
# Set telegram.allowed_user_ids/chat_ids/usernames in config/agent.yaml.

docker compose --profile agent config --quiet
docker compose --profile agent build
docker compose --profile agent up -d
docker compose --profile agent ps

curl --noproxy '*' -fsS http://127.0.0.1:18090/ready
curl --noproxy '*' -fsS http://127.0.0.1:8080/health
```

`config/agent.yaml` is the only non-secret policy file; root `.env` is the only secret/machine
environment file.

## First Telegram workflow

1. Send `/start` to the Bot.
2. Open `/projects` and choose an approved workspace.
3. Send `/new` or select `/resume`.
4. Review `/status`, `/model`, `/reasoning`, `/fast status`, and `/permissions`.
5. Send a natural task.
6. Follow public Codex commentary.
7. Inspect `/history`, `/jobs`, or `/logs JOB_ID`.
8. Use `/browser screenshot` when visual evidence is required.

Completion calls are off per user until `/completion_call on`. They also require global policy and
the Bot user's numeric ID in `VOICE_AGENT_ALLOWED_PEER_IDS`; the preference applies to newly
created Codex jobs.

## Important commands

| Area | Commands |
| --- | --- |
| Navigation | `/start`, `/projects`, `/project SLUG`, `/new`, `/resume` |
| State | `/status`, `/usage`, `/history`, `/jobs`, `/job JOB_ID`, `/logs` |
| Control | `/stop JOB_ID`, `/permissions`, `/model`, `/reasoning`, `/fast` |
| Settings | `/config`, `/language`, `/completion_call` |
| Inspection | `/diff`, `/review`, `/browser` |
| Memory | `/remember`, `/memory`, `/forget` |

See [Telegram commands](docs/TELEGRAM_COMMANDS.md) for exact behavior.

## Voice and media

The persistent service accepts only startup-resolved usernames whose numeric IDs are allowlisted.
It speaks the English introduction “Hello, yes?”, captures complete utterances using configurable
VAD, performs Ajil STT/chat, and replies through Edge TTS.

Telegram VoIP media is independent from Telethon signaling. On this deployment, UDP is captured in
the voice namespace and transported through GOST → SSH → required HTTP CONNECT proxy. A successful
MTProto connection alone does not prove call media.

## Development and verification

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e '.[dev]'

RUFF_CACHE_DIR=/tmp/octopus-ruff-cache .venv/bin/ruff check src tests tests_agent scripts
PYTHONPYCACHEPREFIX=/tmp/octopus-pycache \
  .venv/bin/python -m compileall -q src scripts tests tests_agent
.venv/bin/mypy src
.venv/bin/pytest -q
docker compose --profile agent config --quiet
git diff --check
```

External Ajil, Codex, Telegram, Playwright, two-account call/message, and completion-call tests are
opt-in and must use approved identities. Never claim an integration passed without recorded
content-safe evidence.

## Repository layout

| Path | Purpose |
| --- | --- |
| `src/telegram_codex_agent/` | Bot/API, jobs, worker, Codex/Ajil integration, memory, projects |
| `src/voice_agent/` | Primary Telethon calls/messages, STT/TTS, VAD, audit, completion consumer |
| `modules/ajil_uag/` | Pinned recursive Ajil Unified AI Gateway submodule |
| `config/agent.yaml` | Checked-in non-secret policy |
| `.env.example` | Complete root environment-name contract |
| `alembic/` | PostgreSQL migrations |
| `scripts/` | Bootstrap, doctor, media relay, systemd, and approved live tests |
| `tests/`, `tests_agent/` | Voice and control-plane test suites |
| `generated/codex/` | Installed App Server protocol schemas |
| `docs/` | Architecture, decisions, deployment, operations, commands, testing, handoff |
| `runtime/` | Ignored voice audit/temp/live-test media |
| `data/artifacts/` | Managed control-plane artifacts |

## Security and privacy

Development full access is intentional. It is suitable only for one trusted owner. Numeric
allowlists, trusted workspace roots, path containment, redacted events, and cleanup reduce
accidental risk but do not create a multi-tenant sandbox.

Do not commit `.env`, Telegram sessions, Bot/API/provider tokens, Codex auth, proxy/relay
credentials, runtime transcripts, screenshots with secrets, or live audio. Voice JSONL excludes
content; optional SQLite transcript tables and PostgreSQL messages/jobs remain sensitive.

## Documentation

Start with [the documentation index](docs/README.md), then read:

- [System architecture](docs/ARCHITECTURE.md)
- [Configuration](docs/configuration.md)
- [Platform deployment](docs/DEPLOYMENT.md)
- [Operations runbook](docs/RUNBOOK.md)
- [Completion calls](docs/completion-calls.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Maintainer handoff](docs/HANDOFF.md)

`COMPLETE_CODEX_IMPLEMENTATION_PROMPT.md` is retained as the historical product contract; current
operating documentation and code are authoritative.
