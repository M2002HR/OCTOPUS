#!/usr/bin/env bash
set -u

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
status=0
check() {
  local label="$1"; shift
  if "$@" >/dev/null 2>&1; then printf 'PASS  %s\n' "$label"; else printf 'WARN  %s\n' "$label"; status=1; fi
}
check "Python" python3 --version
check "Git" git --version
check "Docker daemon" docker info
check "Docker Compose" docker compose version
check "FFmpeg" ffmpeg -version
check "Codex binary" codex --version
check "Codex auth" codex login status
check "Ajil submodule" test -f modules/ajil_uag/README.md
check "Root configuration" env PYTHONPATH=src python3 -m telegram_codex_agent.cli config validate
check "Compose configuration" docker compose config --quiet
exit "$status"
