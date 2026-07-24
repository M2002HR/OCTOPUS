# Operations runbook

Use the isolated platform stack for the new Telegram Codex agent:

```bash
docker compose --profile agent up -d
docker compose --profile agent ps
curl --noproxy '*' http://127.0.0.1:18090/ready
```

The first startup runs migrations. `agent-api`, `agent-worker`, and `agent-bot`
use `restart: unless-stopped`; PostgreSQL, Redis, Ajil and the legacy voice
services remain separate services.

In a fully portable deployment build `Dockerfile.agent` first. This host also
supports the checked-in Compose fallback: `AGENT_IMAGE` may point at the
project's prebuilt Python image while `CODEX_HOST_RUNTIME` mounts the local
Codex runtime read-only. Both paths require an explicit `CODEX_HOME_HOST`.

For a host-native deployment, install the user units with
`./scripts/systemd_install.sh`, then use `make systemd-start` and
`make systemd-status`.

Diagnose a job without exposing secrets:

```bash
curl --noproxy '*' http://127.0.0.1:18090/jobs/JOB_ID
curl --noproxy '*' http://127.0.0.1:18090/jobs/JOB_ID/events
docker compose --profile agent logs --tail=200 agent-worker
```

Run non-mutating dependency checks with `make ajil-smoke` and
`make codex-smoke`. The Codex smoke turn neither reads nor changes project
files.
