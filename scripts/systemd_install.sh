#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
target="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p "$target"
for template in "$root"/systemd/*.service.template; do
  unit="$(basename "$template" .template)"
  sed "s|@ROOT@|$root|g" "$template" >"$target/$unit"
done
systemctl --user daemon-reload
systemctl --user enable telegram-codex-agent-api telegram-codex-agent-bot telegram-codex-agent-worker
echo "Installed user units in $target. Start them with: make systemd-start"
