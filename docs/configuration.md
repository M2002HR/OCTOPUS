# Configuration reference

## Sources and precedence

OCTOPUS has exactly two root configuration sources:

1. `config/agent.yaml`: checked-in non-secret product policy and defaults.
2. `.env`: ignored secrets, credentials, machine paths, ports, and deployment overrides.

`load_settings` loads the root `.env` without overwriting already exported process variables,
reads `CONFIG_PATH` (default `config/agent.yaml`), expands `${NAME:-default}`, then validates with
Pydantic. An explicitly empty environment value uses the YAML fallback.

The Telethon compatibility package validates its environment contract directly from the same root
`.env`. Compose injects container URLs/mounts but does not introduce another env file.

Start from `.env.example` or use `scripts/bootstrap_env.py`; it refuses to overwrite `.env`, writes
mode `0600`, and never prints secret values.

Never commit `.env`, create a submodule `.env`, put credentials in YAML, or paste values into
documentation/logs.

## `config/agent.yaml`

### Application and Telegram

| Key | Default | Meaning |
| --- | --- | --- |
| `app.name` | `telegram-codex-agent` | Product/service name |
| `app.environment` | `development` | Environment; production disables API docs |
| `app.timezone` | `Asia/Tehran` | Display/operational timezone |
| `app.language` | `en` | Control-plane response default |
| `app.api_host`, `app.api_port` | `127.0.0.1`, `18090` | Agent API bind |
| `app.log_level`, `app.log_format` | `INFO`, `json` | Process logging |
| `telegram.transport` | `polling` | `polling` or `webhook` |
| `telegram.bot_token_env` | `TELEGRAM_BOT_TOKEN` | Secret indirection |
| `telegram.allowed_user_ids/chat_ids` | empty | Enforced YAML numeric allowlists; an empty list permits all users/chats |
| `telegram.allowed_usernames` | empty | Enforced YAML Telegram username allowlist; case-insensitive and `@` is optional |
| `telegram.webhook_public_url` | empty | Required when webhook transport is chosen |
| `telegram.webhook_secret_env` | `TELEGRAM_WEBHOOK_SECRET` | Webhook secret indirection |
| `telegram.default_parse_mode` | `HTML` | Bot formatting |
| `telegram.progress_edit_interval_seconds` | `3` | Live edit throttle |
| `telegram.max_message_length` | `3800` | Safe Telegram chunk size |
| `telegram.bot_proxy_url_env` | `TELEGRAM_BOT_PROXY_URL` | Bot-only proxy indirection |

The two similarly named values retained in `.env.example` are compatibility placeholders and are
not projected into the current YAML model. Put the active numeric Bot allowlists in
`config/agent.yaml`. Keep them distinct from Telethon peer IDs.

### Database, Redis, Ajil

| Key | Default | Meaning |
| --- | --- | --- |
| `database.url` | local PostgreSQL URL | SQLAlchemy async source of truth |
| `database.echo` | `false` | SQL logging |
| `database.pool_size` | `8` | Async pool size |
| `redis.url` | `redis://127.0.0.1:16379/1` | Agent Redis DB 1 |
| `redis.stream` | `telegram_codex_agent.jobs` | Job Stream |
| `redis.consumer_group` | `telegram_codex_agent.workers` | Worker group |
| `ajil.base_url` | `http://127.0.0.1:8080` | Host Ajil URL |
| `ajil.auth_token_env` | `UAG_AUTH_TOKEN` | Secret indirection |
| `ajil.auth_header_name` | `x-api-token` | Client auth header |
| `ajil.timeout_seconds` | `45` | Request timeout |
| `ajil.planner.model` | empty | Ajil-selected/default planner model |
| `ajil.planner.temperature` | `0` | Deterministic planning |
| `ajil.planner.max_retries` | `2` | Structured plan retries |
| `ajil.planner.reject_local_fallback` | `true` | Do not silently fake a remote plan |

Ajil itself uses Redis DB 0. The agent uses DB 1.

### Codex and jobs

| Key | Default | Meaning |
| --- | --- | --- |
| `codex.binary` | `codex` | App Server executable |
| `codex.model` | `gpt-5.6-terra` | Default model |
| `codex.reasoning_effort` | `high` | Default effort |
| `codex.service_tier` | null | Standard unless per-user Fast resolves a tier |
| `codex.approval_policy` | `never` | `never`, `on-request`, or `untrusted` |
| `codex.sandbox_mode` | `danger-full-access` | Development default |
| `codex.network_access` | `true` | Codex network policy |
| `codex.startup_timeout_seconds` | `30` | App Server startup/RPC bound |
| `jobs.worker_count` | `1` | Declared worker count |
| `jobs.lease_seconds` | `30` | PostgreSQL lease |
| `jobs.heartbeat_seconds` | `5` | Heartbeat interval |
| `jobs.timeout_seconds` | `3600` | Whole job timeout |
| `jobs.step_timeout_seconds` | `900` | Planned step timeout |
| `jobs.output_byte_cap` | `1048576` | Captured output/event bound |
| `jobs.recovery_policy` | `resume_or_fail` | Restart reconciliation |

