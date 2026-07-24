# Root environment inventory

This is the semantic inventory for every root `.env.example` variable. Exact sample defaults live
in `.env.example`; detailed core behavior is in [Configuration](configuration.md). Empty secret
values mean “not configured,” not a usable credential.

## Application and runtime

| Variables | Meaning |
| --- | --- |
| `APP_ENV`, `CONFIG_PATH` | Environment and YAML policy path |
| `AGENT_API_HOST`, `AGENT_API_PORT` | Local API bind |
| `LOG_LEVEL`, `LOG_FORMAT` | Structured process logging |
| `TZ`, `HOSTNAME` | Display timezone and worker identity |
| `RUNTIME_DIR` | Voice/runtime root |
| `VOICE_AGENT_UAG_PORT` | Legacy voice host Ajil-port compatibility value |

## Telegram Bot API and Codex proxy

| Variables | Meaning |
| --- | --- |
| `TELEGRAM_BOT_TOKEN` | Bot secret |
| `TELEGRAM_ALLOWED_USER_IDS`, `TELEGRAM_ALLOWED_CHAT_IDS` | Compatibility placeholders; enforced lists currently live in YAML |
| `TELEGRAM_WEBHOOK_SECRET`, `TELEGRAM_WEBHOOK_PUBLIC_URL` | Webhook mode |
| `TELEGRAM_TRANSPORT` | `polling` or `webhook` |
| `TELEGRAM_BOT_PROXY_URL` | Bot HTTPS proxy |
| `CODEX_HTTP_PROXY_URL` | Independent App Server HTTP/HTTPS proxy |

## PostgreSQL, Redis, and Ajil endpoint

| Variables | Meaning |
| --- | --- |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Compose PostgreSQL identity |
| `POSTGRES_HOST`, `POSTGRES_PORT`, `DATABASE_URL` | Host/control-plane SQL connection |
| `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB`, `REDIS_URL` | Agent Redis DB 1 |
| `AJIL_BASE_URL`, `AJIL_PORT` | Host Ajil client URL/published port |

## Codex runtime and policy

| Variables | Meaning |
| --- | --- |
| `CODEX_BINARY`, `CODEX_INSTALL_MODE` | Executable and installation convention |
| `CODEX_HOME`, `CODEX_HOME_HOST` | Container/host authenticated Codex home |
| `CODEX_HOST_RUNTIME` | Host runtime mounted into agent containers |
| `AGENT_IMAGE` | Platform image name |
| `CODEX_MODEL`, `CODEX_REASONING_EFFORT` | Global defaults |
| `CODEX_APPROVAL_POLICY`, `CODEX_SANDBOX_MODE`, `CODEX_NETWORK_ACCESS` | Execution policy |
| `CODEX_ACCESS_TOKEN`, `OPENAI_API_KEY` | Optional secrets; mounted Codex auth is preferred |

## Codex completion calls

| Variables | Meaning |
| --- | --- |
| `CODEX_COMPLETION_CALLS_ENABLED` | Global availability |
| `CODEX_COMPLETION_CALL_STREAM`, `CODEX_COMPLETION_CALL_CONSUMER_GROUP` | Redis delivery contract |
| `CODEX_COMPLETION_CALL_REDIS_URL` | Voice consumer host Redis URL |
| `CODEX_COMPLETION_CALL_RETRY_ATTEMPTS`, `CODEX_COMPLETION_CALL_RETRY_DELAY_SEC` | Bounded retry |
| `CODEX_COMPLETION_CALL_POST_PLAYBACK_SEC` | Guard before automatic hangup |

## Browser, artifacts, Docker, and workspaces

| Variables | Meaning |
| --- | --- |
| `PLAYWRIGHT_BROWSERS_PATH`, `PLAYWRIGHT_HEADLESS` | Browser installation/mode |
| `CHROME_CDP_ENDPOINT`, `DISPLAY`, `XDG_SESSION_TYPE` | Existing/headed browser context |
| `FFMPEG_BINARY`, `FFPROBE_BINARY` | Platform media inspection |
| `ARTIFACT_ROOT`, `ARTIFACT_RETENTION_DAYS` | Artifact storage/expiry metadata |
| `DOCKER_HOST`, `COMPOSE_PROJECT_NAME` | Docker deployment |
| `PROJECT_OCTOPUS_ROOT`, `WORKSPACE_ROOT`, `WORKSPACE_ROOT_HOST` | Trusted project/container/host roots |

## Primary Telethon signaling

