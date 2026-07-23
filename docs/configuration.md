# Configuration reference

The root `.env` is loaded by the Python process and passed to the Ajil Docker service. It is the
only runtime configuration file. Start from `.env.example`, or run
`python scripts/bootstrap_env.py` once to safely merge the approved local Telegram and Ajil
settings without printing secrets. The bootstrap script refuses to overwrite an existing `.env`
and writes it with `0600` permissions.

Never commit `.env`, copy its values into a submodule, or include them in logs, support tickets,
or shell history.

## Telegram and call policy

| Variable | Default | Meaning |
| --- | --- | --- |
| `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_STRING_SESSION` | required | Existing authorized Telethon account. |
| `TELEGRAM_PROXY_ENABLED` | `false` | Enables the Telethon signaling proxy. |
| `TELEGRAM_PROXY_TYPE` | `socks5` | Proxy scheme supported by Telethon/PySocks. |
| `TELEGRAM_PROXY_HOST`, `TELEGRAM_PROXY_PORT` | empty, `0` | Proxy endpoint when enabled. |
| `TELEGRAM_PROXY_USERNAME`, `TELEGRAM_PROXY_PASSWORD`, `TELEGRAM_PROXY_RDNS` | empty, `true` | Optional proxy credentials and remote DNS choice. |
| `TELEGRAM_PROXY_HOST_DOCKER`, `TELEGRAM_PROXY_PORT_DOCKER` | `host.docker.internal`, `0` | Container-specific proxy endpoint. Compose maps these over the normal host/port for `voice-agent`. |
| `VOICE_AGENT_ALLOWED_PEER_IDS` | empty | Required comma-separated numeric allowlist for outbound calls. |
| `VOICE_AGENT_TEST_PEER_USERNAME` | empty | Convenience value only; the CLI still requires `--username`. |
| `VOICE_AGENT_INBOUND_ENABLED` | `false` | Must be explicitly `true` before `serve` starts the persistent inbound service. |
| `VOICE_AGENT_INBOUND_USERNAME` | empty | The sole inbound caller. It is resolved at startup and must also be in the numeric allowlist. |
| `VOICE_AGENT_REQUIRE_DISCLOSURE` | `true` | Announces automated processing when a call connects. |
| `VOICE_AGENT_CALL_TIMEOUT_SEC` | `120` | PyTgCalls connection timeout; minimum `10`. |

The same Telethon authorization must not be active in another client during a call. A proxy used
by Telethon carries signaling only; it does not prove that the host can reach Telegram media
reflectors. See the VoIP section of [Troubleshooting](troubleshooting.md).

The inbound server accepts only one active call and immediately declines every caller whose numeric
ID differs from the startup-resolved `VOICE_AGENT_INBOUND_USERNAME`. Changing the username requires
a service restart; this avoids accepting a renamed or unverified account by string comparison at
call time.

## Voice behavior

| Variable | Default | Meaning |
| --- | --- | --- |
| `VOICE_AGENT_LANGUAGE` | `fa` | STT language hint. |
| `VOICE_AGENT_SYSTEM_PROMPT` | general assistant prompt | System instruction sent to Ajil chat. |
| `VOICE_AGENT_MAX_HISTORY_MESSAGES` | `12` | Per-call rolling user/assistant history count. |
| `VOICE_AGENT_MAX_TURN_SECONDS` | `45` | Hard upper bound for one detected utterance. |
| `VOICE_AGENT_AUDIO_SAMPLE_RATE` | `48000` | Native PCM sample rate requested from PyTgCalls. |
| `VOICE_AGENT_AUDIO_CHANNELS` | `1` | Native PCM channels (`1` or `2`). |
| `VOICE_AGENT_VAD_START_RMS` | `350` | Energy needed to begin a candidate utterance. |
| `VOICE_AGENT_VAD_CONTINUE_RMS` | `240` | Lower continuation energy; must not exceed start RMS. |
| `VOICE_AGENT_VAD_START_MS` | `80` | Minimum sustained speech before an utterance starts. |
| `VOICE_AGENT_VAD_END_SILENCE_MS` | `600` | Continuous quiet required to finish an utterance. |
| `VOICE_AGENT_VAD_MIN_UTTERANCE_MS` | `250` | Shorter audio is discarded as noise. |
| `VOICE_AGENT_VAD_PRE_ROLL_MS` | `200` | Audio preserved immediately before detected speech. |

