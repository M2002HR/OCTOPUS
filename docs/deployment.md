# Deployment

## Prerequisites

- Python 3.11 or newer and `ffmpeg`.
- Docker Engine with Compose v2 for the bundled Ajil stack.
- A Telegram user authorization that is exclusively owned during a call.
- Outbound connectivity to Telegram signaling and VoIP media infrastructure. A TCP/SOCKS proxy
  for Telethon alone is insufficient for media; verify UDP and fallback TCP requirements with the
  network operator.

## Local setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
python scripts/bootstrap_env.py
docker compose up -d --wait uag-gateway
.venv/bin/ruff check .
.venv/bin/mypy src
.venv/bin/pytest -q
```

`bootstrap_env.py` reads the approved sibling projects by default. Supply explicit `--gerdoo`,
`--triak`, and `--output` paths for another machine. It does not replace an existing `.env`.

## Docker services

`docker compose up -d --wait uag-gateway` starts `uag-redis` and the pinned Ajil gateway. The
`voice-agent` service is deliberately behind the `agent` profile. Its `serve` command accepts only
the startup-resolved `VOICE_AGENT_INBOUND_USERNAME`; it does not dial anyone. It has
`restart: unless-stopped` so it returns after a process or Docker restart.

Before enabling it, stop every other client/container using the same Telethon string session. Then
start and inspect the persistent service:

```bash
docker compose --profile agent up -d voice-agent
docker compose ps
docker compose logs -f voice-agent
```

To intentionally stop it, use `docker compose --profile agent stop voice-agent`. Do not run an
outbound `call` command from another process with the same session while the server is online.

To open an interactive shell in the built agent image without starting the persistent command:

```bash
docker compose --profile agent run --rm voice-agent bash
```

Run a non-call end-to-end verification from the host, pointing at the published gateway port:

```bash
UAG_BASE_URL=http://127.0.0.1:18081 \
  .venv/bin/telegram-voice-agent process-file runtime/verification/edge-smoke.ogg --language fa
```

## Updating Ajil

Ajil is a git submodule pinned by the root repository. Its provider modules are nested submodules.
Update it only deliberately, then initialize nested modules and rerun all verification:

```bash
git submodule update --init --recursive
docker compose build uag-gateway
docker compose up -d --wait uag-gateway
```

The root project uses the Ajil gateway over its HTTP contract. Keep project-specific policy in the
root `.env`, never in the submodule working tree.

## Production notes

Use a dedicated Telegram authorization for the agent, a protected persistent volume for
`RUNTIME_DIR`, secret injection appropriate to the deployment platform, and a process supervisor.
Restrict database access, monitor error events, and obtain informed consent before conversation
processing. This repository does not implement an unattended dialer.