| Variables | Meaning |
| --- | --- |
| `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_STRING_SESSION` | Primary user authorization |
| `TELEGRAM_PROXY_ENABLED`, `TELEGRAM_PROXY_TYPE` | Signaling proxy policy |
| `TELEGRAM_PROXY_HOST`, `TELEGRAM_PROXY_PORT` | Host signaling proxy |
| `TELEGRAM_PROXY_USERNAME`, `TELEGRAM_PROXY_PASSWORD`, `TELEGRAM_PROXY_RDNS` | Proxy authentication/DNS |
| `TELEGRAM_PROXY_HOST_DOCKER`, `TELEGRAM_PROXY_PORT_DOCKER` | Container endpoint |

## Voice calls and conversation

| Variables | Meaning |
| --- | --- |
| `VOICE_AGENT_ALLOWED_PEER_IDS` | Numeric inbound/outbound call allowlist |
| `VOICE_AGENT_TEST_PEER_USERNAME` | Explicit CLI test target convenience |
| `VOICE_AGENT_INBOUND_ENABLED`, `VOICE_AGENT_INBOUND_USERNAMES` | Persistent inbound service |
| `VOICE_AGENT_REQUIRE_DISCLOSURE` | Automated-processing introduction policy |
| `VOICE_AGENT_RECORDING_MODE` | `off` or `transcript_only` |
| `VOICE_AGENT_MAX_TURN_SECONDS`, `VOICE_AGENT_CALL_TIMEOUT_SEC` | Turn/call bounds |
| `VOICE_AGENT_MAX_HISTORY_MESSAGES` | Per-call chat history |
| `VOICE_AGENT_LANGUAGE`, `VOICE_AGENT_SYSTEM_PROMPT` | Enforced English behavior |
| `VOICE_AGENT_MAX_VOICE_REPLY_CHARS` | Spoken response cap |
| `VOICE_AGENT_VAD_START_RMS`, `VOICE_AGENT_VAD_CONTINUE_RMS` | VAD hysteresis |
| `VOICE_AGENT_VAD_START_MS`, `VOICE_AGENT_VAD_END_SILENCE_MS` | VAD timing |
| `VOICE_AGENT_VAD_MIN_UTTERANCE_MS`, `VOICE_AGENT_VAD_PRE_ROLL_MS` | Noise/pre-roll |
| `VOICE_AGENT_AUDIO_SAMPLE_RATE`, `VOICE_AGENT_AUDIO_CHANNELS` | PCM format |

## Telethon private messages

| Variables | Meaning |
| --- | --- |
| `VOICE_AGENT_MESSAGE_ENABLED`, `VOICE_AGENT_MESSAGE_USERNAME` | Handler and sole peer |
| `VOICE_AGENT_MESSAGE_DEFAULT_RESPONSE` | `text` or `voice` |
| `VOICE_AGENT_MESSAGE_MAX_MEDIA_BYTES` | Per-attachment input cap |
| `VOICE_AGENT_MESSAGE_MEDIA_LIBRARY_DIR`, `VOICE_AGENT_MESSAGE_MEDIA_MANIFEST` | Approved outbound assets |
| `VOICE_AGENT_MESSAGE_VISION_ENABLED` | Image analysis |
| `VOICE_AGENT_MESSAGE_STT_LANGUAGE` | Enforced English message-audio STT |
| `VOICE_AGENT_VISION_MODELS`, `VOICE_AGENT_VISION_PROVIDERS` | Ajil vision route |

## Voice UDP media overlay

| Variables | Meaning |
| --- | --- |
| `VOICE_AGENT_MEDIA_TUNNEL_ENABLED`, `VOICE_AGENT_MEDIA_TUNNEL_LISTEN_PORT`, `VOICE_AGENT_MEDIA_TUNNEL_TTL_SEC` | GOST tunnel lifecycle |
| `VOICE_AGENT_MEDIA_TUNNEL_MARK`, `VOICE_AGENT_MEDIA_TUNNEL_FWMARK`, `VOICE_AGENT_MEDIA_TUNNEL_ROUTE_TABLE` | Policy routing/TPROXY |
| `VOICE_AGENT_MEDIA_TUNNEL_EXCLUDED_CIDRS` | Networks excluded from capture |
| `VOICE_AGENT_MEDIA_PROXY_HOST`, `VOICE_AGENT_MEDIA_PROXY_PORT` | Container proxy endpoint |
| `VOICE_AGENT_MEDIA_PROVISION_PROXY_HOST`, `VOICE_AGENT_MEDIA_PROVISION_PROXY_PORT` | Host provisioning proxy |
| `VOICE_AGENT_MEDIA_SSH_HOST`, `VOICE_AGENT_MEDIA_SSH_PORT`, `VOICE_AGENT_MEDIA_SSH_USER` | Remote SSH transport |
| `VOICE_AGENT_MEDIA_SSH_KEY_PATH`, `VOICE_AGENT_MEDIA_SSH_KNOWN_HOSTS_PATH` | SSH trust material |
| `VOICE_AGENT_MEDIA_SSH_FORWARD_PORT` | Local forwarded relay port |
| `VOICE_AGENT_MEDIA_SSH_KEEPALIVE_SEC`, `VOICE_AGENT_MEDIA_SSH_KEEPALIVE_COUNT` | SSH liveness |
| `VOICE_AGENT_MEDIA_RELAY_REMOTE_PORT`, `VOICE_AGENT_MEDIA_RELAY_USER`, `VOICE_AGENT_MEDIA_RELAY_PASSWORD` | Remote GOST relay |
| `VOICE_AGENT_MEDIA_GOST_IMAGE` | Sidecar image |
| `VOICE_AGENT_MEDIA_STUN_HOST`, `VOICE_AGENT_MEDIA_STUN_PORT`, `VOICE_AGENT_MEDIA_STUN_TIMEOUT_SEC` | Preflight |

