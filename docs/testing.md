# Testing and verification

Testing is layered so a failure identifies the smallest boundary. External tests are never implied
by unit success.

## Deterministic suite

```bash
RUFF_CACHE_DIR=/tmp/octopus-ruff-cache ruff check src tests tests_agent scripts
PYTHONPYCACHEPREFIX=/tmp/octopus-pycache \
  python -m compileall -q src scripts tests tests_agent
python -m mypy src
python -m pytest -q
docker compose --profile agent config --quiet
git diff --check
```

Run in Python 3.12/container when the host differs. Tests cover configuration, state transitions,
repositories, queue/recovery, Codex contracts, Bot commands/callbacks, normalization, settings,
memory, artifacts, VAD/audio, Ajil adapters, Telethon authorization, messages/replies, and
completion calls.

## Infrastructure and smoke tests

```bash
docker compose up -d --wait postgres redis ajil_gateway
make doctor
make ajil-smoke
make codex-smoke
```

Codex smoke is read-only. Agent readiness:

```bash
curl --noproxy '*' -fsS http://127.0.0.1:18090/ready
curl --noproxy '*' -fsS http://127.0.0.1:8080/health
```

## STT → Ajil → TTS without a call

```bash
UAG_BASE_URL=http://127.0.0.1:8080 \
  .venv/bin/telegram-voice-agent \
  process-file runtime/verification/edge-smoke.ogg --language en
```

Success proves input decoding, English STT, Ajil chat, Edge TTS, and Ogg/Opus generation, not
Telegram signaling/media.

## Bot/Codex live scenario

Use only an approved test Telegram identity:

1. `/start`;
2. select an approved project;
3. verify model/reasoning/Fast/permissions/language settings;
4. `/new`;
5. submit a read-only Codex task;
6. confirm public intermediate commentary;
7. inspect `/status`, `/usage`, `/history`, `/jobs`, and `/logs`;
8. cancel a bounded test and confirm `turn/interrupt`;
9. request a workspace screenshot and verify Telegram attachment.

Test text, voice note, image, document/video metadata, and reply input independently.

## UDP overlay preflight

```bash
python3 scripts/provision_media_relay.py
docker compose --profile agent up -d --build
docker compose --profile agent exec -T voice-agent \
  python /app/scripts/media_overlay_stun_probe.py
```

Voice/media sidecars must be healthy. Passing proves the in-namespace GOST UDP → SSH → HTTP
CONNECT → remote UDP path.

## Manual inbound voice

1. Confirm test peer numeric ID and username policy.
2. Ensure only `voice-agent` owns the primary session.
3. Tail `runtime/events.jsonl`.
4. Call primary from the approved second account.
5. Confirm “Hello, yes?” in English.
6. Speak short, paused, quiet, and multi-turn English utterances.
7. Confirm each complete turn reaches STT/chat/TTS/playback without repeated “not understood.”
8. Hang up and confirm media cleanup.

`call.active` plus received frames/turns and heard TTS prove real media. Signaling updates alone do
not.

## Private message matrix

From the configured account send:

- plain text and `/text`;
- `/voice` request;
- voice note/audio;
- photo with question;
- reply to text, photo, and voice note;
- approved media-library request;
- oversized/unsupported attachment negative cases.

Confirm response mode, vision/STT context, reply association, audit events, and temporary-file
cleanup.

## Completion-call live test

`scripts/completion_call_live_test.py` drives the real Bot/Codex/call flow with the second Telethon
session:

1. enable `/completion_call on`;
2. select project and submit a real Codex task;
3. wait for primary call and answer;
4. record PCM;
5. confirm automatic hangup;
6. transcribe with bounded retry;
7. verify repetition;
8. check job/voice events and Redis pending/lag.

The primary session remains inside `voice-agent`. Do not use the historical main-user username as
the live test target.

Automated completion tests additionally cover every terminal category, redaction, fallback,
exact-three schema, atomic publish/dedup, retry, invalid payload, audit privacy, and fast-restart
pending recovery.

## Restart recovery

For a disposable job/call:

- stop/restart worker during an active job and confirm lease/pending reconciliation;
- restart voice after completion request delivery and confirm stale pending claim;
- verify authoritative PostgreSQL terminal state is unchanged;
- verify completion queue converges to pending/lag zero;
- accept that crash after audible call but before delivered marker may cause an at-least-once
  repeat.

## Evidence and claims

Record command, commit, environment/version, pass count, approved identities in redacted form,
job/call IDs, safe event sequence, durations/hashes, service health, and queue state. Keep audio and
screenshots under ignored runtime paths.

Do not claim:

- media success from signaling only;
- semantic memory because an embedding column exists;
- Playwright success without inspected browser evidence;
- exactly-once completion calls across Telegram/process crash;
- mypy success when mypy itself crashes;
- clean full-repository lint when only changed files passed.

See [Test matrix](TEST_MATRIX.md).
