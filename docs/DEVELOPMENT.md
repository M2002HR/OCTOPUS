# Development

Use Python 3.12 for supported execution. The host's Python can be used for lightweight config
checks but Docker is the reproducible local environment.

```bash
cp .env.example .env
# add only the secrets you need
make bootstrap
make infra-up
make migrate
make doctor
make dev
```

Run deterministic checks with `make lint`, `make typecheck`, and `make test`. Live Ajil, Codex,
Telegram, and browser tests are opt-in through the `RUN_LIVE_*` environment variables.
