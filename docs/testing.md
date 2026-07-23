# Testing and verification

Testing is layered so a failure identifies the smallest faulty boundary.

## Fast automated suite

```bash
.venv/bin/ruff check .
.venv/bin/mypy src
.venv/bin/pytest -q
docker compose config --quiet
```

The tests cover configuration validation, allowlist behavior, PCM turn construction (including
pre-roll, hysteresis, noise rejection, silence completion, duration calculation, and maximum
length), orchestration event order, transcript-retention policy, Ajil request contracts, Edge TTS
adapter behavior, storage, and Telegram-session policy.

## Real STT → AI → TTS smoke test

Start Ajil and point the host process to the published port:

```bash
docker compose up -d --wait uag-gateway
UAG_BASE_URL=http://127.0.0.1:18081 \
  .venv/bin/telegram-voice-agent process-file runtime/verification/edge-smoke.ogg --language fa
```

Success means the command prints a generated reply and an Ogg/Opus path. Inspect the recent
content-free events with `tail -f runtime/events.jsonl` and query SQLite only when authorized.

## Manual inbound live-call test

1. Confirm the test peer’s numeric ID is in `VOICE_AGENT_ALLOWED_PEER_IDS`.
2. Stop every other process/container using the same `TELEGRAM_STRING_SESSION`; do not delete
   its session.
3. Ensure the test peer has consented and will answer.
4. In one terminal, tail events: `tail -f runtime/events.jsonl`.
5. Start the persistent server:

   ```bash
   docker compose --profile agent up -d voice-agent
   docker compose logs -f voice-agent
   ```

6. From the configured inbound username, call the agent account. A different Telegram account must
   be declined. Speak a short sentence, a sentence with a natural mid-sentence pause, and a quiet sentence.
   Confirm one answer arrives after each completed turn, without lost initial syllables.
7. Stop with `docker compose --profile agent stop voice-agent`; verify `voip.hangup` and call
   cleanup events, then restore any paused service that used the session.

Do not call arbitrary usernames as a test. The numeric allowlist is intentionally enforced before
Telegram call setup.

## What a successful live test proves

`call.active` proves the PyTgCalls media connection completed. `telegram.raw.call_update` shows
that Telegram call signaling reached the owning session, but by itself does not prove media
connectivity. If the call remains at encryption-key exchange or errors before `call.active`, use
[Troubleshooting](troubleshooting.md#telegram-voip-handshake-and-media).
