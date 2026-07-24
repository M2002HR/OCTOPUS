# MASTER IMPLEMENTATION PROMPT
## Telegram-Based Full-Access Personal AI Agent over Codex CLI/App Server, Ajil Unified AI Gateway, Playwright, Persistent Memory, Voice, and Host Tools

> **How to use this file**
>
> Give this entire file to Codex CLI, Codex App, Claude Code, or another capable coding agent at the root of the target repository.
> This is an **execution specification**, not a high-level proposal. The implementation agent must inspect the repository, create or complete all missing components, run the system, test every layer, fix failures, and continue until the acceptance criteria in this document pass.
>
> The target user-facing language is **Persian-first**, while source code, internal identifiers, logs, schemas, and technical documentation should be written in clear English unless Persian is explicitly required.

---

# 1. Your Role

You are the principal software architect, staff-level backend engineer, DevOps engineer, test engineer, and implementation agent for this project.

You must:

1. Design the complete architecture.
2. Implement every required component.
3. Integrate all third-party modules correctly.
4. Add and initialize Git submodules recursively.
5. Build the local infrastructure.
6. Integrate Telegram, Ajil Unified AI Gateway, Codex App Server, Playwright, PostgreSQL/pgvector, Redis, FFmpeg, Git, Docker, and host shell execution.
7. Build persistent jobs, memory, artifacts, browser verification, voice input/output, and recovery after restart.
8. Write automated tests for every component.
9. Run all tests and fix failures.
10. Run realistic end-to-end smoke tests.
11. Produce complete documentation and reproducible setup scripts.
12. Keep working until the completion checklist is satisfied.

Do not stop after scaffolding. Do not provide only pseudocode. Do not leave core paths as TODOs. Do not merely explain how something could be implemented; implement it.

When a non-secret design decision is ambiguous, choose the most robust and maintainable option and document the decision. Do not block waiting for user confirmation.

If an external secret such as a Telegram token or provider key is unavailable:

- Create the complete implementation.
- Use a mock/fake adapter for automated testing.
- Add the missing secret to the root `.env.example`.
- Continue all local tests.
- Clearly mark only the live external smoke test as blocked by the missing credential.
- Do not stop the project because of missing secrets.

---

# 2. Primary Product Goal

Build a complete personal AI assistant that runs on the user's computer and is controlled primarily through Telegram.

The user must be able to send:

- Normal text messages
- Voice messages
- Images
- Documents
- Videos
- Code-related tasks
- System administration requests
- Browser testing requests
- Multi-step project requests

The assistant must be able to:

- Behave as a normal conversational chatbot
- Act as a Persian voice assistant
- Understand images and files
- Select the correct execution path
- Call Ajil Unified AI Gateway for general AI capabilities
- Start or resume Codex coding sessions
- Let Codex inspect, edit, run, debug, and test projects
- Execute arbitrary host commands in development full-access mode
- Manage Git repositories
- Manage Docker containers and Compose projects
- Start and stop development servers
- Use Playwright to open a browser and validate the result
- Capture screenshots
- Record browser video
- Record traces
- Optionally record the visible desktop/session
- Send reports and artifacts back through Telegram
- Maintain persistent memory across conversations and restarts
- Maintain project-specific Codex threads
- Continue long jobs asynchronously
- Stream progress back to Telegram
- Recover gracefully after process restart
- Support multiple projects without mixing context
- Store a complete audit trail of jobs and events

The conceptual flow is:

```text
Telegram
  -> Input normalization
  -> User/project/conversation resolution
  -> Persistent memory retrieval
  -> Intent classification and structured planning through Ajil
  -> Deterministic orchestrator
  -> Codex / Shell / Git / Docker / Playwright / File tools
  -> Automated verification
  -> Artifact collection
  -> Persistent memory update
  -> Telegram result
```

The architecture must **not** be:

```text
Telegram -> raw LLM text -> shell
```

The LLM may propose a structured plan, but a deterministic runtime must own state, execution, cancellation, retries, persistence, and reporting.

---

# 3. Development Security Mode

For the current phase, implement a **development full-access mode**.

This phase prioritizes functionality, reliability, debugging, and complete integration over permission hardening.

Required development behavior:

```text
execution_mode = full_access
codex sandbox_mode = danger-full-access
codex approval_policy = never
codex automatic approval bridge = accept all recognized approval requests
host shell = unrestricted
network access = enabled
filesystem access = unrestricted for the runtime user
docker access = enabled when available
git access = enabled
browser automation = enabled
```

Important implementation requirement:

- Security architecture must remain configurable.
- Do not hard-code full-access assumptions throughout the codebase.
- Centralize this behavior under configuration such as:

```yaml
security:
  mode: development_full_access
  auto_approve_codex_requests: true
  allow_arbitrary_shell: true
  allow_host_filesystem: true
  allow_network: true
  allow_docker_socket: true
```

Create interfaces that make a later hardened policy engine possible, but do not delay the current implementation by building a complex security product.

Even in full-access mode:

- Do not intentionally print secrets in logs.
- Redact obvious API keys, Telegram tokens, authorization headers, and passwords.
- Do not commit `.env`.
- Do not expose services publicly by default.
- These basic measures must not interfere with functionality.

Create a documented backlog section named `Future Security Hardening`, but do not make it a blocker.

---

# 4. Technical Grounding and Required Integration Approach

## 4.1 Ajil Unified AI Gateway

Use this repository as the unified AI module:

```text
https://github.com/M2002HR/Ajil_Unified_AI_Gateway.git
```

Add it as a Git submodule:

```text
modules/ajil_uag
```

Initialize its nested submodules recursively.

Ajil is responsible for unified access to:

- Chat completions
- Responses
- Vision-capable chat
- Embeddings
- Image generation
- Speech-to-text
- Text-to-speech
- Model/provider routing
- Fallback and load balancing
- Usage and provider observability

Ajil is **not** the main job runtime, tool runtime, memory store, or Codex process manager. Build those in this project.

Use Ajil through a typed asynchronous client.

Required Ajil endpoints to support:

```text
GET  /health
GET  /v1/models
GET  /v1/models/catalog
POST /v1/chat/completions
POST /v1/responses
POST /v1/embeddings
POST /v1/images/generations
POST /v1/audio/transcriptions
POST /v1/audio/speech
POST /v1/orchestrate
WS   /ws/llm                     optional
```

The planner must use structured output validated by Pydantic.

Ajil may return a local fallback chat response when upstream providers fail. For normal chat this may be acceptable, but for execution planning it is not acceptable. The implementation must detect fallback signals such as:

- `provider == local-fallback`
- `model == local/fallback`
- `x-uag-fallback` response header
- malformed or non-schema-compliant output

When one of these occurs during planning:

- Do not execute tools from that plan.
- Retry with a different model route.
- If all retries fail, return a clear message to Telegram.
- Never treat a placeholder response as a valid execution plan.

## 4.2 Codex

Use the maintained Codex CLI and its App Server interface.

Primary integration:

```text
codex app-server --listen stdio://
```

If the installed version accepts `--stdio`, support that as a compatibility fallback.

The runtime must generate and inspect the protocol schema for the exact installed Codex version:

```bash
codex app-server generate-json-schema --out generated/codex_app_server_schema
codex app-server generate-ts --out generated/codex_app_server_ts
```

Do not assume the wire schema forever. Build a protocol adapter and pin the tested Codex version.

The App Server client must implement:

- Process startup and supervision
- `initialize`
- `initialized`
- Request/response correlation
- JSONL transport over stdin/stdout
- stderr log collection
- Thread start
- Thread resume
- Thread read
- Thread fork where useful
- Turn start
- Turn interrupt
- Event streaming
- Diff updates
- Plan updates
- Agent message deltas
- Command output deltas
- File-change events
- Turn completion
- Token usage events
- Approval requests
- Process health monitoring
- Automatic restart
- Reconnection and thread recovery

Persist Codex thread IDs in the database.

Codex thread scope must be configurable. Default:

```text
one active Codex thread per:
user_id + project_id + logical_conversation_id
```

In development full-access mode:

```text
approval_policy = never
sandbox_mode = danger-full-access
network access = enabled
```

Also implement an approval request handler because some Codex versions or tool paths may still emit approval requests. When `security.auto_approve_codex_requests` is true:

- Automatically accept command approvals.
- Prefer session-scoped acceptance when supported.
- Automatically accept file-change approvals.
- Automatically grant requested filesystem/network permissions when supported.
- Log the approval event.
- Continue the turn without Telegram interaction.

Do not depend exclusively on interactive Codex TUI scraping.

As a fallback for short stateless tasks, support:

```text
codex exec --json
```

But the main implementation must use App Server for persistent sessions and streaming events.

## 4.3 Telegram

Use the official Telegram Bot API.

Default transport:

```text
long polling
```

Optional transport:

```text
webhook
```

Use an async Python Telegram framework, preferably `aiogram` 3.x unless repository constraints strongly justify another choice.

Support:

- Text
- Voice
- Audio
- Photo
- Document
- Video
- Callback queries
- Commands
- Inline keyboards
- Message editing for progress
- File download
- Artifact upload
- Long message splitting
- Markdown/HTML escaping
- Telegram API rate-limit handling
- Retrying transient errors

## 4.4 Playwright

Use Playwright for browser automation and verification.

Support:

1. Isolated browser mode
2. Headless browser mode
3. Headed browser mode
4. Existing Chrome connection over CDP
5. Screenshot capture
6. Browser-context video
7. Trace recording
8. Console error collection
9. Page error collection
10. Failed request collection
11. HTTP error collection
12. Assertions
13. Download collection
14. HTML report generation

Optional desktop/session recording:

- X11: FFmpeg `x11grab`
- Wayland: detect and use an available backend such as `wf-recorder`, or document the limitation
- Xvfb: use FFmpeg against the virtual display
- Windows/macOS: define an abstraction and implement where practical, but Linux is the primary target

Playwright artifacts must be sent to Telegram when requested.

---

# 5. Selected Technology Stack

Use the following baseline unless the existing repository already has a strongly justified compatible stack:

```text
Language:                    Python 3.12+
Package manager:             uv
Web/API framework:           FastAPI
Telegram framework:          aiogram 3.x
Configuration:               Pydantic v2 + pydantic-settings + YAML
Database:                    PostgreSQL 16
Vector search:               pgvector
ORM:                         SQLAlchemy 2 async
Migrations:                  Alembic
Redis client:                redis-py asyncio
Queue/event bus:             Redis Streams + PostgreSQL source of truth
HTTP client:                 httpx
Retries:                     tenacity
Structured logging:          structlog over stdlib logging
CLI:                         Typer
Serialization:               orjson
File I/O:                    aiofiles
Browser:                     Playwright Python
Testing:                     pytest + pytest-asyncio
Coverage:                    pytest-cov
Lint/format:                 Ruff
Type checking:               mypy
Containers:                  Docker Compose
Process supervision:         systemd user service + development runner
Media:                       FFmpeg
```

