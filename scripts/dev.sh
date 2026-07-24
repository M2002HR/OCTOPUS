#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
PYTHONPATH=src python3 -m telegram_codex_agent.cli config validate
docker compose up -d --wait postgres redis ajil_gateway
PYTHONPATH=src alembic upgrade head
PYTHONPATH=src python3 -m telegram_codex_agent.cli codex status
exec PYTHONPATH=src python3 -m telegram_codex_agent.cli api