Per-user model, reasoning, Fast, permissions, and language settings override defaults only through
a job snapshot. They do not rewrite YAML or `.env`.

### Artifacts, browser, memory, workspace

| Key | Default | Meaning |
| --- | --- | --- |
| `artifacts.root` | `./data/artifacts` | Managed artifact root |
| `artifacts.retention_days` | `30` | Expiry metadata; external cleanup needed while scheduler is disabled |
| `artifacts.telegram_direct_upload_max_bytes` | `47185920` | Bot direct upload cap |
| `browser.default_mode` | `isolated_headless` | Preferred browser mode |
| `browser.headless` | `true` | Default headless flag |
| `browser.cdp_endpoint` | `http://127.0.0.1:9222` | Chrome Lab/CDP endpoint |
| `memory.enabled` | `true` | Memory service |
| `memory.summarize_after_messages` | `30` | Compaction policy threshold |
| `memory.retrieval_limit` | `8` | Scoped retrieval cap |
| `workspace.root` | `/home/mhr/Code` | Trusted project discovery root |
| `workspace.discover_git_projects` | `true` | Discover Git directories |
| `workspace.max_depth` | `1` | Discovery depth |
| `projects[]` | OCTOPUS | Explicit trusted registry with root and test/lint policy |

### Voice bridge policy

| Key | Default | Meaning |
| --- | --- | --- |
| `voice.enabled` | `true` | Platform voice availability |
| `voice.telegram_voice_replies_default` | `false` | Bot response default |
| `voice.stt_language` | `en` | Bot voice-note STT default |
| `voice.ffmpeg_binary` | `ffmpeg` | Platform media binary |
| `voice.legacy_telethon_service` | `true` | Preserve compatibility subsystem |
| `voice.completion_calls.enabled` | `true` | Global completion-call availability |
| `.stream` | `telegram_codex_agent.completion_calls` | Completion Stream |
| `.consumer_group` | `voice_agent.completion_calls` | Primary voice group |
| `.repeat_count` | exactly `3` | Schema-fixed repetitions |
| `.max_message_characters` | `240` | Spoken status cap |
| `.queue_retention_seconds` | `2592000` | Dedup retention |
| `.max_queue_length` | `10000` | Approximate Stream cap |

## Root environment groups

`.env.example` is the exhaustive variable-name inventory. The tables below explain ownership and
interaction; Ajil provider internals retain their authoritative semantics in the pinned submodule.

### Root, platform, storage

| Variables | Purpose |
| --- | --- |
| `APP_ENV`, `CONFIG_PATH`, `TZ`, `HOSTNAME`, `LOG_LEVEL`, `LOG_FORMAT` | Process policy/identity |
| `AGENT_API_HOST`, `AGENT_API_PORT` | Host API |
| `POSTGRES_*`, `DATABASE_URL` | PostgreSQL |
| `REDIS_*`, `REDIS_URL` | Agent Redis DB 1 |
| `AJIL_BASE_URL`, `AJIL_PORT` | Host Ajil endpoint |
| `RUNTIME_DIR`, `ARTIFACT_ROOT`, `ARTIFACT_RETENTION_DAYS` | Local data roots/retention |
| `DOCKER_HOST`, `COMPOSE_PROJECT_NAME` | Docker deployment |

Use a strong non-example PostgreSQL password and keep `DATABASE_URL` consistent with it.

### Telegram Bot

| Variable | Default/policy |
| --- | --- |
| `TELEGRAM_BOT_TOKEN` | required secret |
| `TELEGRAM_ALLOWED_USER_IDS`, `TELEGRAM_ALLOWED_CHAT_IDS` | compatibility placeholders; active lists are YAML policy |
| `TELEGRAM_TRANSPORT` | `polling` |
| `TELEGRAM_WEBHOOK_PUBLIC_URL`, `TELEGRAM_WEBHOOK_SECRET` | webhook only |
| `TELEGRAM_BOT_PROXY_URL` | Bot HTTPS proxy; independent from all other proxies |

### Codex and workspace