Do not introduce a JavaScript service unless necessary. A Node package may be used only if a required browser feature cannot be implemented cleanly in Python.

---

# 6. Repository and Git Submodule Policy

## 6.1 Root repository

The root project should be a normal Git repository.

If no repository exists:

```bash
git init
```

Before changes:

```bash
git status --short
git branch --show-current
```

Do not overwrite unrelated user files.

## 6.2 Required submodule

Add Ajil if it is not already present:

```bash
git submodule add https://github.com/M2002HR/Ajil_Unified_AI_Gateway.git modules/ajil_uag
git submodule update --init --recursive
```

Pin the submodule to a known commit.

Do not copy Ajil source files into the root project.

Ajil already contains nested provider submodules. Initialize recursively.

## 6.3 Additional source repositories

If another external source repository must be modified or built from source:

- Add it under `modules/<name>` as a Git submodule.
- Pin the commit.
- Document why it is a submodule.
- Do not paste an unmanaged copy into the repository.

Normal Python packages, system packages, and binaries are not Git submodules.

Codex should normally be installed as an official executable dependency. Add the OpenAI Codex repository as a submodule only if the implementation genuinely requires building Codex from source. Make this optional through:

```text
CODEX_INSTALL_MODE=package
CODEX_SOURCE_SUBMODULE_PATH=modules/openai_codex
```

## 6.4 Submodule patching

Prefer adapting to Ajil externally.

If a local Ajil change is unavoidable and there is no writable fork:

- Keep reproducible patches under `patches/ajil/`.
- Add `scripts/apply_submodule_patches.sh`.
- Verify patches are idempotent.
- Document each patch.
- Never leave the submodule dirty without a reproducible patch.

## 6.5 Submodule tooling

Implement:

```text
scripts/submodules_init.sh
scripts/submodules_verify.sh
scripts/submodules_update.sh
scripts/apply_submodule_patches.sh
```

`submodules_verify.sh` must check:

- Required paths exist
- Expected commits are checked out
- Nested submodules are initialized
- No unexpected dirty state exists
- Required Ajil files exist
- Ajil health/build prerequisites are present

---

# 7. Required Root Directory Layout

Implement a structure close to this:

```text
.
├── AGENTS.md
├── MASTER_IMPLEMENTATION_PROMPT.md
├── README.md
├── README.fa.md
├── pyproject.toml
├── uv.lock
├── Makefile
├── docker-compose.yml
├── .env
├── .env.example
├── .gitignore
├── config/
│   └── agent.yaml
├── generated/
│   ├── codex_app_server_schema/
│   └── config.schema.json
├── modules/
│   └── ajil_uag/
├── patches/
│   └── ajil/
├── src/
│   └── telegram_codex_agent/
│       ├── __init__.py
│       ├── main.py
│       ├── cli.py
│       ├── config/
│       │   ├── loader.py
│       │   ├── models.py
│       │   └── interpolation.py
│       ├── api/
│       │   ├── app.py
│       │   ├── dependencies.py
│       │   ├── health.py
│       │   ├── jobs.py
│       │   ├── projects.py
│       │   ├── artifacts.py
│       │   └── metrics.py
│       ├── telegram/
│       │   ├── bot.py
│       │   ├── dispatcher.py
│       │   ├── middleware.py
│       │   ├── commands.py
│       │   ├── callbacks.py
│       │   ├── formatting.py
│       │   ├── progress.py
│       │   ├── files.py
│       │   └── handlers/
│       │       ├── text.py
│       │       ├── voice.py
│       │       ├── photo.py
│       │       ├── document.py
│       │       ├── video.py
│       │       └── commands.py
│       ├── orchestrator/
│       │   ├── service.py
│       │   ├── state_machine.py
│       │   ├── planner.py
│       │   ├── router.py
│       │   ├── executor.py
│       │   ├── verifier.py
│       │   └── schemas.py
│       ├── ajil/
│       │   ├── client.py
│       │   ├── models.py
│       │   ├── streaming.py
│       │   ├── structured_output.py
│       │   └── fallback_detection.py
│       ├── codex/
│       │   ├── supervisor.py
│       │   ├── transport.py
│       │   ├── rpc.py
│       │   ├── client.py
│       │   ├── protocol.py
│       │   ├── events.py
│       │   ├── approvals.py
│       │   ├── threads.py
│       │   └── exec_fallback.py
│       ├── jobs/
│       │   ├── service.py
│       │   ├── queue.py
│       │   ├── worker.py
│       │   ├── recovery.py
│       │   ├── cancellation.py
│       │   └── events.py
│       ├── memory/
│       │   ├── service.py
│       │   ├── conversation.py
│       │   ├── project.py
│       │   ├── semantic.py
│       │   ├── summarizer.py
│       │   └── retrieval.py
│       ├── tools/
│       │   ├── registry.py
│       │   ├── base.py
│       │   ├── shell.py
│       │   ├── filesystem.py
│       │   ├── process.py
│       │   ├── git.py
│       │   ├── docker.py
│       │   ├── systemd.py
│       │   ├── network.py
│       │   └── project.py
│       ├── browser/
│       │   ├── service.py
│       │   ├── session.py
│       │   ├── verifier.py
│       │   ├── recording.py
│       │   ├── tracing.py
│       │   └── report.py
│       ├── voice/
│       │   ├── service.py
│       │   ├── ffmpeg.py
│       │   ├── stt.py
│       │   └── tts.py
│       ├── artifacts/
│       │   ├── service.py
│       │   ├── storage.py
│       │   ├── compression.py
│       │   ├── metadata.py
│       │   └── telegram_sender.py
│       ├── db/
│       │   ├── base.py
│       │   ├── session.py
│       │   ├── models.py
│       │   ├── repositories/
│       │   └── migrations/
│       ├── observability/
│       │   ├── logging.py
│       │   ├── context.py
│       │   ├── metrics.py
│       │   └── tracing.py
│       └── common/
│           ├── errors.py
│           ├── ids.py
│           ├── time.py
│           ├── redaction.py
│           └── subprocess.py
├── alembic.ini
├── migrations/
├── scripts/
│   ├── bootstrap.sh
│   ├── doctor.sh
│   ├── dev.sh
│   ├── run_agent.sh
│   ├── run_worker.sh
│   ├── run_scheduler.sh
│   ├── install_codex.sh
│   ├── configure_codex.sh
│   ├── generate_codex_schema.sh
│   ├── install_playwright.sh
│   ├── submodules_init.sh
│   ├── submodules_verify.sh
│   ├── submodules_update.sh
│   ├── apply_submodule_patches.sh
│   ├── smoke_ajil.sh
│   ├── smoke_codex.sh
│   ├── smoke_playwright.sh
│   ├── smoke_telegram.sh
│   └── reset_dev_data.sh
├── deploy/
│   └── systemd/
│       ├── telegram-codex-agent.service
│       ├── telegram-codex-worker.service
│       └── telegram-codex-scheduler.service
├── examples/
│   └── demo_webapp/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── contract/
│   ├── e2e/
│   ├── fixtures/
│   └── fakes/
├── data/
│   ├── inbox/
│   ├── artifacts/
│   ├── work/
│   └── logs/
└── docs/
    ├── ARCHITECTURE.md
    ├── CONFIGURATION.md
    ├── DEVELOPMENT.md
    ├── DEPLOYMENT.md
    ├── TELEGRAM_COMMANDS.md
    ├── CODEX_PROTOCOL.md
    ├── PLAYWRIGHT_VERIFICATION.md
    ├── MEMORY.md
    ├── TROUBLESHOOTING.md
    ├── FUTURE_SECURITY_HARDENING.md
    ├── IMPLEMENTATION_STATUS.md
    ├── TEST_MATRIX.md
    ├── DECISIONS.md
    └── HANDOFF.md
```

Adjust names only when a better coherent structure is required. Keep responsibilities separated.

---

# 8. Single Root Configuration Requirement

All non-secret settings must live in exactly one primary configuration file:

```text
config/agent.yaml
```

All secret and environment-specific values must live in one root environment file:

```text
.env
```

Provide:

```text
.env.example
```

Do not require separate `.env` files inside submodules.

Do not require users to manually duplicate variables into Ajil.

The root Docker Compose file and native process launcher must inject the root environment into all services, including Ajil.

## 8.1 Configuration precedence

Implement this precedence:

```text
1. Hard-coded typed defaults
2. config/agent.yaml
3. Root .env and process environment overrides
4. Explicit CLI flags
```

Environment interpolation in YAML must support:

```yaml
database:
  url: "${DATABASE_URL}"
```

Also support default syntax:

```yaml
api:
  host: "${AGENT_API_HOST:-127.0.0.1}"
```

Fail fast on missing required variables.

Implement:

```bash
agentctl config validate
agentctl config dump
agentctl config dump --redact
agentctl config schema
```

Generate a JSON Schema for the YAML config.

## 8.2 Complete sample `config/agent.yaml`

Create a real config file based on this contract:

