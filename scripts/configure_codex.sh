#!/usr/bin/env bash
set -euo pipefail

codex_home="${CODEX_HOME:-$HOME/.codex}"
config_file="$codex_home/config.toml"
mkdir -p "$codex_home"
touch "$config_file"

python3 - "$config_file" <<'PY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
for key, value in (("approval_policy", '"never"'), ("sandbox_mode", '"danger-full-access"')):
    pattern = rf"(?m)^{key}\s*=.*$"
    text = re.sub(pattern, f"{key} = {value}", text) if re.search(pattern, text) else f"{key} = {value}\n" + text
section = "[sandbox_workspace_write]\nnetwork_access = true\n"
if "[sandbox_workspace_write]" not in text:
    text = text.rstrip() + "\n\n" + section
elif not re.search(r"(?ms)^\[sandbox_workspace_write\].*?^network_access\s*=", text):
    text = text.replace("[sandbox_workspace_write]\n", section)
path.write_text(text, encoding="utf-8")
PY

echo "Configured Codex full-access development policy in $config_file"
