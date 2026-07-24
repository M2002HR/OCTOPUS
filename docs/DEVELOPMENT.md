# Development guide

## Environment

Use Python 3.12 for reproducible execution. The package declares Python 3.11 minimum, but the
deployed images and validated Telegram/NTgCalls dependency set use 3.12.

```bash
git submodule update --init --recursive
python3.12 -m venv .venv
.venv/bin/pip install -e '.[dev]'
cp .env.example .env
chmod 600 .env
```

Alternatively, `make bootstrap` runs the checked-in bootstrap script. `scripts/bootstrap_env.py`
refuses to overwrite an existing `.env` and never prints secret values.

## Configuration discipline

- checked-in policy: `config/agent.yaml`;
- secret/machine values: root `.env`;
- deployment projection: `docker-compose.yml` and systemd templates;
- runtime user preferences: PostgreSQL;
- no submodule/project-local copy of root secrets.

When adding configuration, update schema/dataclass validation, YAML, `.env.example`, Compose,
documentation, and tests in one change.

## Common workflows

```bash
make config-validate
make infra-up
make migrate
make doctor
make dev
```

Individual processes:

```bash
make api
make bot
make worker
```

The scheduler target is reserved and currently exits as disabled. Do not document it as an active
service.

Compose platform:

```bash
make agent-up
make agent-status
make agent-logs
```

Do not run native and Compose copies of Bot/worker/voice simultaneously unless the test explicitly
requires it.

## Database changes

SQLAlchemy models live in `src/telegram_codex_agent/db/models.py`; Alembic owns PostgreSQL schema.

```bash
PYTHONPATH=src alembic revision --autogenerate -m "describe change"
PYTHONPATH=src alembic upgrade head
```

Review generated SQL, defaults, indexes, ownership scoping, and upgrade behavior. Do not rewrite an
applied migration. SQLite voice storage has its own schema initialization and backward-compatible
evolution in `src/voice_agent/storage.py`.

## Codex protocol development

Generated protocol material lives under `generated/codex`; it reflects the installed Codex
runtime. Update it only deliberately after checking CLI/App Server version and reviewing protocol
changes. The integration client is in `src/telegram_codex_agent/integrations/codex.py`.

Every App Server change must preserve:

- bounded startup/RPC/turn/shutdown;
- concurrent stdout/stderr draining;
- request ID correlation;
- public-versus-private event filtering;
- deterministic approval responses;
- cancellation via `turn/interrupt`;
- subprocess termination/await in `finally`;
- thread/turn persistence and recovery.

## Ajil development

Root integration uses `src/telegram_codex_agent/integrations/ajil.py` and
`src/voice_agent/adapters/uag.py`. `modules/ajil_uag` is a recursive submodule: do not edit it
directly. Implement/review/test an upstream patch, commit there, update the root pointer, and
initialize nested modules.

## Telegram and voice development

Use Bot unit tests for most work. Live tests require explicit flags and approved IDs. The primary
Telethon session belongs exclusively to `voice-agent`; the second session drives real tests.
Never generate/replace a production string session while the voice container is using it.

For call code, test state transitions, busy behavior, hangup, cancellation, audio cleanup, and
restart recovery. For Bot code, test both command text and callback normalization.

## Quality gates

```bash
RUFF_CACHE_DIR=/tmp/octopus-ruff-cache ruff check src tests tests_agent scripts
PYTHONPYCACHEPREFIX=/tmp/octopus-pycache \
  python -m compileall -q src scripts tests tests_agent
python -m mypy src
python -m pytest -q
docker compose --profile agent config --quiet
git diff --check
```

`make lint`, `make typecheck`, and `make test` are the standard shortcuts. Use a writable temporary
cache when repository cache directories were created by a container. Do not describe a mypy
internal crash as a passing typecheck.

Live layers:

```bash
make ajil-smoke
make codex-smoke
RUN_INTEGRATION_TESTS=true make test-integration
RUN_E2E_TESTS=true make test-e2e
```

See [Testing](testing.md) and [Test matrix](TEST_MATRIX.md).

## Style and implementation rules

- keep async paths non-blocking;
- add timeouts to network/subprocess/browser work;
- cleanup subprocesses, browser contexts, calls, and temporary media;
- use structured safe events instead of free-form secret-bearing logs;
- preserve unrelated user work in dirty trees;
- use explicit workspace/path containment;
- keep public Telegram commentary concise and never forward private reasoning;
- update implementation status and architecture decisions for material changes.

## Commit and release

Use the repository's Conventional Commit style, stage only intended files, and run checks before
push. Update submodule pointers in their own logical commit. Use a review branch/PR unless the
owner explicitly authorizes a direct default-branch push. The release checklist is in
[Handoff](HANDOFF.md).