`VOICE_AGENT_SILENCE_MS` remains accepted as a legacy fallback only when
`VOICE_AGENT_VAD_END_SILENCE_MS` is absent. Prefer the latter. Detailed tuning guidance is in
[Voice turn detection](voice-turn-detection.md).

## Ajil, Edge TTS, and Docker

| Variable | Default | Meaning |
| --- | --- | --- |
| `UAG_BASE_URL` | `http://127.0.0.1:8080` | URL used by a bare-metal agent. Docker overrides it to `http://uag-gateway:8080`. |
| `UAG_CHAT_ENDPOINT` | `/v1/chat/completions` | Ajil chat route. |
| `UAG_AUDIO_TRANSCRIPTIONS_ENDPOINT` | `/v1/audio/transcriptions` | Ajil STT route. |
| `UAG_AUTH_TOKEN`, `UAG_AUTH_HEADER_NAME` | empty, `x-api-token` | Client authentication for Ajil if enabled. |
| `UAG_TIMEOUT_SEC` | `45` | HTTP timeout per STT/chat request. |
| `AI_CHAT_MODELS`, `AI_CHAT_PROVIDERS` | empty | Ajil chat routing choices. |
| `AI_TRANSCRIPTION_PROVIDER`, `AI_TRANSCRIPTION_MODELS` | empty | Ajil STT provider configuration; the direct STT route selects its configured provider/model. |
| `EDGE_TTS_VOICE`, `EDGE_TTS_RATE` | `fa-IR-DilaraNeural`, `+0%` | Edge TTS voice and rate. |
| `FFMPEG_BIN` | `ffmpeg` | Ogg/Opus conversion executable. |
| `VOICE_AGENT_UAG_PORT` | `18081` | Host port for the Compose Ajil gateway. |
| `UAG_PROXY_URL_DOCKER` | empty | Docker-reachable proxy URL for Ajil; separate from a host-loopback URL. |
| `UAG_DOCKER_BUILD_NETWORK`, `UAG_BUILD_*`, `UAG_PIP_*` | empty | Optional controlled build-network/proxy/package-index settings. |

Ajil itself supports many `UAG_*` provider, router, retry, logging, and Redis variables. Keep all
of them in this root `.env`; Compose forwards the file to `uag-gateway`. Their semantics are owned
by the pinned Ajil submodule. Do not create `vendor/Ajil_Unified_AI_Gateway/.env`.

## Storage and diagnostics

| Variable | Default | Meaning |
| --- | --- | --- |
| `RUNTIME_DIR` | `runtime` | Local runtime root. Docker maps it to `/runtime`. |
| `AUDIT_DATABASE_PATH` | `runtime/voice_agent.sqlite3` | SQLite audit and optional transcript database. |
| `AUDIT_JSONL_PATH` | `runtime/events.jsonl` | Content-free JSONL event mirror. |
| `VOICE_AGENT_RECORDING_MODE` | `transcript_only` | `transcript_only` stores transcript/reply text in SQLite; `off` omits that table’s rows. Both modes delete call media on close. |
| `APP_ENV`, `LOG_LEVEL` | `development`, `INFO` | Application environment/log verbosity conventions. |

Transcript text is sensitive data. Protect the database, establish an external retention policy,
and use `off` where transcript storage is not authorized. Encryption-at-rest is intentionally not
claimed by this project; use encrypted host storage or a managed encrypted volume if required.

## UDP media overlay

The full `VOICE_AGENT_MEDIA_*` configuration surface is documented in
[media-overlay.md](media-overlay.md). It is deliberately independent from Telegram signaling
proxy values: media is captured by a dedicated network sidecar, then reaches the required proxy
through the SSH sidecar. All values, including the relay credential, are set from the root `.env`.

## Private messaging

`VOICE_AGENT_MESSAGE_*` settings control the same persistent `serve` process's allowlisted private
message assistant. Their semantics, privacy behavior, photo support, voice-first response policy,
and local media-library contract are documented in [messaging.md](messaging.md).