| Variable | Default/policy |
| --- | --- |
| `CODEX_BINARY` | `codex` |
| `CODEX_HOME_HOST` | host authenticated Codex home |
| `CODEX_HOST_RUNTIME` | host Node/Codex runtime mounted read-only |
| `AGENT_IMAGE` | `octopus-agent-platform:latest` |
| `CODEX_MODEL` | `gpt-5.6-terra` |
| `CODEX_REASONING_EFFORT` | `high` |
| `CODEX_APPROVAL_POLICY` | `never` |
| `CODEX_SANDBOX_MODE` | `danger-full-access` |
| `CODEX_NETWORK_ACCESS` | `true` |
| `CODEX_HTTP_PROXY_URL` | App Server HTTP CONNECT proxy |
| `CODEX_ACCESS_TOKEN`, `OPENAI_API_KEY` | optional secrets; prefer mounted authenticated home |
| `PROJECT_OCTOPUS_ROOT` | registered host project |
| `WORKSPACE_ROOT`, `WORKSPACE_ROOT_HOST` | container and host trusted workspace roots |

`PLAYWRIGHT_BROWSERS_PATH`, `PLAYWRIGHT_HEADLESS`, `CHROME_CDP_ENDPOINT`, `DISPLAY`,
`XDG_SESSION_TYPE`, `FFMPEG_BINARY`, and `FFPROBE_BINARY` support browser/artifact tasks.

### Per-user Bot preferences

Stored in PostgreSQL, not `.env`:

- `codex_model`
- `codex_reasoning_effort`
- `codex_fast_mode` and resolved `codex_service_tier`
- `sandbox_mode`/permission selection
- `input_language`, `response_language`
- `log_level`, `stream_progress`
- `completion_call_enabled`
- selected project/session context.

`/status` shows effective next-job values. `/usage` is Codex account quota; it is not a preference.

### Primary Telethon and calls

| Variable | Default | Meaning |
| --- | --- | --- |
| `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_STRING_SESSION` | required | Primary user authorization |
| `TELEGRAM_PROXY_ENABLED` | `false` | Signaling proxy |
| `TELEGRAM_PROXY_TYPE` | `socks5` | PySocks/Telethon scheme |
| `TELEGRAM_PROXY_HOST`, `TELEGRAM_PROXY_PORT` | empty, `0` | Host endpoint |
| `TELEGRAM_PROXY_USERNAME/PASSWORD/RDNS` | empty/true | Optional credentials/DNS |
| `TELEGRAM_PROXY_HOST_DOCKER/PORT_DOCKER` | host gateway/`0` | Container endpoint |
| `VOICE_AGENT_ALLOWED_PEER_IDS` | required for calls | Numeric outbound/inbound allowlist |
| `VOICE_AGENT_TEST_PEER_USERNAME` | empty | Explicit CLI test convenience |
| `VOICE_AGENT_INBOUND_ENABLED` | `false` | Persistent inbound call enable |
| `VOICE_AGENT_INBOUND_USERNAMES` | empty | Startup-resolved caller list |
| `VOICE_AGENT_REQUIRE_DISCLOSURE` | code default `true`; example `false` | Automated processing disclosure |
| `VOICE_AGENT_CALL_TIMEOUT_SEC` | `120` | Connection timeout |

`VOICE_AGENT_INBOUND_USERNAME` is a legacy one-user fallback. The same primary session must not be
active in another process.

### Completion calls

| Variable | Default | Meaning |
| --- | --- | --- |
| `CODEX_COMPLETION_CALLS_ENABLED` | `true` | Global availability; users remain opted out |
| `CODEX_COMPLETION_CALL_STREAM` | standard stream | Must match YAML |
| `CODEX_COMPLETION_CALL_CONSUMER_GROUP` | voice group | Must match YAML |
| `CODEX_COMPLETION_CALL_REDIS_URL` | host DB 1 | Compose overrides voice to `redis://redis:6379/1` |
| `CODEX_COMPLETION_CALL_RETRY_ATTEMPTS` | `3` | Bounded attempts |
| `CODEX_COMPLETION_CALL_RETRY_DELAY_SEC` | `10` | Retry delay |
| `CODEX_COMPLETION_CALL_POST_PLAYBACK_SEC` | `2` | Hangup guard |

See [Completion calls](completion-calls.md).

### Voice language, VAD, audio, and chat

