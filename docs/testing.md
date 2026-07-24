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
adapter behavior, storage, Telegram-session policy, message response-mode selection, media-library
path containment, audio/image attachment classification, and the image-chat data-URL contract.

## Real STT → AI → TTS smoke test

Start Ajil and point the host process to the published port:

```bash
docker compose up -d --wait uag-gateway
UAG_BASE_URL=http://127.0.0.1:18081 \
  .venv/bin/telegram-voice-agent process-file runtime/verification/edge-smoke.ogg --language en
```

Success means the command prints a generated reply and an Ogg/Opus path. Inspect the recent
content-free events with `tail -f runtime/events.jsonl` and query SQLite only when authorized.

## UDP overlay preflight

Before a live call, provision and start the media overlay:

```bash
python3 scripts/provision_media_relay.py
docker compose --profile agent up -d --build
docker compose --profile agent ps
```

All of `voice-media-ssh-tunnel`, `voice-media-tunnel`, and `voice-agent` must be running; the
first two must be healthy. The deployment's acceptance criterion is a STUN binding request that
returns through the overlay. It proves the complete required path: GOST UDP, the SSH forward,
HTTP CONNECT through the Docker-facing endpoint for host port `3128`, and the remote UDP egress.
Run `docker compose --profile agent exec -T voice-agent python
/app/scripts/media_overlay_stun_probe.py`; it must pass. Do not bypass the proxy with a direct
remote relay connection.

## Manual inbound live-call test

1. Confirm the test peer’s numeric ID is in `VOICE_AGENT_ALLOWED_PEER_IDS`.
2. Stop every other process/container using the same `TELEGRAM_STRING_SESSION`; do not delete
   its session.
3. Ensure the test peer has consented and will answer.
4. In one terminal, tail events: `tail -f runtime/events.jsonl`.
5. Start the persistent server:

   ```bash
   docker compose --profile agent up -d
   docker compose logs -f voice-agent
   ```

6. From the configured inbound username, call the agent account. A different Telegram account must
   be declined. Speak a short sentence, a sentence with a natural mid-sentence pause, and a quiet sentence.
   Confirm one answer arrives after each completed turn, without lost initial syllables.
7. Stop with `docker compose --profile agent stop voice-agent`; verify `voip.hangup` and call
   cleanup events, then restore any paused service that used the session.

Do not call arbitrary usernames as a test. The numeric allowlist is intentionally enforced before
Telegram call setup.

## Manual private-message test

With `voice-agent` already running, use only the configured
`VOICE_AGENT_MESSAGE_USERNAME` account. Send, in order: plain text (expect text), `/voice`
followed by a question (expect a voice note), a voice note or audio attachment (expect automatic
language STT then text), and a photo or image attachment with a question (expect a Gemini vision
request then text).
Observe the content-free `message.*` events in `runtime/events.jsonl`. When transcript retention
is authorized, query `message_turns` in the SQLite database for the stored transcript/reply pair.

To test outbound image/video delivery, first add an authorized local file and its manifest entry as
described in [Private messaging](messaging.md#local-image-and-video-sending). Ask a question that
clearly maps to that asset. Confirm `message.media.sent` and that Telegram receives the original
file; no image/video generation path exists.

Reply to a text message, a photo, and a voice note with a follow-up question. Confirm
`message.reply_context.loaded` for text/photo references and `message.reply_context.stt.*` for the
voice reference. The model prompt receives the referenced text/transcript and every referenced
image, while the follow-up message alone chooses text versus voice output.

## What a successful live test proves

`call.active` proves the PyTgCalls media connection completed. `telegram.raw.call_update` shows
that Telegram call signaling reached the owning session, but by itself does not prove media
connectivity. If the call remains at encryption-key exchange or errors before `call.active`, use
[Troubleshooting](troubleshooting.md#telegram-voip-handshake-and-media).
