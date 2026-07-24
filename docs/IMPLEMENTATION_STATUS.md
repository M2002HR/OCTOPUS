# Implementation status

Evidence is recorded here rather than inferred from design documents.

## Phase 0 — discovery

- [x] Repository, host tools, Docker, FFmpeg, Codex, and current service topology inspected.
- [x] Ajil recursive submodule inspected and relocated to `modules/ajil_uag`.
- [x] Current Codex app-server JSON and TypeScript schemas generated locally.
- [x] Existing Telethon calling and messaging subsystem catalogued for integration.

## Phase 1 — repository foundation

- [x] Unified package/configuration/CLI
- [x] Compose PostgreSQL, Redis, and Ajil topology
- [x] Persistent domain models, repository primitives, and initial Alembic migration
- [x] Root environment contract, Ajil variable coverage, Makefile, bootstrap, doctor, and Codex configuration helper

## Later phases

- [x] Ajil typed client with structured-output/fallback handling
- [x] Telegram Bot API adapter and normalization primitives
- [x] Job state machine, Redis Streams delivery, PostgreSQL leases, event persistence, and live cancellation
- [x] Codex App Server JSONL integration: initialize, thread/turn lifecycle, event capture, safe approval bridge, interrupt, and persistence
- [x] Explicit project registry and persistent selected-project context
- [x] Persistent lexical-scoped memory, user commands, retrieval metadata, and outcome recording
- [x] Live E2E: Ajil direct chat, Codex read-only project task, and cancellation during a live Codex turn
- [x] Compose API/worker/bot services, migrations, health checks, restart policy, runbook, and systemd templates
- [x] Codex CLI-style Telegram UX: persistent/inline keyboards, workspace discovery under `~/Code`, `/new`, real `thread/resume`, `/status`, `/permissions`, model/reasoning controls, and scoped job logs
- [x] Live level-controlled Codex lifecycle/activity streaming and verified Telegram screenshot/artifact delivery
- [x] Redis pending-message recovery coordinated with PostgreSQL leases, plus Codex-driven Chrome Lab/browser verification and artifact handoff
