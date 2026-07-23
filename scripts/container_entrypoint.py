"""Prepare the bind-mounted runtime directory, then run the agent without root privileges."""

from __future__ import annotations

import os
import sys
from pathlib import Path

AGENT_UID = 10001
AGENT_GID = 10001


def main() -> None:
    runtime = Path(os.environ.get("RUNTIME_DIR", "/runtime"))
    runtime.mkdir(parents=True, exist_ok=True)
    os.chown(runtime, AGENT_UID, AGENT_GID)
    # A host bind mount can contain previous root-owned turn artifacts.
    for path in runtime.rglob("*"):
        os.chown(path, AGENT_UID, AGENT_GID, follow_symlinks=False)
    os.setgid(AGENT_GID)
    os.setuid(AGENT_UID)
    os.execvp("telegram-voice-agent", ["telegram-voice-agent", *sys.argv[1:]])


if __name__ == "__main__":
    main()