```yaml
version: 1

app:
  name: telegram-codex-agent
  environment: development
  language: fa
  timezone: Asia/Tehran
  data_dir: ./data
  work_dir: ./data/work
  log_dir: ./data/logs
  shutdown_timeout_seconds: 30

api:
  enabled: true
  host: "${AGENT_API_HOST:-127.0.0.1}"
  port: "${AGENT_API_PORT:-8090}"
  docs_enabled: true
  metrics_enabled: true

security:
  mode: development_full_access
  auto_approve_codex_requests: true
  allow_arbitrary_shell: true
  allow_host_filesystem: true
  allow_network: true
  allow_docker: true
  allow_systemd: true
  redact_secrets_in_logs: true

telegram:
  enabled: true
  transport: polling
  token_env: TELEGRAM_BOT_TOKEN
  allowed_user_ids: []
  allowed_chat_ids: []
  parse_mode: HTML
  default_reply_language: fa
  progress_update_interval_seconds: 1.5
  typing_action_interval_seconds: 4
  max_text_chunk_chars: 3800
  download_dir: ./data/inbox
  send_text_result: true
  send_voice_result_by_default: false
  send_artifacts_automatically: true
  webhook:
    public_url: ""
    secret_token_env: TELEGRAM_WEBHOOK_SECRET
    listen_host: 127.0.0.1
    listen_port: 8091

database:
  url: "${DATABASE_URL}"
  echo: false
  pool_size: 10
  max_overflow: 20
  pool_recycle_seconds: 1800

redis:
  url: "${REDIS_URL}"
  stream_prefix: agent
  consumer_group: agent-workers
  consumer_name: "${HOSTNAME:-local-worker}"
  blocking_read_ms: 5000
  claim_stale_after_seconds: 120
  event_ttl_seconds: 86400

ajil:
  enabled: true
  base_url: "${AJIL_BASE_URL:-http://127.0.0.1:8080}"
  api_token_env: UAG_AUTH_TOKEN
  api_token_header: "${UAG_AUTH_HEADER_NAME:-x-api-token}"
  admin_token_env: UAG_ADMIN_TOKEN
  admin_token_header: "${UAG_ADMIN_HEADER_NAME:-x-admin-token}"
  timeout_seconds: 90
  connect_timeout_seconds: 10
  retries: 3
  retry_backoff_seconds: 0.5
  reject_local_fallback_for_planning: true
  healthcheck_interval_seconds: 15
  planning:
    capability: chat.completions
    temperature: 0.1
    max_tokens: 4000
    strategy: fallback_chain
    mode: quality_first
    models:
      - provider: gemini
        model: gemini-2.5-flash
        priority: 0
      - provider: groq
        model: llama-3.3-70b-versatile
        priority: 1
  chat:
    strategy: fallback_chain
    mode: latency_first
    stream: true
    models:
      - provider: groq
        model: llama-3.3-70b-versatile
        priority: 0
      - provider: gemini
        model: gemini-2.5-flash
        priority: 1
  vision:
    strategy: fallback_chain
    mode: quality_first
    models:
      - provider: gemini
        model: gemini-2.5-flash
        priority: 0
  embeddings:
    model:
      provider: gemini
      model: gemini-embedding-001
  stt:
    provider: groq
    model: whisper-large-v3-turbo
    language: fa
    response_format: json
  tts:
    enabled: true
    provider: groq
    model: canopylabs/orpheus-v1-english
    voice: diana
    response_format: wav
    fallback_to_text: true

codex:
  enabled: true
  binary: "${CODEX_BINARY:-codex}"
  install_mode: "${CODEX_INSTALL_MODE:-package}"
  home_dir: "${CODEX_HOME}"
  transport: stdio
  app_server_args:
    - app-server
    - --listen
    - stdio://
  startup_timeout_seconds: 30
  request_timeout_seconds: 300
  turn_timeout_seconds: 3600
  max_restart_attempts: 5
  restart_backoff_seconds: 2
  generate_schema_on_start: true
  schema_output_dir: ./generated/codex_app_server_schema
  client:
    name: telegram_codex_agent
    title: Telegram Codex Agent
    version: 0.1.0
    experimental_api: true
  defaults:
    model: "${CODEX_MODEL:-}"
    reasoning_effort: "${CODEX_REASONING_EFFORT:-high}"
    approval_policy: never
    sandbox_mode: danger-full-access
    network_access: true
  thread_scope: user_project_conversation
  resume_existing_threads: true
  auto_accept:
    command_execution: true
    file_changes: true
    permissions: true
    mcp_tools: true
    prefer_session_scope: true
  event_forwarding:
    agent_message_deltas: true
    command_output_deltas: true
    plan_updates: true
    diff_updates: true
    token_usage: true
  exec_fallback:
    enabled: true
    json_mode: true

orchestrator:
  max_plan_retries: 3
  max_steps_per_job: 30
  max_tool_iterations: 50
  max_self_correction_rounds: 5
  require_structured_plan: true
  continue_after_transient_failure: true
  direct_chat_without_job: true
  persist_all_messages: true
  verification_required_for_code_changes: true
  reviewer_enabled: true

jobs:
  worker_concurrency: 2
  per_project_write_lock: true
  allow_parallel_read_jobs: true
  default_timeout_seconds: 3600
  heartbeat_interval_seconds: 10
  stale_job_seconds: 120
  max_attempts: 3
  retry_backoff_seconds: 5
  recover_on_startup: true
  keep_event_history: true

shell:
  enabled: true
  full_access: true
  default_shell: /bin/bash
  login_shell: true
  default_timeout_seconds: 600
  max_output_bytes: 10485760
  inherit_environment: true
  stream_output: true
  kill_process_group_on_cancel: true

git:
  enabled: true
  default_remote: origin
  auto_commit: false
  auto_push: false
  create_worktree_for_concurrent_jobs: true
  include_diff_in_report: true
  max_diff_chars_in_telegram: 12000

docker:
  enabled: true
  binary: docker
  compose_command:
    - docker
    - compose
  default_timeout_seconds: 900

systemd:
  enabled: true
  user_mode_default: true

browser:
  enabled: true
  engine: chromium
  mode: isolated
  headless: true
  default_timeout_ms: 30000
  navigation_timeout_ms: 60000
  viewport:
    width: 1440
    height: 1000
  locale: fa-IR
  timezone_id: Asia/Tehran
  record_video: true
  record_trace: true
  capture_screenshot: true
  capture_console: true
  capture_page_errors: true
  capture_failed_requests: true
  capture_http_errors: true
  cdp:
    enabled: false
    endpoint: "${CHROME_CDP_ENDPOINT:-http://127.0.0.1:9222}"
  desktop_recording:
    enabled: false
    backend: auto
    fps: 20

artifacts:
  storage_backend: local
  root_dir: ./data/artifacts
  retain_days: 30
  max_single_file_bytes: 2000000000
  telegram_direct_upload_limit_bytes: 48000000
  auto_compress_large_video: true
  video_target_height: 720
  video_crf: 28
  create_job_zip: true

voice:
  enabled: true
  ffmpeg_binary: "${FFMPEG_BINARY:-ffmpeg}"
  ffprobe_binary: "${FFPROBE_BINARY:-ffprobe}"
  normalize_input: true
  input_sample_rate: 16000
  input_channels: 1
  telegram_voice_format: ogg
  tts_enabled: true
  send_text_alongside_voice: true

memory:
  enabled: true
  store_raw_messages: true
  summarize_every_messages: 12
  max_recent_messages: 30
  semantic_retrieval_enabled: true
  semantic_top_k: 8
  embedding_dimension: 768
  project_memory_enabled: true
  outcome_memory_enabled: true
  codex_thread_memory_enabled: true

projects:
  default_project_id: ""
  auto_detect_from_message: true
  allow_dynamic_registration: true
  entries: []
```

Implement typed validation for this structure.

---

# 9. Complete Root `.env.example` Contract

Create one root `.env.example` containing all variables required by the root app and Ajil.

Do not include real secrets.

At minimum include the following categories and variables.

