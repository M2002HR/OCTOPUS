# Telegram Voice Agent

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
  .venv/bin/telegram-voice-agent process-file runtime/verification/edge-smoke.ogg --language fa
```

To run the persistent inbound assistant, set `VOICE_AGENT_INBOUND_ENABLED=true`, set
`VOICE_AGENT_INBOUND_USERNAME`, and ensure its resolved numeric ID is in
`VOICE_AGENT_ALLOWED_PEER_IDS`. The username is resolved once at startup; every other caller is
rejected.

```bash
docker compose --profile agent up -d voice-agent
docker compose logs -f voice-agent
```

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
