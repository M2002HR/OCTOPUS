# Architecture decisions

## ADR-001: Unified product and legacy voice service

The project is now `telegram-codex-agent`. The existing `voice_agent` package remains a
supported Telethon/PyTgCalls call subsystem because it has already been exercised with real
two-account calls. The new aiogram bot is the user-facing Telegram Bot API adapter; it does not
replace private-account call handling, which Bot API cannot provide.

## ADR-002: Ajil submodule location

Ajil Unified AI Gateway is pinned as the recursive submodule `modules/ajil_uag`. Its nested
provider modules must be initialized recursively. The root `.env` is the only environment file;
the submodule is launched with that file and no submodule `.env` is required.

## ADR-003: Native development control plane

The API, bot, and worker are native processes in development so they can operate on user-owned
projects, Codex authentication, Docker, and an optional local browser. PostgreSQL, Redis, and
Ajil are Compose infrastructure services. The supported runtime uses Python 3.12 even when the
host's convenience Python is older.

## ADR-004: Language boundary

The new Bot API product is Persian-first as specified by the master implementation contract.
The pre-existing Telethon call service retains its explicitly configured English-only behaviour
until its media conversation policy is migrated deliberately; this avoids silently changing a
tested call workflow. New voice-note processing is configured by `config/agent.yaml`.

## Discovery record (2026-07-24)

- Host: Linux, Docker/Compose and FFmpeg available; host Python is 3.10, so supported execution
  is Docker/Python 3.12.
- Codex CLI: `0.142.5`, authenticated through ChatGPT. App-server protocol schemas were generated
  locally from this installed version.
- Ajil submodule commit: `1e281e70e409d40e79d520f78623eeaf54e1350c`, with nested modules initialized.
- Existing voice call, STT/TTS, private message, image analysis, and audit capabilities remain
  in `src/voice_agent` and are integrated as a compatibility subsystem rather than discarded.