```dotenv
# -------------------------------------------------------------------
# Root application
# -------------------------------------------------------------------
APP_ENV=development
CONFIG_PATH=config/agent.yaml
AGENT_API_HOST=127.0.0.1
AGENT_API_PORT=8090
LOG_LEVEL=INFO
LOG_FORMAT=json
TZ=Asia/Tehran
HOSTNAME=local-worker

# -------------------------------------------------------------------
# Telegram
# -------------------------------------------------------------------
TELEGRAM_BOT_TOKEN=
TELEGRAM_ALLOWED_USER_IDS=
TELEGRAM_ALLOWED_CHAT_IDS=
TELEGRAM_WEBHOOK_SECRET=
TELEGRAM_WEBHOOK_PUBLIC_URL=
TELEGRAM_TRANSPORT=polling

# -------------------------------------------------------------------
# Database and Redis
# -------------------------------------------------------------------
POSTGRES_DB=telegram_codex_agent
POSTGRES_USER=agent
POSTGRES_PASSWORD=agent_dev_password
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
DATABASE_URL=postgresql+asyncpg://agent:agent_dev_password@127.0.0.1:5432/telegram_codex_agent

REDIS_HOST=127.0.0.1
REDIS_PORT=6379
REDIS_DB=1
REDIS_URL=redis://127.0.0.1:6379/1

# -------------------------------------------------------------------
# Ajil client
# -------------------------------------------------------------------
AJIL_BASE_URL=http://127.0.0.1:8080

# -------------------------------------------------------------------
# Codex
# -------------------------------------------------------------------
CODEX_BINARY=codex
CODEX_INSTALL_MODE=package
CODEX_HOME=
CODEX_MODEL=
CODEX_REASONING_EFFORT=high
CODEX_APPROVAL_POLICY=never
CODEX_SANDBOX_MODE=danger-full-access
CODEX_NETWORK_ACCESS=true
CODEX_ACCESS_TOKEN=
OPENAI_API_KEY=
RUST_LOG=warn
LOG_FORMAT=json

# -------------------------------------------------------------------
# Playwright and browser
# -------------------------------------------------------------------
PLAYWRIGHT_BROWSERS_PATH=
PLAYWRIGHT_HEADLESS=true
CHROME_CDP_ENDPOINT=http://127.0.0.1:9222
DISPLAY=
XDG_SESSION_TYPE=
FFMPEG_BINARY=ffmpeg
FFPROBE_BINARY=ffprobe

# -------------------------------------------------------------------
# Artifact storage
# -------------------------------------------------------------------
ARTIFACT_ROOT=./data/artifacts
ARTIFACT_RETENTION_DAYS=30

# -------------------------------------------------------------------
# Docker access
# -------------------------------------------------------------------
DOCKER_HOST=
COMPOSE_PROJECT_NAME=telegram-codex-agent

# -------------------------------------------------------------------
# Ajil Unified AI Gateway: app
# -------------------------------------------------------------------
UAG_APP_HOST=0.0.0.0
UAG_APP_PORT=8080
UAG_APP_LOG_LEVEL=INFO
UAG_APP_DOCS_ENABLED=true

# -------------------------------------------------------------------
# Ajil logging and observability
# -------------------------------------------------------------------
UAG_LOG_ENABLED=true
UAG_LOG_JSON=true
UAG_LOG_HTTP_REQUESTS=true
UAG_LOG_ROUTER_DISPATCH=true
UAG_LOG_PROVIDER_ATTEMPTS=true
UAG_LOG_WEBSOCKET=true
UAG_LOG_MAX_EVENTS=50000
UAG_USAGE_MAX_EVENTS=20000

# -------------------------------------------------------------------
# Ajil client authentication
# -------------------------------------------------------------------
UAG_AUTH_ENABLED=true
UAG_AUTH_TOKEN=replace_with_random_client_token
UAG_AUTH_HEADER_NAME=x-api-token

# -------------------------------------------------------------------
# Ajil admin authentication
# -------------------------------------------------------------------
UAG_ADMIN_ENABLED=true
UAG_ADMIN_TOKEN=replace_with_random_admin_token
UAG_ADMIN_HEADER_NAME=x-admin-token

# -------------------------------------------------------------------
# Ajil router
# -------------------------------------------------------------------
UAG_ROUTER_DEFAULT_STRATEGY=fallback_chain
UAG_ROUTER_DEFAULT_MODE=latency_first
UAG_ROUTER_PARALLEL_TIMEOUT_SEC=25
UAG_ROUTER_MAX_CANDIDATES=6
UAG_ROUTER_FALLBACK_MAX_ATTEMPTS=6
UAG_ROUTER_FALLBACK_ATTEMPT_TIMEOUT_SEC=12
UAG_ROUTER_FALLBACK_ROUND_BACKOFF_SEC=0.2
UAG_ROUTER_RETRYABLE_STATUS_CODES=408,409,425,429,500,502,503,504
UAG_ROUTER_STRICT_RATE_LIMIT_ERRORS_ONLY=false

# -------------------------------------------------------------------
# Ajil Redis
# -------------------------------------------------------------------
UAG_REDIS_REQUIRED=false
UAG_REDIS_URL=redis://127.0.0.1:6379/0
UAG_REDIS_URL_DOCKER=redis://redis:6379/0
UAG_REDIS_HOST_PORT=6379
UAG_REDIS_KEY_PREFIX=uag
UAG_REDIS_DEFAULT_LIMIT_PER_MINUTE=120

# -------------------------------------------------------------------
# Ajil outbound proxy
# -------------------------------------------------------------------
UAG_PROXY_ENABLED=false
UAG_PROXY_URL=socks5://127.0.0.1:2080
UAG_PROXY_URL_DOCKER=http://proxy2080:2080
UAG_PROXY_USE_COMPOSE_SERVICE=false

# -------------------------------------------------------------------
# Ajil Docker build network/proxy
# -------------------------------------------------------------------
UAG_DOCKER_BUILD_NETWORK=default
UAG_BUILD_HTTP_PROXY=
UAG_BUILD_HTTPS_PROXY=
UAG_BUILD_ALL_PROXY=
UAG_BUILD_NO_PROXY=127.0.0.1,localhost,redis,postgres,gateway
UAG_PIP_INDEX_URL=
UAG_PIP_EXTRA_INDEX_URL=

# -------------------------------------------------------------------
# Ajil Gemini provider
# -------------------------------------------------------------------
UAG_GEMINI_ENABLED=true
UAG_GEMINI_MODE=gemini_direct
UAG_GEMINI_BASE_URL=https://generativelanguage.googleapis.com
UAG_GEMINI_API_VERSION=v1beta
UAG_GEMINI_DEFAULT_MODEL=gemini-2.5-flash
UAG_GEMINI_API_KEYS=
UAG_GEMINI_RETRY_ON_429=true
UAG_GEMINI_RETRY_ON_5XX=true
UAG_GEMINI_MAX_RETRIES_PER_KEY=2
UAG_GEMINI_MAX_RETRIES_ON_5XX=4
UAG_GEMINI_RETRY_BACKOFF_SEC=0.35
UAG_GEMINI_COOLOFF_SEC=20
UAG_GEMINI_MIN_INTERVAL_SEC=0
UAG_GEMINI_WORKER_BASE_URLS=
UAG_GEMINI_WORKER_ROUTE_PREFIX=/gemini
UAG_GEMINI_WORKER_AUTH_TOKEN=
UAG_GEMINI_WORKER_AUTH_HEADER_NAME=x-worker-auth

# -------------------------------------------------------------------
# Ajil Groq provider
# -------------------------------------------------------------------
UAG_GROQ_ENABLED=true
UAG_GROQ_BASE_URL=https://api.groq.com/openai/v1
UAG_GROQ_API_KEYS=
UAG_GROQ_RETRY_ON_429=true
UAG_GROQ_RETRY_ON_5XX=true
UAG_GROQ_MAX_RETRIES_PER_KEY=2
UAG_GROQ_MAX_RETRIES_ON_5XX=4
UAG_GROQ_RETRY_BACKOFF_SEC=0.35
UAG_GROQ_COOLOFF_SEC=20
UAG_GROQ_MIN_INTERVAL_SEC=0

UAG_GROQ_STT_PRIMARY_MODEL=whisper-large-v3-turbo
UAG_GROQ_STT_FALLBACK_MODEL=whisper-large-v3
UAG_GROQ_STT_LANGUAGE=fa
UAG_GROQ_STT_TEMPERATURE=0
UAG_GROQ_STT_RESPONSE_FORMAT=json
UAG_GROQ_STT_PROMPT=

UAG_GROQ_TTS_DEFAULT_MODEL=canopylabs/orpheus-v1-english
UAG_GROQ_TTS_DEFAULT_VOICE=diana
UAG_GROQ_TTS_DEFAULT_RESPONSE_FORMAT=wav

# -------------------------------------------------------------------
# Ajil Pollinations provider
# -------------------------------------------------------------------
UAG_POLLINATIONS_ENABLED=true
UAG_POLLINATIONS_BASE_URL=https://gen.pollinations.ai
UAG_POLLINATIONS_API_KEYS=
UAG_POLLINATIONS_DEFAULT_IMAGE_MODEL=flux
UAG_POLLINATIONS_MAX_ATTEMPTS_PER_REQUEST=6
UAG_POLLINATIONS_RETRY_STATUS_CODES=402,429,500,502,503,504
UAG_POLLINATIONS_RETRY_BACKOFF_SEC=0.35
UAG_POLLINATIONS_KEY_COOLDOWN_SEC=20
UAG_POLLINATIONS_LOCAL_PLACEHOLDER_ON_FAILURE=true
UAG_IMAGE_DEFAULT_N=1
UAG_IMAGE_DEFAULT_SIZE=1024x1024
UAG_IMAGE_DEFAULT_QUALITY=standard
UAG_IMAGE_DEFAULT_RESPONSE_FORMAT=url

# -------------------------------------------------------------------
# Backward-compatible provider aliases used by nested modules
# -------------------------------------------------------------------
GROQ_API_KEYS=
GROQ_API_KEY=
GEMINI_API_KEYS=
POLLINATIONS_API_KEYS=
POLLINATIONS_API_KEY=

# -------------------------------------------------------------------
# Optional live integration-test flags
# -------------------------------------------------------------------
RUN_LIVE_AJIL_TESTS=false
RUN_LIVE_CODEX_TESTS=false
RUN_LIVE_TELEGRAM_TESTS=false
RUN_LIVE_PLAYWRIGHT_TESTS=true
TEST_TELEGRAM_CHAT_ID=
```

Inspect the current Ajil submodule's `.env.example` and README during implementation. If the submodule defines additional variables, merge them into the single root `.env.example`.

Add an automated contract test that compares required Ajil environment variable names against the root `.env.example` and fails when a required variable is missing.

---

# 10. Docker Compose and Runtime Topology

Create one root `docker-compose.yml`.

Required infrastructure services:

```text
postgres
redis
ajil_gateway
```

Optional profiles:

```text
ajil_proxy
local_telegram_bot_api
prometheus
grafana
```

The root agent and Codex worker should run natively by default in development full-access mode because they need direct access to host projects, processes, desktop/browser, Git credentials, Docker, and Codex authentication.

Provide an optional containerized profile, but native runtime is the supported default.

## 10.1 PostgreSQL

Use a pgvector-enabled PostgreSQL image.

Requirements:

- Persistent volume
- Health check
- Extension creation
- Database migrations
- UTF-8
- Stable host port from `.env`

## 10.2 Redis

Requirements:

- Persistent or append-only development storage
- Health check
- Separate logical DB or key namespace from Ajil
- Root config references

## 10.3 Ajil

Build from:

```text
modules/ajil_uag
```

Use the root `.env` through `env_file`.

Override Ajil Redis URL inside Compose to point to the Compose Redis service.

Expose Ajil only on localhost by default.

Health check:

```text
GET /health
```

Initialize nested submodules before build.

## 10.4 Agent native runner

Implement:

```bash
make infra-up
make migrate
make dev
```

`make dev` should:

- Validate config
- Verify Ajil health
- Verify database
- Verify Redis
- Verify Codex executable and auth state
- Verify Playwright browser
- Start API
- Start Telegram polling
- Start worker
- Stream readable logs

Also provide split commands:

```bash
make api
make bot
make worker
make scheduler
```

## 10.5 Systemd user services

Provide tested user-level unit files.

They must:

- Load root `.env`
- Use the project virtual environment
- Start after network
- Restart on failure
- Write logs to journal and structured file
- Use the repository root as working directory

Add:

```bash
make systemd-install
make systemd-start
make systemd-status
make systemd-stop
```

---

# 11. Core Domain Models

Use UUIDv7 or sortable UUID/ULID identifiers where practical.

Implement database models and repositories for:

## 11.1 User

Fields:

```text
id
telegram_user_id
username
first_name
last_name
language_code
is_active
created_at
updated_at
last_seen_at
preferences_json
```

## 11.2 Chat

```text
id
telegram_chat_id
chat_type
title
created_at
updated_at
```

## 11.3 Conversation

```text
id
user_id
chat_id
project_id nullable
title
status
created_at
updated_at
last_message_at
summary
metadata_json
```

## 11.4 Project

```text
id
slug
name
root_path
description
default_branch
default_remote
run_commands_json
test_commands_json
lint_commands_json
build_commands_json
browser_url
browser_config_json
environment_json
is_active
created_at
updated_at
```

## 11.5 Message

```text
id
conversation_id
telegram_message_id nullable
role
content_type
text
file_path nullable
mime_type nullable
metadata_json
created_at
embedding nullable
```

## 11.6 Job

```text
id
conversation_id
project_id nullable
parent_job_id nullable
request_message_id nullable
intent
objective
state
priority
attempt
max_attempts
execution_mode
planner_output_json
verification_policy_json
result_summary
error_code
error_message
created_at
queued_at
started_at
completed_at
cancelled_at
heartbeat_at
worker_id
codex_thread_id nullable
codex_turn_id nullable
metadata_json
```

Job states:

```text
received
normalizing
planning
planned
queued
running
waiting_external
verifying
reporting
completed
failed
cancel_requested
cancelled
interrupted
recovering
```

State transitions must be explicit and tested.

## 11.7 JobStep

```text
id
job_id
sequence
kind
name
description
tool_name nullable
input_json
output_json
state
started_at
completed_at
error_message
```

## 11.8 JobEvent

```text
id
job_id
sequence
event_type
level
message
data_json
created_at
```

## 11.9 CodexThread

```text
id
user_id
conversation_id
project_id
codex_thread_id
status
cwd
model
approval_policy
sandbox_mode
last_turn_id
created_at
updated_at
last_used_at
metadata_json
```

## 11.10 Artifact

```text
id
job_id
kind
name
path
mime_type
size_bytes
sha256
telegram_file_id nullable
created_at
expires_at nullable
metadata_json
```

Artifact kinds:

```text
log
stdout
stderr
diff
patch
screenshot
video
trace
html_report
json_report
audio
document
archive
download
other
```

## 11.11 MemoryRecord

```text
id
user_id
conversation_id nullable
project_id nullable
memory_type
title
content
source_message_ids_json
importance
embedding nullable
created_at
updated_at
last_accessed_at
metadata_json
```

Memory types:

```text
conversation_summary
user_preference
project_fact
procedure
decision
task_outcome
error_solution
codebase_fact
manual_note
```

## 11.12 WorkerLease or Heartbeat

Persist enough information to recover stale jobs.