## Ajil application, logging, auth, and routing

| Variables | Meaning |
| --- | --- |
| `UAG_BASE_URL`, `UAG_APP_HOST`, `UAG_APP_PORT`, `UAG_APP_LOG_LEVEL`, `UAG_APP_DOCS_ENABLED` | Gateway app |
| `UAG_LOG_ENABLED`, `UAG_LOG_JSON`, `UAG_LOG_HTTP_REQUESTS`, `UAG_LOG_ROUTER_DISPATCH` | Core logs |
| `UAG_LOG_PROVIDER_ATTEMPTS`, `UAG_LOG_WEBSOCKET`, `UAG_LOG_MAX_EVENTS`, `UAG_USAGE_MAX_EVENTS` | Provider/event/usage logging |
| `UAG_CHAT_ENDPOINT`, `UAG_AUDIO_TRANSCRIPTIONS_ENDPOINT` | Root client routes |
| `UAG_AUTH_TOKEN`, `UAG_AUTH_HEADER_NAME` | Client API auth |
| `UAG_ADMIN_ENABLED`, `UAG_ADMIN_TOKEN`, `UAG_ADMIN_HEADER_NAME` | Admin API auth |
| `UAG_TIMEOUT_SEC` | Root client/provider bound |
| `UAG_ROUTER_DEFAULT_STRATEGY`, `UAG_ROUTER_DEFAULT_MODE` | Router selection |
| `UAG_ROUTER_PARALLEL_TIMEOUT_SEC`, `UAG_ROUTER_MAX_CANDIDATES` | Parallel bounds |
| `UAG_ROUTER_FALLBACK_MAX_ATTEMPTS`, `UAG_ROUTER_FALLBACK_ATTEMPT_TIMEOUT_SEC` | Fallback bounds |
| `UAG_ROUTER_FALLBACK_ROUND_BACKOFF_SEC`, `UAG_ROUTER_RETRYABLE_STATUS_CODES` | Retry policy |
| `UAG_ROUTER_STRICT_RATE_LIMIT_ERRORS_ONLY` | Rate-limit classification |

## Ajil Redis, proxy, and build

| Variables | Meaning |
| --- | --- |
| `UAG_REDIS_REQUIRED`, `UAG_REDIS_URL`, `UAG_REDIS_URL_DOCKER`, `UAG_REDIS_HOST_PORT` | Ajil Redis DB 0 |
| `UAG_REDIS_KEY_PREFIX`, `UAG_REDIS_DEFAULT_LIMIT_PER_MINUTE` | Key/rate policy |
| `UAG_PROXY_ENABLED`, `UAG_PROXY_URL`, `UAG_PROXY_URL_DOCKER`, `UAG_PROXY_USE_COMPOSE_SERVICE` | Gateway outbound proxy |
| `UAG_DOCKER_BUILD_NETWORK` | Build network |
| `UAG_BUILD_HTTP_PROXY`, `UAG_BUILD_HTTPS_PROXY`, `UAG_BUILD_ALL_PROXY`, `UAG_BUILD_NO_PROXY` | Build proxy |
| `UAG_PIP_INDEX_URL`, `UAG_PIP_EXTRA_INDEX_URL` | Build package indexes |

## Ajil Gemini

