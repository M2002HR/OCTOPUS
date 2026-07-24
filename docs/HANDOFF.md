# Maintainer handoff

This document is the operational handoff checklist for the current OCTOPUS implementation.

## Product boundary

- The Telegram Bot API account is the owner's normal control plane.
- Ajil performs direct conversation, STT/provider routing, orchestration assistance, and terminal
  completion-call wording.
- Codex App Server is the primary coding, inspection, test, Git, Docker, and browser execution
  engine inside an explicitly selected workspace.
- The primary Telethon user session exclusively owns private calls and compatibility private
  messages.
- The second Telethon session exists for approved end-to-end testing; it is not a production
  worker or substitute for the primary session.

## Non-negotiable invariants

1. Non-secret policy lives in `config/agent.yaml`.
2. Secrets and machine-specific credentials live only in the root `.env`.
3. `modules/ajil_uag` is a recursive submodule and must not be edited in-place from the root.
4. PostgreSQL is the control-plane source of truth; Redis is delivery/live-event infrastructure.
5. Only one process owns `TELEGRAM_STRING_SESSION`.
6. Telegram IDs are authorized numerically; usernames are resolved to IDs at startup.
7. Telegram input never directly becomes a filesystem root or unrestricted artifact path.
8. Async network/subprocess/browser work is bounded and cleaned up.
9. Logs/events exclude credentials, raw reasoning, call keys, and content unless the protected
   persistence policy explicitly allows transcripts.
10. No live integration is declared successful without recorded evidence.

## Current supported deployment

Python 3.12 and Docker Compose v2 are the reproducible runtime. `docker compose --profile agent
up -d` runs PostgreSQL, Redis, Ajil, migrations, API, Bot, worker, voice service, and voice media
sidecars. The API binds to localhost. Agent Bot/worker use host networking so they can reach the
host Codex runtime, proxy, browser, and workspaces.

The host must supply:

- an authenticated Codex home/runtime mount;
- a Telegram Bot token;
- primary Telethon API/session credentials;
- allowlisted Telegram IDs/usernames;
- Ajil provider credentials;
- proxy/media-relay values required by the target network;
- writable workspace/runtime paths.

## Before modifying

```bash
git status -sb
git submodule status --recursive
docker compose --profile agent ps
curl --noproxy '*' http://127.0.0.1:18090/ready
curl --noproxy '*' http://127.0.0.1:8080/health
```

Inspect `AGENTS.md`, the relevant architecture decision, configuration schema, migration history,
and existing tests before changing a subsystem.

## Configuration-change checklist

- update `config/agent.yaml` for non-secret policy;
- update `.env.example` for secret/machine environment;
- update Pydantic/dataclass validation;
- update Compose/systemd mappings where applicable;
- update `docs/configuration.md` and the subsystem document;
- update implementation status;
- add positive, default, and invalid-value tests;
- avoid introducing a second configuration file.

Persistent model changes additionally require a new Alembic migration; never rewrite a migration
already applied outside a disposable environment.

## Release checklist

1. Confirm no `.env`, session, token, key, runtime media, or user project file is staged.
2. Run Ruff, compileall, mypy, pytest, Compose config, and `git diff --check`.
3. Run Ajil/Codex smoke tests when their integration changed.
4. Run the second-session Telegram scenario when Bot/Telethon behavior changed.
5. Build/recreate only affected services first; avoid interrupting an active user call.
6. Confirm `/ready`, Ajil `/health`, Compose state, Redis pending/lag, and restart counts.
7. Update `IMPLEMENTATION_STATUS.md` and `TEST_MATRIX.md` with evidence.
8. Commit using the existing Conventional Commit style.
9. Push a review branch/PR unless the owner explicitly requests direct default-branch publication.

## Known constraints

- Development full access is intentional and unsuitable for untrusted/multi-user exposure.
- Telegram Bot API cannot place private user-account calls; Telethon is required.
- Voice media may require the UDP-over-SSH overlay even when MTProto signaling works.
- Completion-call delivery is at-least-once at a process-crash boundary.
- The scheduler command is reserved but currently disabled.
- Browser execution relies on each selected workspace's available tooling.
- Memory retrieval is currently scoped/lexical; schema support does not imply semantic-vector
  production retrieval.
- Artifact retention configuration exists, but unattended deletion requires an external job while
  the scheduler remains disabled.
- Voice transcript storage is not encrypted by the application.

## Recovery priorities

1. Preserve PostgreSQL and Redis volumes.
2. Restore Ajil, then migrations/API, worker/Bot, then the Telethon voice service.
3. Ensure only one primary Telethon owner.
4. Inspect PostgreSQL terminal state before replaying a Redis job.
5. Let consumer-group recovery claim stale entries; do not manually duplicate Stream messages.
6. Verify completion-call `XPENDING` and lag return to zero.
7. Run a read-only Codex smoke task before allowing workspace mutation.

## Documentation ownership

The root README is an entry point. `docs/ARCHITECTURE.md`, `DECISIONS.md`,
`configuration.md`, `DEPLOYMENT.md`, `RUNBOOK.md`, and `TEST_MATRIX.md` are release-critical.
Subsystem changes must update their focused documents as well. The historical master prompt is not
an excuse to leave operating documentation stale.