## 11.13 ApprovalRecord

Even though approvals are automatically accepted in this phase, persist:

```text
id
job_id
codex_request_id
approval_type
request_json
decision
scope
auto_approved
created_at
resolved_at
```

This supports later security hardening.

---

# 12. Input Normalization

Normalize every incoming Telegram update into one internal schema.

Example:

```json
{
  "input_id": "inp_...",
  "user_id": "usr_...",
  "chat_id": "chat_...",
  "conversation_id": "conv_...",
  "telegram_message_id": 123,
  "kind": "text",
  "text": "پروژه را اجرا کن و تست بگیر",
  "attachments": [],
  "reply_to": null,
  "received_at": "..."
}
```

Attachment schema:

```json
{
  "kind": "photo",
  "telegram_file_id": "...",
  "file_unique_id": "...",
  "local_path": "data/inbox/...",
  "mime_type": "image/jpeg",
  "size_bytes": 12345,
  "caption": ""
}
```

Requirements:

- Preserve the original Telegram metadata.
- Generate deterministic local paths.
- Avoid filename collisions.
- Compute SHA-256.
- Store message before starting execution.
- Support captions.
- Support reply context.
- Support forwarded-message metadata without trusting it as instruction authority.
- Convert Telegram voice OGG/Opus to normalized WAV before STT.
- For video analysis, preserve original and optionally extract frames.

---

# 13. Telegram Bot Features

Implement the following commands:

```text
/start
/help
/status
/health
/projects
/project
/project_add
/project_remove
/new
/resume
/jobs
/job
/stop
/retry
/artifacts
/memory
/remember
/forget
/mode
/voice
/browser
/codex
/logs
/config
```

Required behavior:

## `/start`

- Register user and chat.
- Show a concise Persian introduction.
- Show active project.
- Show capability summary.
- Display command keyboard.

## `/project`

- Show active project.
- Allow selection by inline keyboard.
- Accept a slug or path.
- Persist selection in conversation.

## `/project_add`

Accept:

```text
/project_add <slug> <absolute_path>
```

Then inspect repository metadata and create a project profile.

## `/new`

- Start a new logical conversation.
- Optionally start a new Codex thread.

## `/resume`

- Resume latest conversation or named job/thread.

## `/status`

Show:

- Runtime health
- Ajil health
- Codex health
- Database
- Redis
- Current project
- Running jobs

## `/jobs`

Show active and recent jobs.

## `/job <id>`

Show:

- State
- Current step
- Elapsed time
- Last event
- Artifacts
- Codex thread/turn summary

## `/stop`

- Cancel active job.
- Send `turn/interrupt` if Codex is active.
- Terminate active subprocess process group.
- Stop Playwright context.
- Mark job cancelled.

## `/retry`

Create a retry attempt with prior context.

## `/artifacts`

List and resend job artifacts.

## `/memory`

Show memory summary and recent project facts.

## `/remember`

Store a manual memory record.

## `/forget`

Delete or deactivate the requested memory record.

## `/mode`

Modes:

```text
auto
chat
code
shell
browser
voice
```

`auto` is the default.

## `/voice`

Toggle voice replies.

## `/browser`

Show browser mode and allow switching:

```text
isolated_headless
isolated_headed
cdp
```

## `/codex`

Show Codex executable, version, auth state, thread ID, and current defaults.

## `/logs`

Send recent runtime logs with redaction.

## `/config`

Show a redacted configuration summary.

### Progress UI

For long jobs:

- Send one initial progress message.
- Edit it no more frequently than the configured interval.
- Show state, current step, elapsed time, and last useful event.
- Do not flood chat with every token.
- Send important milestone messages separately.
- Provide a stop button.
- Send a final report.

### Message formatting

- Persian-friendly RTL text.
- Escape Telegram HTML/Markdown correctly.
- Split messages below platform limits.
- Keep code blocks intact when possible.
- Send large logs as files rather than giant messages.

---

# 14. Intent Routing and Structured Planning

Implement a deterministic router with LLM-assisted classification.

Intent enum:

```text
chat
question
code_task
project_task
shell_task
git_task
docker_task
system_task
browser_task
file_analysis
image_analysis
voice_chat
hybrid_task
memory_task
status_task
unknown
```

Execution target enum:

```text
direct_ajil
codex
shell
git
docker
systemd
playwright
file_tools
memory
hybrid
none
```

Create a Pydantic schema similar to:

```python
class PlannedStep(BaseModel):
    sequence: int
    name: str
    description: str
    executor: Literal[
        "ajil", "codex", "shell", "git", "docker",
        "systemd", "playwright", "filesystem", "memory"
    ]
    command_hint: str | None = None
    expected_output: str | None = None
    continue_on_failure: bool = False

class VerificationPlan(BaseModel):
    required: bool = False
    run_tests: bool = False
    run_lint: bool = False
    run_build: bool = False
    browser_check: bool = False
    capture_screenshot: bool = False
    capture_video: bool = False
    capture_trace: bool = False
    inspect_console_errors: bool = False
    inspect_http_errors: bool = False

class ExecutionPlan(BaseModel):
    intent: IntentType
    objective: str
    project_id: str | None
    requires_job: bool
    primary_executor: ExecutionTarget
    use_codex: bool
    use_memory: bool
    response_mode: Literal["text", "voice", "text_and_voice"]
    steps: list[PlannedStep]
    verification: VerificationPlan
    success_criteria: list[str]
    assumptions: list[str]
```

Planner requirements:

- Use low temperature.
- Request JSON only.
- Validate with Pydantic.
- Retry malformed output.
- On retry, include validation errors.
- Maximum retry count from config.
- Reject Ajil local fallback for plans.
- Bound number of steps.
- Never execute a raw command solely because it appears in LLM prose.
- Store the final plan on the Job.

Heuristic bypasses:

- `/status` does not need an LLM.
- `/stop` does not need an LLM.
- Explicit `/mode shell` may route directly.
- Simple greetings use direct chat.
- Voice is transcribed, then routed normally.

---

# 15. Orchestrator State Machine

Implement a real state machine, not scattered status strings.

Recommended flow:

```text
RECEIVED
  -> NORMALIZING
  -> CONTEXT_RESOLUTION
  -> MEMORY_RETRIEVAL
  -> CLASSIFYING
  -> PLANNING
  -> PLANNED
  -> QUEUED
  -> RUNNING
  -> VERIFYING
  -> REPORTING
  -> COMPLETED
```

Failure/cancellation branches:

```text
ANY ACTIVE STATE
  -> CANCEL_REQUESTED
  -> CANCELLED

RUNNING/VERIFYING
  -> RECOVERING
  -> RUNNING or FAILED

ANY STATE
  -> FAILED
```

Requirements:

- Transition method validates allowed previous states.
- Every transition creates a JobEvent.
- State changes and events are committed atomically.
- Duplicate Telegram updates must not create duplicate jobs.
- Workers must use leases/heartbeats.
- On startup, recover stale jobs according to policy.
- A project write lock prevents simultaneous conflicting Codex edits.
- Read-only tasks may run concurrently.
- Cancellation propagates to all active child processes.

---

# 16. Job Queue and Worker Design

Use PostgreSQL as the source of truth and Redis Streams for delivery and live events.

## Queue flow

1. Create Job in PostgreSQL.
2. Commit.
3. Publish job ID to Redis Stream.
4. Worker consumer group claims it.
5. Worker obtains DB lease.
6. Worker updates heartbeat.
7. Worker emits events to DB and Redis.
8. Telegram progress subscriber edits the message.
9. Completion event triggers final report.

Requirements:

- Idempotent job claiming.
- At-least-once delivery safe behavior.
- Attempts tracked.
- Stale pending messages reclaimed.
- Worker crash recovery.
- Graceful shutdown.
- Per-job cancellation token.
- Per-project lock.
- Process registry for subprocess termination.
- Job timeout.
- Step timeout.
- Output byte cap.
- Persist full output to artifact files even when Telegram summary is truncated.

Implement a local in-memory queue adapter for unit tests.

---

# 17. Ajil Client

Create a fully typed async client.

Required methods:

```python
health()
list_models()
list_model_catalog()
chat(...)
chat_stream(...)
responses(...)
embeddings(...)
image_generation(...)
transcribe(...)
speech(...)
orchestrate(...)
```

Requirements:

- `httpx.AsyncClient`
- Configurable token/header
- Request IDs
- Timeouts
- Retries
- Backoff
- Stream cancellation
- Capture provider/model winner headers
- JSON parsing errors
- Binary audio handling
- Multipart transcription
- Response metadata
- Tests using `respx` or equivalent
- Fake Ajil server fixture

Structured output helper:

```python
await ajil.structured_chat(
    schema=ExecutionPlan,
    messages=[...],
    routing=...
)
```

It must:

- Inject schema instructions.
- Parse fenced or plain JSON.
- Validate.
- Retry with validation feedback.
- Reject fallback.
- Return typed model and raw metadata.

Streaming chat must aggregate deltas while also forwarding progress where useful.

---

# 18. Codex App Server Client

This is a critical component and must be production-quality.

## 18.1 Process supervisor

Implement:

- Resolve binary
- Check `codex --version`
- Spawn App Server with asyncio subprocess
- New process group/session
- Async stdin writer
- Async stdout JSONL reader
- Async stderr reader
- Startup timeout
- Unexpected exit detection
- Exponential restart
- Health state
- Graceful shutdown
- Force kill fallback
- Metrics

## 18.2 Protocol initialization

On connection:

1. Send `initialize` with client metadata.
2. Wait for result.
3. Send `initialized` notification.
4. Mark connection ready.
5. Optionally call `account/read`.
6. Generate/store capability snapshot.

## 18.3 RPC layer

Implement:

- Monotonic request IDs
- Pending request futures
- Timeout
- Error response mapping
- Notification handlers
- Server-initiated request handlers
- Concurrent requests
- Bounded queues
- Backpressure
- Unknown event logging
- Clean cancellation

## 18.4 Thread operations

Implement methods:

```python
start_thread(...)
resume_thread(...)
read_thread(...)
fork_thread(...)
archive_thread(...)
```

Start/resume with:

- cwd
- model
- approval policy
- sandbox policy
- project trust/full access as supported by installed schema
- optional experimental capabilities

Persist returned thread.

## 18.5 Turn operations

Implement:

```python
start_turn(thread_id, inputs, overrides, output_schema=None)
interrupt_turn(thread_id, turn_id)
wait_for_turn(...)
```

Input support:

- Text
- Inline data URL image
- Local image path where supported

## 18.6 Event model

Normalize Codex events into internal events:

```text
codex.thread.started
codex.turn.started
codex.turn.plan_updated
codex.item.started
codex.agent.delta
codex.command.started
codex.command.output
codex.command.completed
codex.file_change.started
codex.file_change.approval_requested
codex.diff.updated
codex.token_usage.updated
codex.turn.completed
codex.turn.failed
codex.warning
```