| Variables | Meaning |
| --- | --- |
| `UAG_GEMINI_ENABLED`, `UAG_GEMINI_MODE`, `UAG_GEMINI_BASE_URL`, `UAG_GEMINI_API_VERSION` | Adapter |
| `UAG_GEMINI_DEFAULT_MODEL`, `UAG_GEMINI_API_KEYS` | Model/credentials |
| `UAG_GEMINI_RETRY_ON_429`, `UAG_GEMINI_RETRY_ON_5XX` | Retry classes |
| `UAG_GEMINI_MAX_RETRIES_PER_KEY`, `UAG_GEMINI_MAX_RETRIES_ON_5XX`, `UAG_GEMINI_RETRY_BACKOFF_SEC` | Retry bounds |
| `UAG_GEMINI_COOLOFF_SEC`, `UAG_GEMINI_MIN_INTERVAL_SEC` | Key pacing |
| `UAG_GEMINI_WORKER_BASE_URLS`, `UAG_GEMINI_WORKER_ROUTE_PREFIX` | Optional worker routes |
| `UAG_GEMINI_WORKER_AUTH_TOKEN`, `UAG_GEMINI_WORKER_AUTH_HEADER_NAME` | Worker auth |
| `AI_CHAT_MODELS`, `AI_CHAT_PROVIDERS` | Root chat routing |

## Ajil Groq STT/TTS

| Variables | Meaning |
| --- | --- |
| `AI_TRANSCRIPTION_PROVIDER`, `AI_TRANSCRIPTION_MODELS` | Root STT routing |
| `UAG_GROQ_ENABLED`, `UAG_GROQ_BASE_URL`, `UAG_GROQ_API_KEYS` | Adapter/credentials |
| `UAG_GROQ_RETRY_ON_429`, `UAG_GROQ_RETRY_ON_5XX` | Retry classes |
| `UAG_GROQ_MAX_RETRIES_PER_KEY`, `UAG_GROQ_MAX_RETRIES_ON_5XX`, `UAG_GROQ_RETRY_BACKOFF_SEC` | Retry bounds |
| `UAG_GROQ_COOLOFF_SEC`, `UAG_GROQ_MIN_INTERVAL_SEC` | Key pacing |
| `UAG_GROQ_STT_PRIMARY_MODEL`, `UAG_GROQ_STT_FALLBACK_MODEL` | STT models |
| `UAG_GROQ_STT_LANGUAGE`, `UAG_GROQ_STT_TEMPERATURE`, `UAG_GROQ_STT_RESPONSE_FORMAT`, `UAG_GROQ_STT_PROMPT` | STT behavior |
| `UAG_GROQ_TTS_DEFAULT_MODEL`, `UAG_GROQ_TTS_DEFAULT_VOICE`, `UAG_GROQ_TTS_DEFAULT_RESPONSE_FORMAT` | Groq TTS |

## Ajil Pollinations/image

| Variables | Meaning |
| --- | --- |
| `UAG_POLLINATIONS_ENABLED`, `UAG_POLLINATIONS_BASE_URL`, `UAG_POLLINATIONS_API_KEYS` | Adapter/credentials |
| `UAG_POLLINATIONS_DEFAULT_IMAGE_MODEL`, `UAG_POLLINATIONS_MAX_ATTEMPTS_PER_REQUEST` | Model/attempts |
| `UAG_POLLINATIONS_RETRY_STATUS_CODES`, `UAG_POLLINATIONS_RETRY_BACKOFF_SEC`, `UAG_POLLINATIONS_KEY_COOLDOWN_SEC` | Retry/pacing |
| `UAG_POLLINATIONS_LOCAL_PLACEHOLDER_ON_FAILURE` | Failure placeholder policy |
| `UAG_IMAGE_DEFAULT_N`, `UAG_IMAGE_DEFAULT_SIZE`, `UAG_IMAGE_DEFAULT_QUALITY`, `UAG_IMAGE_DEFAULT_RESPONSE_FORMAT` | Image defaults |

## Provider aliases, Edge TTS, audit, and live tests

| Variables | Meaning |
| --- | --- |
| `GROQ_API_KEYS`, `GROQ_API_KEY` | Nested-module Groq aliases |
| `GEMINI_API_KEYS` | Nested-module Gemini alias |
| `POLLINATIONS_API_KEYS`, `POLLINATIONS_API_KEY` | Nested-module Pollinations aliases |
| `EDGE_TTS_VOICE`, `EDGE_TTS_RATE`, `FFMPEG_BIN` | Voice synthesis/conversion |
| `AUDIT_DATABASE_PATH`, `AUDIT_JSONL_PATH` | Voice persistence |
| `RUN_LIVE_AJIL_TESTS`, `RUN_LIVE_CODEX_TESTS`, `RUN_LIVE_TELEGRAM_TESTS`, `RUN_LIVE_PLAYWRIGHT_TESTS` | External opt-ins |
| `TEST_TELEGRAM_CHAT_ID` | Approved live Bot target |

The pinned Ajil submodule owns detailed provider/router behavior. Keep the root variable names and
Compose forwarding stable, but consult the pinned submodule documentation before changing an
adapter-specific value.