| Variable | Default | Meaning |
| --- | --- | --- |
| `VOICE_AGENT_LANGUAGE` | `en` | Enforced English call STT |
| `VOICE_AGENT_SYSTEM_PROMPT` | English direct assistant | No self-introduction |
| `VOICE_AGENT_MAX_HISTORY_MESSAGES` | `12` | Per-call rolling context |
| `VOICE_AGENT_MAX_TURN_SECONDS` | `45` | Utterance cap |
| `VOICE_AGENT_MAX_VOICE_REPLY_CHARS` | `480` | Spoken reply cap |
| `VOICE_AGENT_VAD_START_RMS` | `350` | Speech start energy |
| `VOICE_AGENT_VAD_CONTINUE_RMS` | `240` | Continuation energy; ≤ start |
| `VOICE_AGENT_VAD_START_MS` | `80` | Sustained start |
| `VOICE_AGENT_VAD_END_SILENCE_MS` | `1200` | Turn-ending silence |
| `VOICE_AGENT_VAD_MIN_UTTERANCE_MS` | `250` | Noise rejection |
| `VOICE_AGENT_VAD_PRE_ROLL_MS` | `200` | Preserve initial audio |
| `VOICE_AGENT_AUDIO_SAMPLE_RATE` | `48000` | PCM rate |
| `VOICE_AGENT_AUDIO_CHANNELS` | `1` | `1` or `2` |

`VOICE_AGENT_SILENCE_MS` is a legacy fallback only. See
[Voice turn detection](voice-turn-detection.md).

### Private Telethon messaging

`VOICE_AGENT_MESSAGE_ENABLED`, `VOICE_AGENT_MESSAGE_USERNAME`,
`VOICE_AGENT_MESSAGE_DEFAULT_RESPONSE`, `VOICE_AGENT_MESSAGE_MAX_MEDIA_BYTES`,
`VOICE_AGENT_MESSAGE_MEDIA_LIBRARY_DIR`, `VOICE_AGENT_MESSAGE_MEDIA_MANIFEST`,
`VOICE_AGENT_MESSAGE_VISION_ENABLED`, `VOICE_AGENT_MESSAGE_STT_LANGUAGE`,
`VOICE_AGENT_VISION_MODELS`, and `VOICE_AGENT_VISION_PROVIDERS` are documented in
[Private messaging](messaging.md). Message STT is currently enforced to `en`.

### Ajil client, providers, and TTS

Root clients use:

- `UAG_BASE_URL`, endpoints, auth token/header, timeout;
- `AI_CHAT_MODELS`, `AI_CHAT_PROVIDERS`;
- `AI_TRANSCRIPTION_PROVIDER`, `AI_TRANSCRIPTION_MODELS`;
- `EDGE_TTS_VOICE`, `EDGE_TTS_RATE`, `FFMPEG_BIN`.

The root also passes `UAG_*` app/logging/admin/router/Redis/proxy/build values and
Gemini/Groq/Pollinations provider keys/policies to the pinned gateway. Backward-compatible
`GROQ_*`, `GEMINI_*`, and `POLLINATIONS_*` aliases exist for nested providers. Do not duplicate
their moving internal semantics here; `.env.example` lists every supported root variable and
`modules/ajil_uag` documents provider behavior.

### Voice storage and privacy

| Variable | Default | Meaning |
| --- | --- | --- |
| `AUDIT_DATABASE_PATH` | `runtime/voice_agent.sqlite3` | SQLite audit/content store |
| `AUDIT_JSONL_PATH` | `runtime/events.jsonl` | Content-free event mirror |
| `VOICE_AGENT_RECORDING_MODE` | `transcript_only` | `off` or sensitive transcript/reply rows |

Both modes remove temporary call media. The application does not claim encryption at rest.

### Media overlay

All `VOICE_AGENT_MEDIA_*` variables configure UDP capture, GOST, SSH, proxy endpoint, relay,
credentials, image, and STUN preflight. See [UDP media overlay](media-overlay.md). They are
independent from Bot, Codex, Ajil, and Telethon signaling proxies.

### Live test flags

`RUN_LIVE_AJIL_TESTS`, `RUN_LIVE_CODEX_TESTS`, `RUN_LIVE_TELEGRAM_TESTS`,
`RUN_LIVE_PLAYWRIGHT_TESTS`, and `TEST_TELEGRAM_CHAT_ID` opt into external tests. Ordinary tests
must not require credentials.

## Restart rules

Per-user Bot preferences need no restart and affect new jobs. Restart affected services after
changing credentials, URLs, proxies, allowlists, workspace mounts, global policy, VAD/TTS, or
completion Stream/group. Rebuild when source/dependencies/images change.

## Validation and safe inspection

```bash
agentctl config validate
agentctl config dump
curl --noproxy '*' http://127.0.0.1:18090/config/redacted
docker compose --profile agent config --quiet
```

Use only redacted output in support material. Compose-rendered configuration may contain expanded
secrets from `.env`; do not publish it.