Persist important events.

Do not persist every tiny token delta forever unless configured. Aggregate deltas.

## 18.7 Automatic approval bridge

Handle current and version-specific approval request names discovered from generated schema.

When full-access auto-approval is enabled:

- Command approval -> accept or accept for session
- File change approval -> accept
- Permission request -> grant requested subset with session scope where supported
- MCP approval -> approve when recognizable
- Log approval record
- Resolve request promptly

When a request shape is unknown:

- Store raw request.
- Log error.
- Avoid deadlocking forever.
- In development mode, use schema-based generic acceptance only when safely inferable.
- Otherwise fail the turn with a clear diagnostic artifact.

## 18.8 Full-access configuration

Implement `scripts/configure_codex.sh` that creates or updates the configured Codex `config.toml` without destroying unrelated user settings.

Required values:

```toml
approval_policy = "never"
sandbox_mode = "danger-full-access"

[sandbox_workspace_write]
network_access = true
```

The exact active Codex version may support additional options. Inspect official schema/help and document effective settings.

Also pass per-thread or per-turn overrides when supported, because relying only on global config may be inconsistent across versions.

## 18.9 Auth diagnostics

Implement:

```bash
agentctl codex status
agentctl codex login
agentctl codex schema
agentctl codex smoke
```

`status` should show:

- Binary path
- Version
- App Server health
- Account/auth state
- Active model
- Full-access settings
- Current thread counts

Do not expose tokens.

## 18.10 Codex task prompt construction

For a code job, send Codex a precise task envelope containing:

- User request
- Project path
- Current branch
- Relevant memory
- Known project commands
- Required acceptance criteria
- Required tests
- Required Playwright verification
- Artifact output directory
- Instruction to inspect existing code before editing
- Instruction not to stop at explanation
- Instruction to run tests and fix failures
- Instruction to summarize changed files
- Instruction to avoid modifying unrelated files

Codex should be allowed to operate naturally inside the project rather than micromanaged command-by-command.

---

# 19. Direct Host Tool Layer

Implement a registry with typed tool interfaces.

Each tool call must have:

```text
name
description
input schema
output schema
timeout
cancellation support
streaming support
artifact support
```

Required tools:

## 19.1 Shell

Capabilities:

- Run arbitrary command
- Set cwd
- Set environment
- Stream stdout/stderr
- PTY optional
- Timeout
- Process group cancellation
- Exit code
- Output truncation metadata
- Full output artifact

## 19.2 Filesystem

Capabilities:

- Read text/binary
- Write
- Append
- List
- Glob
- Find
- Copy
- Move
- Remove
- Stat
- Hash
- Archive
- Extract

## 19.3 Process

Capabilities:

- List processes
- Inspect process
- Start detached process
- Stop process
- Wait
- Capture logs
- Check port owner

## 19.4 Git

Capabilities:

- Status
- Diff
- Log
- Branch
- Checkout
- Create branch
- Worktree
- Add
- Commit
- Pull
- Fetch
- Push
- Remote info
- Changed files
- Restore
- Stash

Do not automatically rewrite history.

## 19.5 Docker

Capabilities:

- `docker ps`
- inspect
- logs
- restart
- stop
- start
- exec
- compose ps
- compose up/down
- compose build
- compose logs
- health wait

## 19.6 Systemd

Capabilities:

- User and system service status
- Start/stop/restart
- Journal logs
- Enable/disable where configured

## 19.7 Network

Capabilities:

- Port check
- HTTP health request
- DNS check
- Socket check
- Curl-like diagnostic through `httpx` or shell

## 19.8 Project

Capabilities:

- Detect language/framework
- Detect package manager
- Detect test/build/run commands
- Detect Git root
- Detect README instructions
- Register project
- Update profile

Tools must be independently unit-tested.

---

# 20. Project Registry and Context

Projects may be defined in `config/agent.yaml` or dynamically registered in the database.

On project registration, detect:

- Absolute root path
- Git root
- Repository remote
- Default branch
- Current branch
- Languages
- Frameworks
- Package managers
- Test commands
- Build commands
- Lint commands
- Run commands
- Docker Compose files
- Browser URL
- Known ports
- README and AGENTS instructions

Create a generated project profile but allow user overrides.

Before a code task, collect a compact context:

```text
project name
path
branch
git status
recent commits
detected stack
configured commands
relevant memories
active server state
```

Do not send the entire repository into the planner. Codex can inspect it locally.

Support multiple projects and explicit switching.

For concurrent write jobs, create a Git worktree when enabled.

---

# 21. Persistent Memory

Build memory as a first-class subsystem.

## 21.1 Memory layers

### Working memory

Current job state, plan, step outputs, active process IDs.

### Conversation memory

Recent messages and summaries.

### User preference memory

Examples:

- Persian responses
- Preferred verbosity
- Preferred project
- Whether voice replies are enabled

### Project memory

Examples:

- Project commands
- Known architecture
- Frequent failures
- Important paths
- Ports
- Test strategy
- Prior solutions

### Outcome memory

What was tried, what succeeded, what failed, and final verification.

### Codex continuity

Codex thread mapping and last turn metadata.

## 21.2 Summarization

After configured message count:

- Summarize older messages.
- Keep recent raw messages.
- Persist summary.
- Do not delete source messages by default.
- Include decisions, unresolved items, and project facts.

## 21.3 Semantic retrieval

Use Ajil embeddings.

Store vectors in pgvector.

Retrieve by:

- user
- conversation
- project
- memory type
- similarity
- recency
- importance

Build a combined score.

Do not inject irrelevant memories.

## 21.4 Memory commands

Implement:

```text
/remember <text>
/memory
/forget <id or description>
```

## 21.5 Post-job memory

At successful or failed completion, create a task outcome memory containing:

- Objective
- Files changed
- Commands run
- Errors
- Fix
- Tests
- Browser verification
- Remaining issues

---

# 22. Voice Assistant

## 22.1 Input flow

```text
Telegram voice/audio
  -> download
  -> FFmpeg normalization
  -> Ajil STT
  -> persist transcript
  -> normal intent pipeline
```

Normalization command should produce mono 16 kHz WAV unless provider requires another format.

Capture:

- Duration
- Original codec
- Normalized path
- Transcript
- Detected language
- STT model/provider

## 22.2 Output flow

```text
Final answer
  -> Ajil TTS
  -> FFmpeg conversion to Telegram-compatible OGG/Opus
  -> sendVoice
```

If Persian TTS is not available:

- Send Persian text.
- Optionally send supported voice only when configured.
- Do not fail the whole job.

## 22.3 Voice behavior

A voice message may request a coding/system task. It is not merely chat.

The transcript must enter the same orchestrator.

Store original and normalized audio as artifacts when configured.

---

# 23. File, Image, and Video Handling

## Images

Support:

- Ajil vision analysis
- Passing local image to Codex where supported
- OCR only when needed
- Screenshot comparison
- User-provided UI bug screenshots

## Documents

Support:

- Plain text
- Markdown
- JSON
- YAML
- CSV
- PDF text extraction
- DOCX text extraction where practical
- ZIP extraction to controlled work directory
- Source-code files

Create adapters rather than embedding all parsing in Telegram handlers.

## Videos

Support:

- Download
- Metadata probe
- Extract representative frames
- Optional audio transcription
- Pass selected frames to vision
- Preserve original
- Summarize findings

Large file operations must be asynchronous and cancellable.

---

# 24. Playwright Verification

Build a dedicated browser verification service.

## 24.1 Session modes

### Isolated

Launch a new browser/context.

### CDP

Connect to:

```text
http://127.0.0.1:9222
```

Use for an already-authenticated browser only when configured.

### Headed/Xvfb

Support visible execution and recording.

## 24.2 Verification request schema

```python
class BrowserVerificationRequest(BaseModel):
    job_id: str
    url: str
    mode: Literal["isolated", "cdp"]
    headless: bool
    steps: list[BrowserAction]
    assertions: list[BrowserAssertion]
    screenshot: bool = True
    video: bool = True
    trace: bool = True
    fail_on_console_error: bool = True
    fail_on_page_error: bool = True
    fail_on_http_5xx: bool = True
```

Actions:

```text
goto
click
fill
press
select
wait_for
upload
download
evaluate
screenshot
```

Assertions:

```text
url
title
visible
hidden
text
value
count
response_status
no_console_errors
no_page_errors
```

## 24.3 Artifact output

Per browser verification:

```text
browser-result.json
browser-actions.json
console.json
page-errors.json
network-errors.json
http-errors.json
final.png
video.webm
trace.zip
report.html
```

## 24.4 Code task verification

After Codex changes code:

1. Run configured tests.
2. Run lint.
3. Run build.
4. Start application.
5. Wait for health URL.
6. Open browser.
7. Execute scenario.
8. Assert expected result.
9. Capture artifacts.
10. Stop application if the agent started it.
11. Include result in final report.

## 24.5 Visual semantic review

Optionally send final screenshot to Ajil Vision with a structured question:

- Does the requested feature appear?
- Is there an obvious error page?
- Are critical elements visible?
- Does the screenshot match the success criteria?

This is supplementary. Deterministic assertions remain primary.

---

# 25. Desktop Recording

Implement a recorder abstraction.

Backends:

```text
playwright_video
x11_ffmpeg
wayland_wf_recorder
xvfb_ffmpeg
disabled
```

Auto-detect.

Requirements:

- Start before the visible verification.
- Stop in `finally`.
- Handle process cancellation.
- Validate output file.
- Compress if needed.
- Attach recording metadata.
- Send to Telegram or include in ZIP.

If full desktop recording cannot work in the current session type, fall back to Playwright video and clearly report the fallback.

---

# 26. Artifact Manager

Artifacts must be first-class records.

Storage layout:

```text
data/artifacts/YYYY/MM/DD/<job_id>/
```

Example:

```text
request.json
plan.json
events.jsonl
stdout.log
stderr.log
codex.log
diff.patch
tests.log
lint.log
build.log
browser-result.json
screenshot.png
video.webm
trace.zip
report.html
summary.md
job-artifacts.zip
```

Requirements:

- SHA-256
- Size
- MIME type
- Atomic writes
- Database metadata
- Retention
- Optional ZIP
- Telegram upload
- Reuse Telegram file IDs after first upload
- Video compression through FFmpeg
- Send direct files under configured threshold
- Split or compress larger files
- Never silently discard an artifact

Final job report must link artifact IDs.

---

# 27. Reports to Telegram

A final report should contain:

```text
Job ID
Objective
Project
Final status
Duration
Summary of actions
Files changed
Git status
Tests
Lint
Build
Browser verification
Console/network errors
Screenshot/video/trace availability
Codex thread
Remaining issues
```

Persian template example:

