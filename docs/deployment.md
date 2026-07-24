# Voice subsystem deployment

This document covers the primary Telethon voice/message service. For the complete Bot/Codex stack
see [Platform deployment](DEPLOYMENT.md).

## Prerequisites

- Python 3.12 and FFmpeg;
- Docker Engine with Compose v2;
- an exclusively owned Telegram user authorization;
- numeric peer allowlist and configured inbound/message usernames;
- healthy Ajil STT/chat provider routes;
- outbound Telegram signaling and VoIP media access;
- the media overlay when direct UDP is unavailable.

A Telethon TCP/SOCKS proxy carries signaling only. It does not prove PyTgCalls media access.

## Configuration

Use the root `.env`; never create a voice or submodule environment file. Required groups are
documented in [Configuration](configuration.md):

- `TELEGRAM_API_*`, `TELEGRAM_STRING_SESSION`, optional signaling proxy;
- `VOICE_AGENT_ALLOWED_PEER_IDS`, inbound/message usernames and enable flags;
- English language/system prompt, VAD/audio settings;
- Ajil and Edge TTS values;
- completion-call Redis/retry values;
- runtime/audit paths;
- media-overlay values where required.

Before enabling the service, stop every other client/container using the primary session.

## Build and start

```bash
docker compose --profile agent build voice-agent
docker compose --profile agent up -d \
  voice-media-ssh-tunnel voice-media-tunnel voice-agent
docker compose --profile agent ps
docker compose logs -f voice-agent
```

The service resolves usernames to numeric IDs at startup and rejects a configured username whose
ID is absent from `VOICE_AGENT_ALLOWED_PEER_IDS`. It listens for approved inbound calls/messages.
It may place an outbound call only for a validated Redis completion request whose protected
numeric target also passes the allowlist.

The container uses `restart: unless-stopped`, mounts `./runtime` at `/runtime`, points Ajil to
`http://ajil_gateway:8080`, and points completion-call Redis to DB 1.

## Non-call pipeline smoke

```bash
UAG_BASE_URL=http://127.0.0.1:8080 \
  .venv/bin/telegram-voice-agent \
  process-file runtime/verification/edge-smoke.ogg --language en
```

Success requires STT, Ajil chat, Edge TTS, and an Ogg/Opus result without opening Telegram calls.

## Service ownership and updates

Do not run `telegram-voice-agent call`, a session-generation script, or another Telethon client
with the primary session while `voice-agent` is running. The approved second session is a peer/test
driver, not another owner.

For a source-only update:

1. confirm no active call;
2. check completion-call `XPENDING=0`;
3. build the voice image;
4. recreate only `voice-agent`;
5. wait for Telethon connected and service-ready logs;
6. recheck Redis pending/lag and Ajil health.

## Updating Ajil

Ajil is pinned recursively:

```bash
git submodule update --init --recursive
docker compose build ajil_gateway
docker compose up -d --wait ajil_gateway
```

Do not edit `modules/ajil_uag` directly from the root. Reproduce a required change upstream and
update the pinned commit.

## Stop and cleanup

```bash
docker compose --profile agent stop \
  voice-agent voice-media-tunnel voice-media-ssh-tunnel
```

Graceful shutdown hangs up active media, stops consumers/handlers, disconnects Telethon, closes
audit storage, and removes temporary per-call files. Do not delete the runtime/database or Compose
volumes unless retention policy explicitly requires it.

## Production notes

Use a dedicated Telegram authorization, encrypted/protected runtime storage, credential rotation,
log monitoring, informed consent, and an external retention policy. Completion calls are
per-user opt-in, job-triggered, allowlisted, and bounded; this is not a general dialer.
