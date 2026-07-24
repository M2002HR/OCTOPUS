# Documentation index

This directory is the canonical English documentation for OCTOPUS, also packaged as
`telegram-codex-agent`. Documentation describes the checked-in implementation, not only the
original implementation prompt. When implementation and prose disagree, treat code and
`config/agent.yaml` as authoritative and update the relevant document in the same change.

## Start here

| Document | Scope |
| --- | --- |
| [Root README](../README.md) | Product overview, quick start, first Telegram workflow, and repository map |
| [System architecture](ARCHITECTURE.md) | End-to-end Bot, job, Codex, Ajil, persistence, and Telethon boundaries |
| [Architecture decisions](DECISIONS.md) | Durable design choices and their trade-offs |
| [Configuration](configuration.md) | Policy precedence, root `.env` contract, defaults, and secret handling |
| [Environment inventory](ENVIRONMENT.md) | Every root `.env.example` variable grouped by ownership and behavior |
| [Platform deployment](DEPLOYMENT.md) | Complete Compose/native deployment and update procedure |
| [Operations runbook](RUNBOOK.md) | Startup, health checks, job inspection, recovery, backup, and shutdown |
| [Local administration API](API.md) | Health, readiness, redacted config, projects, jobs, events, and cancellation |
| [Telegram commands](TELEGRAM_COMMANDS.md) | Complete Bot UI, command, session, settings, and attachment reference |
| [Codex protocol](CODEX_PROTOCOL.md) | App Server lifecycle, thread continuity, approvals, progress, usage, and cancellation |

## Subsystems and data

| Document | Scope |
| --- | --- |
| [Voice architecture](architecture.md) | Telethon/PyTgCalls call, STT, TTS, VAD, persistence, and concurrency internals |
| [Voice deployment](deployment.md) | Voice-only prerequisites, persistent service, and Ajil updates |
| [Completion calls](completion-calls.md) | End-of-Codex-call policy, Ajil wording, Redis delivery, retries, privacy, and testing |
| [Private messaging](messaging.md) | Telethon text, voice note, image, reply context, and approved media behavior |
| [Voice turn detection](voice-turn-detection.md) | VAD algorithm and tuning |
| [UDP media overlay](media-overlay.md) | Telegram media path through GOST, SSH, and the required proxy |
| [Memory](MEMORY.md) | Conversation, preference, project, outcome, and Codex continuity data |
| [Browser verification](PLAYWRIGHT_VERIFICATION.md) | Browser commands, Codex ownership, screenshots, and artifact delivery |

## Development, verification, and support

| Document | Scope |
| --- | --- |
| [Development](DEVELOPMENT.md) | Environment, migrations, local services, quality gates, and contribution rules |
| [Testing](testing.md) | Automated, integration, live Telegram, voice, and completion-call procedures |
| [Test matrix](TEST_MATRIX.md) | Capability-to-test/evidence map and claims policy |
| [Operations and audit](operations.md) | Event streams, log levels, privacy boundaries, retention, and incidents |
| [Troubleshooting](troubleshooting.md) | Platform, Codex, Ajil, Bot, Redis, completion-call, and VoIP failures |
| [Implementation status](IMPLEMENTATION_STATUS.md) | Implemented, partial, and deliberately unavailable capabilities |
| [Security hardening](FUTURE_SECURITY_HARDENING.md) | Required work before multi-user or untrusted exposure |
| [Handoff](HANDOFF.md) | Maintainer checklist, invariants, known constraints, and release handoff |

`COMPLETE_CODEX_IMPLEMENTATION_PROMPT.md` is the historical product contract. It is useful for
traceability, but the documents above are the operating reference.

## Documentation invariants

- Non-secret policy belongs only in `config/agent.yaml`; secrets and machine-specific values
  belong only in the root `.env`.
- Do not copy real tokens, API keys, Telegram sessions, proxy credentials, user IDs, or relay
  credentials into documentation.
- `modules/ajil_uag` is a pinned recursive submodule. Document root integration here and upstream
  Ajil internals in that project.
- The Bot API control plane and the primary Telethon account are different transports. The Bot is
  the normal user interface; Telethon supplies private calls and the compatibility message service.
- English is the configured default for the control plane and the enforced language of the
  Telethon voice subsystem.
- Never mark an external integration verified without preserving content-safe evidence.