```text
✅ کار با موفقیت انجام شد

شناسه کار: ...
پروژه: ...
مدت: ...

خلاصه:
...

فایل‌های تغییرکرده:
...

آزمون‌ها:
- Unit tests: PASS
- Lint: PASS
- Build: PASS
- Browser verification: PASS

خروجی‌ها:
- Screenshot
- Video
- Trace
- Diff
```

For failure:

- State exactly what failed.
- Include last useful error.
- Include attempted fixes.
- Include artifacts.
- Suggest the next automatic retry.
- Do not claim success when verification failed.

---

# 28. Admin and Health API

Implement a local FastAPI control plane.

Endpoints:

```text
GET  /health
GET  /ready
GET  /version
GET  /config/redacted
GET  /projects
GET  /projects/{id}
POST /projects
GET  /jobs
GET  /jobs/{id}
POST /jobs/{id}/cancel
POST /jobs/{id}/retry
GET  /jobs/{id}/events
GET  /jobs/{id}/artifacts
GET  /codex/status
POST /codex/restart
GET  /ajil/status
GET  /metrics
```

Optional WebSocket/SSE:

```text
GET /jobs/{id}/stream
```

Health distinction:

- Liveness: process is alive
- Readiness: DB, Redis, Ajil, worker, and Codex are usable

Do not require this API to be publicly exposed.

---

# 29. Observability

Use structured JSON logs.

Every log/event should carry available context:

```text
request_id
input_id
user_id
chat_id
conversation_id
job_id
step_id
project_id
codex_thread_id
codex_turn_id
worker_id
```

Implement context variables.

Metrics:

```text
jobs_total
jobs_active
jobs_failed_total
job_duration_seconds
codex_process_restarts_total
codex_turn_duration_seconds
ajil_requests_total
ajil_failures_total
telegram_updates_total
telegram_errors_total
tool_calls_total
tool_failures_total
browser_verifications_total
artifact_bytes_total
queue_lag_seconds
```

Add redaction filters.

---

# 30. Common Use Cases That Must Work

## 30.1 Normal chat

User:

```text
سلام، امروز چه کمکی می‌تونی بکنی؟
```

Flow:

- Direct Ajil chat
- Conversation persistence
- Persian response
- No unnecessary Codex job

## 30.2 Voice chat

User sends voice.

Flow:

- STT
- Chat response
- Optional TTS
- Text also sent

## 30.3 Code bug fix

User:

```text
برو پروژه Takane، تست‌ها را اجرا کن، مشکل را پیدا کن و درستش کن.
```

Flow:

- Resolve project
- Create job
- Retrieve memory
- Plan
- Start/resume Codex thread
- Codex inspects and edits
- Tests
- Summary
- Diff artifact

## 30.4 Code + browser verification

User:

```text
این فیچر را پیاده کن، برنامه را اجرا کن، با مرورگر تست کن و عکس و ویدیو بفرست.
```

Flow:

- Codex implementation
- Test/build
- Start app
- Playwright scenario
- Screenshot/video/trace
- Vision review optional
- Telegram report

## 30.5 Docker diagnostic

User:

```text
ببین چه کانتینرهایی بالا هستند و چرا API کار نمی‌کند.
```

Flow:

- Docker tool
- Logs
- Health requests
- Optional Codex analysis if code-related
- Report

## 30.6 Shell task

User:

```text
فضای دیسک را بررسی کن و بگو چه چیزی بیشترین فضا را گرفته.
```

Flow:

- Direct host shell
- Summarize
- Attach full output if large

## 30.7 Git task

User:

```text
تغییرات پروژه را خلاصه کن و یک کامیت مناسب بساز.
```

Flow:

- Git status/diff
- Optional Ajil summary
- Commit
- Report commit hash

## 30.8 Multi-project task

User switches project and context remains isolated.

## 30.9 Restart recovery

Kill worker during a long job.

Expected:

- Job becomes stale.
- New worker reclaims/recover it.
- If Codex turn cannot be resumed, mark interruption and continue with thread context or retry.
- Telegram receives recovery status.

## 30.10 Cancellation

User presses stop.

Expected:

- Job cancel requested
- Codex interrupted
- subprocesses terminated
- browser closed
- state cancelled
- partial artifacts sent

## 30.11 File analysis

User sends a log/archive/document and asks Codex to use it while debugging.

## 30.12 Image-based UI bug

User sends screenshot.

Expected:

- Vision summary
- Relevant image passed to Codex
- Code fix
- Browser verification

## 30.13 Create new project

User requests a new application from scratch.

Expected:

- Project path created
- Git initialized
- Codex implements
- Tests
- Browser verification
- Project registered

## 30.14 Long-running process

User asks to start a dev server.

Expected:

- Detached process registry
- Health monitoring
- Logs
- Later stop command

---

# 31. Error Handling and Recovery

Create typed exceptions:

```text
ConfigurationError
AjilUnavailableError
AjilFallbackError
StructuredOutputError
CodexStartupError
CodexProtocolError
CodexTurnError
CodexApprovalError
JobCancelledError
JobTimeoutError
ToolExecutionError
BrowserVerificationError
ArtifactError
MemoryError
```

Requirements:

- Never swallow exceptions without a log/event.
- Retry transient network failures.
- Do not retry deterministic validation failures indefinitely.
- Always finalize process/browser resources.
- Store failure artifact.
- Final Telegram failure message must be useful.
- Preserve traceback in local logs, not necessarily Telegram.
- Mark partially completed steps accurately.
- A failed Telegram send must not change a successful job to failed; queue a notification retry.

---

# 32. Automated Testing Strategy

The project is not complete without tests.

## 32.1 Unit tests

Cover:

- Config interpolation and validation
- Redaction
- State transitions
- Planner parsing and retries
- Ajil fallback detection
- Telegram formatting and chunking
- Job queue semantics
- Cancellation token
- Tool input validation
- Shell output/cancel
- Git parser
- Artifact hashing
- Memory ranking
- Codex RPC correlation
- Codex event normalization
- Automatic approvals
- Playwright result aggregation

## 32.2 Integration tests

Use real local dependencies where possible:

- PostgreSQL
- pgvector
- Redis
- Fake Ajil FastAPI server
- Fake Codex JSONL process
- Real shell subprocess
- Temporary Git repository
- Docker integration opt-in
- Playwright local demo app

## 32.3 Contract tests

### Ajil contract

- Health
- Chat
- Structured planning
- Embeddings
- STT request shape
- TTS request shape
- Fallback detection
- Root env contains required Ajil variables

### Codex contract

- Generate schema from installed version
- Initialization handshake
- Thread start
- Turn start
- Event parse
- Interrupt
- Approval request parse
- Version snapshot

Do not require live OpenAI usage in normal CI. Use a fake App Server protocol fixture. Provide opt-in live smoke test.

## 32.4 Telegram tests

- Fake updates
- Text
- Voice metadata
- Photo
- Document
- Callback
- Duplicate update handling
- Progress edit throttle
- Long report splitting
- Artifact sending

## 32.5 End-to-end tests

Create `examples/demo_webapp`.

E2E scenario:

1. Start fake Telegram update input.
2. Ask agent to modify demo UI text or feature.
3. Fake or live Codex adapter performs a deterministic change in CI.
4. Run tests.
5. Start demo app.
6. Run Playwright verification.
7. Produce screenshot/video/trace.
8. Generate report.
9. Verify job completed and artifacts exist.

Create separate live E2E profile using real Codex/Ajil/Telegram.

## 32.6 Quality gates

Required commands:

```bash
make format
make lint
make typecheck
make test
make test-integration
make test-e2e
make coverage
```

Target:

```text
Core module coverage >= 85%
No Ruff errors
No mypy errors in project code
All deterministic E2E tests pass
```

Do not chase coverage through meaningless tests.

---

# 33. Bootstrap and Developer Experience

Implement `scripts/bootstrap.sh`.

It must:

1. Detect OS.
2. Check Git.
3. Initialize submodules recursively.
4. Check/install `uv` instructions.
5. Create virtual environment.
6. Install Python dependencies.
7. Check Docker.
8. Start infrastructure optionally.
9. Check FFmpeg.
10. Check Codex.
11. Install Codex when requested.
12. Generate Codex protocol schemas.
13. Install Playwright browsers.
14. Create `.env` from `.env.example` if missing.
15. Validate root config.
16. Run migrations.
17. Run doctor checks.
18. Run smoke tests that do not require secrets.

Implement `scripts/doctor.sh` with a clear PASS/WARN/FAIL table.

Checks:

```text
Python
uv
Git
submodules
Docker daemon
Docker Compose
PostgreSQL
pgvector
Redis
Ajil health
Ajil auth
Codex binary
Codex version
Codex auth
Codex App Server handshake
Playwright Chromium
FFmpeg
Telegram token format
project paths
write permissions
```

Makefile targets:

```text
help
bootstrap
submodules
install
config-validate
infra-up
infra-down
infra-logs
migrate
dev
api
bot
worker
scheduler
doctor
ajil-smoke
codex-smoke
playwright-smoke
telegram-smoke
format
lint
typecheck
test
test-unit
test-integration
test-e2e
coverage
clean
reset
systemd-install
systemd-start
systemd-stop
systemd-status
```

---

# 34. `AGENTS.md` Requirements

Create an `AGENTS.md` in the root for future Codex/Claude sessions.

It must state:

- Project purpose
- Architecture summary
- One config file and one root env rule
- Ajil is a submodule
- Do not edit submodule without reproducible patch
- Full-access development mode is intentional
- Run tests after changes
- Update migrations with model changes
- Update docs and `.env.example` with config changes
- Keep `docs/IMPLEMENTATION_STATUS.md` current
- Never declare success without verification
- Do not modify unrelated user projects
- Use async APIs properly
- Keep type checks and lint clean

---

# 35. Documentation Requirements

Write:

## `README.md`

English quick start and feature overview.

## `README.fa.md`

Complete Persian setup and usage guide.

## `docs/ARCHITECTURE.md`

Components, diagrams, data flow, lifecycle.

## `docs/CONFIGURATION.md`

Every YAML key and env variable.

## `docs/DEVELOPMENT.md`

How to run and test.

## `docs/DEPLOYMENT.md`

Native/systemd and Compose infrastructure.

## `docs/TELEGRAM_COMMANDS.md`

All commands and examples in Persian.

## `docs/CODEX_PROTOCOL.md`

Version, handshake, event mapping, approval behavior, recovery.

## `docs/PLAYWRIGHT_VERIFICATION.md`

Modes, artifacts, CDP, video, traces.

## `docs/MEMORY.md`

Data model, summarization, embeddings, retrieval.

## `docs/TROUBLESHOOTING.md`

Common failures:

- Ajil unavailable
- Provider key failure
- Codex not authenticated
- App Server protocol mismatch
- Playwright browser missing
- Chrome CDP unavailable
- FFmpeg missing
- Telegram upload too large
- Redis/PostgreSQL unavailable
- Docker permission error
- Full-access settings apparently ignored
- Stale jobs

