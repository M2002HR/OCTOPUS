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
- [x] Job state machine and Redis/in-memory queue primitives
- [ ] Persistent worker, recovery, and full orchestration
- [ ] Codex App Server integration
- [ ] Host tools and project registry
- [ ] Memory, browser, artifacts, and voice notes
- [ ] Deterministic E2E and operational documentation
