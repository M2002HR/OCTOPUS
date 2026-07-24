# Deployment

Compose runs infrastructure only: PostgreSQL with pgvector, Redis, and Ajil. API, bot, worker,
and scheduler run natively in development so they can use local projects, Docker, Codex auth, and
an existing browser. The legacy voice profile remains available with:

```bash
docker compose --profile agent up -d voice-agent voice-media-ssh-tunnel voice-media-tunnel
```

All network ports bind to localhost by default. Optional Compose profiles are
`local_telegram_bot_api`, `prometheus`, and `grafana`.