## `docs/FUTURE_SECURITY_HARDENING.md`

Future work only:

- Allowlist
- Fine-grained policy
- Approval UI
- Sandboxing
- Secret management
- Audit immutability
- Container isolation
- Command restrictions
- Network policy

## `docs/IMPLEMENTATION_STATUS.md`

Checklist updated after each phase.

## `docs/TEST_MATRIX.md`

Feature-to-test mapping.

## `docs/DECISIONS.md`

Architecture decision records or links.

## `docs/HANDOFF.md`

Exact current state and next steps.

---

# 36. Implementation Phases

Work phase by phase. After each phase:

- Run relevant tests.
- Fix failures.
- Update `IMPLEMENTATION_STATUS.md`.
- Create a focused Git commit if repository policy allows.
- Continue automatically.

## Phase 0: Discovery

- Inspect current repository.
- Inspect OS and installed tools.
- Inspect Ajil repository and current environment contract.
- Inspect current Codex CLI help and version.
- Generate current App Server schema.
- Record decisions.

## Phase 1: Repository foundation

- Root package
- Config loader
- `.env.example`
- Logging
- CLI
- Directory layout
- Submodule scripts
- Docker infrastructure
- Database models and migrations

## Phase 2: Ajil integration

- Typed client
- Health
- Chat
- Structured planning
- Embeddings
- STT/TTS wrappers
- Tests

## Phase 3: Telegram

- Polling
- Commands
- Input normalization
- Files
- Progress
- Fake update tests

## Phase 4: Jobs and orchestrator

- State machine
- Queue
- Worker
- Events
- Cancellation
- Recovery
- Project locks

## Phase 5: Codex

- Process supervisor
- JSONL RPC
- Handshake
- Threads
- Turns
- Events
- Auto approvals
- Persistence
- Smoke tests

## Phase 6: Tools

- Shell
- Filesystem
- Process
- Git
- Docker
- Systemd
- Network
- Project detection

## Phase 7: Memory

- Message persistence
- Summaries
- Embeddings
- Retrieval
- Outcome memory

## Phase 8: Playwright and artifacts

- Browser modes
- Verification actions/assertions
- Screenshot
- Video
- Trace
- Report
- Telegram sending
- Desktop recording fallback

## Phase 9: Voice

- FFmpeg
- STT
- TTS
- Telegram voice

## Phase 10: End-to-end workflows

- Demo app
- Deterministic E2E
- Live smoke scripts
- Recovery/cancel tests

## Phase 11: Deployment and docs

- Systemd
- Makefile
- Doctor
- Full documentation
- Final test pass

---

# 37. Git Commit Plan

Use commits similar to:

```text
chore: initialize project and submodules
feat(config): add unified root configuration and env contract
feat(infra): add postgres redis and ajil compose services
feat(db): add persistent domain models and migrations
feat(ajil): add typed unified gateway client
feat(telegram): add async bot and message normalization
feat(jobs): add persistent queue state machine and recovery
feat(codex): add app-server supervisor and jsonl rpc client
feat(codex): add thread turn event and approval handling
feat(tools): add host execution tool registry
feat(memory): add summaries embeddings and retrieval
feat(browser): add playwright verification and artifacts
feat(voice): add stt tts and ffmpeg pipeline
test(e2e): add complete demo workflow
docs: add setup architecture operations and handoff
```

Do not create empty commits.

Do not push unless `git.auto_push` or explicit project instruction enables it.

---

# 38. Completion Acceptance Criteria

The project is complete only when all applicable criteria pass.

## Repository

- [ ] Root Git repository valid
- [ ] Ajil added as submodule
- [ ] Nested submodules initialized
- [ ] No unexplained dirty submodule
- [ ] Root `.env.example` complete
- [ ] Single `config/agent.yaml`
- [ ] No required submodule `.env`

## Infrastructure

- [ ] PostgreSQL healthy
- [ ] pgvector enabled
- [ ] Redis healthy
- [ ] Ajil healthy
- [ ] Migrations run

## Application

- [ ] Config validates
- [ ] API liveness/readiness works
- [ ] Telegram bot starts
- [ ] Worker starts
- [ ] Job queue works
- [ ] Restart recovery works

## Ajil

- [ ] Chat works or fake contract passes
- [ ] Planner structured output validates
- [ ] Fallback detection works
- [ ] Embeddings work or fake contract passes
- [ ] STT/TTS wrappers tested

## Codex

- [ ] Binary detected
- [ ] Version captured
- [ ] Schema generated
- [ ] App Server handshake passes
- [ ] Thread starts
- [ ] Turn starts
- [ ] Events stream
- [ ] Diff/command output captured
- [ ] Interrupt works
- [ ] Automatic approvals work
- [ ] Thread mapping persists
- [ ] Restart behavior tested

## Tools

- [ ] Shell streaming
- [ ] Shell cancellation
- [ ] Filesystem
- [ ] Git
- [ ] Docker
- [ ] Process registry
- [ ] Project detection

## Memory

- [ ] Messages persist
- [ ] Summary created
- [ ] Project memory stored
- [ ] Semantic retrieval tested
- [ ] Outcome memory created

## Playwright

- [ ] Browser installs
- [ ] Demo app opens
- [ ] Assertions work
- [ ] Screenshot created
- [ ] Video created
- [ ] Trace created
- [ ] Console/page/network errors collected
- [ ] Artifacts registered

## Telegram

- [ ] Text path
- [ ] Command path
- [ ] Voice path
- [ ] File path
- [ ] Progress update
- [ ] Stop button
- [ ] Final report
- [ ] Artifact upload or mock validation

## Quality

- [ ] Ruff clean
- [ ] mypy clean
- [ ] Unit tests pass
- [ ] Integration tests pass
- [ ] E2E tests pass
- [ ] Coverage target met
- [ ] Doctor has no unexplained failures
- [ ] Documentation complete

Do not mark a checkbox complete without evidence.

---

# 39. Required Final Verification Scenario

Run this final scenario locally, using real integrations where credentials exist and fakes where they do not.

1. Start PostgreSQL, Redis, and Ajil.
2. Start agent API, Telegram adapter, and worker.
3. Verify `/ready`.
4. Register `examples/demo_webapp` as a project.
5. Create a job equivalent to:

```text
Change the demo page heading, run tests, start the app, open it in Playwright,
verify the new heading is visible, take a screenshot, record video and trace,
then generate the final Telegram report.
```

6. Ensure the job passes through:
   - planning
   - queue
   - Codex or deterministic E2E Codex fake
   - code change
   - tests
   - app startup
   - Playwright
   - artifacts
   - report
7. Cancel a second running job and verify cleanup.
8. Restart a worker during a third job and verify recovery.
9. Run all quality gates.
10. Save final output under:

```text
data/artifacts/final-acceptance/
```

Create:

```text
final-acceptance-report.md
test-results.txt
coverage.xml
doctor.txt
screenshots/
videos/
traces/
```

---

# 40. Autonomous Work Rules

Follow these rules throughout implementation:

1. Inspect before editing.
2. Prefer working code over speculative abstraction.
3. Keep interfaces typed.
4. Keep the event loop non-blocking.
5. Put blocking work in subprocesses or threads.
6. Add timeouts to network and subprocess operations.
7. Use `try/finally` for process/browser cleanup.
8. Test failure paths.
9. Never claim a live integration passed unless it actually ran.
10. Use mocks only where external credentials are absent.
11. Do not stop after one failed test; diagnose and fix.
12. Do not delete unrelated files.
13. Do not rewrite Git history.
14. Do not commit secrets.
15. Update docs as behavior changes.
16. Update `.env.example` for every new env variable.
17. Update config schema for every new setting.
18. Update migrations for every persistent model change.
19. Keep submodule handling reproducible.
20. Maintain `docs/IMPLEMENTATION_STATUS.md`.
21. Continue until acceptance criteria pass or an external dependency is objectively impossible.
22. When externally blocked, complete everything else and provide exact reproduction steps.

---

# 41. Initial Commands You Should Execute

Begin by running and recording the results of:

```bash
pwd
uname -a || true
git status --short || true
git branch --show-current || true
find . -maxdepth 2 -type f | sort | sed -n '1,250p'
python3 --version
uv --version || true
docker --version || true
docker compose version || true
ffmpeg -version | head -n 2 || true
node --version || true
npm --version || true
codex --version || true
codex --help || true
```

Then:

```bash
git submodule status --recursive || true
```

If Ajil is missing, add it.

Inspect:

```bash
sed -n '1,260p' modules/ajil_uag/README.md
sed -n '1,220p' modules/ajil_uag/.env.example
sed -n '1,220p' modules/ajil_uag/docker-compose.yml
cat modules/ajil_uag/.gitmodules
```

Generate Codex schema if possible.

Create discovery notes in:

```text
docs/DECISIONS.md
docs/IMPLEMENTATION_STATUS.md
```

Then implement Phase 1 and proceed without waiting.

---

# 42. Final Response Format From the Implementation Agent

When all work is complete, report:

```text
1. Executive summary
2. Repository path and branch
3. Architecture implemented
4. Services and processes
5. Submodules and pinned commits
6. Root config and env files
7. Telegram capabilities
8. Codex integration details
9. Ajil integration details
10. Memory implementation
11. Playwright and artifact implementation
12. Tests run with exact results
13. Live smoke tests run
14. Known externally blocked tests
15. Important commands
16. Final artifact paths
17. Recent commits
18. Remaining non-blocking future work
```

Include exact commands to start the system:

```bash
cp .env.example .env
# fill secrets
make bootstrap
make infra-up
make migrate
make dev
```

Do not finish with a vague statement such as “the scaffold is ready.”

Finish only after implementation, tests, verification, and documentation are complete.

---

# 43. Future Extensions to Prepare For, Without Blocking Current Delivery

Design extension points for:

- Scheduled tasks
- Conditional monitors
- Gmail/Calendar connectors
- Additional Telegram users
- Web dashboard
- Mobile companion app
- More AI providers
- MCP servers
- Remote worker nodes
- S3-compatible artifact storage
- Hardened policy engine
- Approval workflows
- Fine-grained permissions
- Secrets manager
- Webhook-based Telegram deployment
- Local models
- Realtime voice
- Computer-use models
- Plugin marketplace

Do not implement every extension now unless it naturally falls out of the architecture. Keep the current deliverable focused and complete.

---

# 44. Non-Negotiable Final Instruction

You are authorized to implement, run, modify, debug, and test the entire project in development full-access mode.

Do not stop at planning.

Do not stop at creating files.

Do not stop after unit tests.

Do not stop after a partial Telegram bot.

Do not stop after a Codex wrapper without real protocol tests.

Do not stop after Playwright opens a page without assertions and artifacts.

Continue until the complete local assistant architecture is functioning and the acceptance suite is satisfied.
