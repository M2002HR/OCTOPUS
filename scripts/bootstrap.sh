#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
git submodule update --init --recursive
if [[ ! -f .env ]]; then cp .env.example .env; echo 'Created .env; fill its secrets before live services.'; fi
python3 --version
docker --version
docker compose version
ffmpeg -version | head -n 1
codex --version || true
python3 -m pip install -e '.[dev]'
PYTHONPATH=src python3 -m telegram_codex_agent.cli config validate
./scripts/doctor.sh || true
