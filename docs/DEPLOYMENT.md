# Platform deployment

This is the complete Bot/Codex platform deployment. Voice-only details are in
[Voice deployment](deployment.md), and the network relay is in
[UDP media overlay](media-overlay.md).

## Prerequisites

- Linux, Docker Engine, and Compose v2;
- Git with recursive submodule support;
- Python 3.12 for supported native development;
- FFmpeg/ffprobe;
- authenticated Codex CLI/App Server state;
- Telegram Bot token;
- primary Telethon API ID/hash/string session;
- approved numeric/user allowlists;
- Ajil provider credentials;
- network/proxy/media relay access required by the host;
- owner-controlled workspace root, normally `/home/mhr/Code`.

## Checkout and configuration

```bash
git clone --recurse-submodules REPOSITORY_URL
cd OCTOPUS
git submodule update --init --recursive
cp .env.example .env
chmod 600 .env
```

Fill `.env` without printing values. At minimum configure the Bot token, PostgreSQL password/URL,
Codex mounts, workspace paths, Ajil providers, primary Telethon credentials, Telethon numeric
peers/usernames, and required proxies. Put the enforced Bot numeric user/chat allowlists in
`config/agent.yaml`; empty lists accept every Bot user/chat and are only appropriate for a
controlled bootstrap. Keep all other non-secret policy there as well.

Validate before startup:

```bash
docker compose --profile agent config --quiet
PYTHONPATH=src python -m telegram_codex_agent.cli config validate
git submodule status --recursive
```

## Images and mounts

`Dockerfile.agent` builds the Bot/API/worker platform image. `Dockerfile` builds the voice image
with FFmpeg and cached dependency layers. `Dockerfile.media-ssh-tunnel` builds the relay sidecar.

Important mounts:

| Host value | Container path | Access |
| --- | --- | --- |
| repository | `/workspace/octopus` | read/write development |
| `WORKSPACE_ROOT_HOST` | `/workspace/code` | read/write Codex workspaces |
| `CODEX_HOME_HOST` | `/codex-home` | Codex authentication/config |
| `CODEX_HOST_RUNTIME` | `/host-codex` | read-only local Codex runtime |
| `./runtime` | `/runtime` | voice audit/temp/media library |
| media SSH key/known_hosts | `/run/ssh-*` | read-only |

Do not mount a broader host root than needed.

## Start

```bash
docker compose --profile agent build
docker compose --profile agent up -d
docker compose --profile agent ps
```

Startup dependency order:

1. PostgreSQL and Redis become healthy.
2. Ajil becomes healthy.
3. `agent-migrate` applies Alembic.
4. API, Bot, and worker start.
5. Voice service and media sidecars start under the same profile.

Persistent services use `restart: unless-stopped`. Migration is one-shot.

## Health acceptance

```bash
curl --noproxy '*' -fsS http://127.0.0.1:18090/health
curl --noproxy '*' -fsS http://127.0.0.1:18090/ready
curl --noproxy '*' -fsS http://127.0.0.1:8080/health
docker compose --profile agent logs --tail=200 \
  agent-api agent-bot agent-worker voice-agent
```

`/ready` must report Ajil, database, and Redis healthy. Voice logs must show its Telethon
connection and inbound service ready. Redis completion calls should show no unexplained pending
or lag:

```bash
docker compose exec -T redis redis-cli -n 1 \
  XINFO GROUPS telegram_codex_agent.completion_calls
```

Run `make doctor`, `make ajil-smoke`, and `make codex-smoke` before accepting mutation work.

## First Telegram acceptance

1. Send `/start` to the Bot.
2. Select `/projects` → `octopus` or another approved workspace.
3. Use `/new`.
4. Run a read-only request and observe commentary.
5. Inspect `/status`, `/usage`, `/history`, and `/logs JOB_ID`.
6. Confirm model/reasoning/Fast/permissions settings apply to a new test job.
7. Enable `/completion_call on` only for an allowlisted consenting test identity.

## Updating application code

```bash
git fetch --all --prune
git pull --ff-only
git submodule update --init --recursive
docker compose --profile agent build agent-api agent-worker agent-bot voice-agent
docker compose --profile agent up -d
```

Compose reruns migrations through `agent-migrate`. For a voice-only source change, first confirm no
active call and completion `XPENDING=0`, then rebuild/recreate only `voice-agent`:

```bash
docker compose --profile agent build voice-agent
docker compose --profile agent up -d --no-deps --force-recreate voice-agent
```

Never use `--remove-orphans` casually; this repository can intentionally share legacy-named
containers.

## Native/systemd development

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e '.[dev]'
make infra-up
make migrate
make doctor
make dev
```

User services:

```bash
./scripts/systemd_install.sh
make systemd-start
make systemd-status
```

Do not run native Bot/worker/voice processes concurrently with Compose equivalents using the same
queues, port, Bot token, or Telethon session unless explicitly testing multi-worker behavior.

## Backups and rollback

Before a risky upgrade:

- record the Git/submodule commits;
- back up the PostgreSQL volume/database;
- preserve Redis AOF when queued work must survive;
- protect Codex home and root `.env` separately;
- back up voice SQLite only when transcript policy permits;
- never include temporary audio or credentials in Git.

Application rollback is `git switch` to the known commit, recursive submodule update, rebuild, and
Compose up. Database rollback should use a tested forward-fix or explicit migration procedure;
do not blindly downgrade a production database. Inspect terminal jobs before replaying queues.

## Stop

Graceful platform stop:

```bash
docker compose --profile agent stop \
  agent-bot agent-worker agent-api voice-agent \
  voice-media-tunnel voice-media-ssh-tunnel
```

Full infrastructure shutdown without deleting volumes:

```bash
docker compose --profile agent down
```

Do not add `-v` unless the user explicitly intends to destroy PostgreSQL/Redis data.

## Optional profiles

- `local_telegram_bot_api`: optional local Bot API endpoint; polling remains default.
- `prometheus`: local Prometheus on port 9090.
- `grafana`: local Grafana on port 3000.

These profiles are not required for core readiness and must be configured/hardened before external
exposure.

## Production cautions

This deployment is designed for one trusted owner. Keep ports localhost-bound, use encrypted
storage/backup, protect mounted Codex/Telegram credentials, rotate real secrets, monitor audit
events, define retention, and complete the security-hardening backlog before multi-user access.
