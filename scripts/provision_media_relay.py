#!/usr/bin/env python3
"""Provision the private remote GOST relay and persist its root-.env settings.

The relay is bound to loopback on the remote server.  It is reachable solely
through an SSH local forward whose SSH transport uses the project's HTTP proxy.
Secrets are generated locally, written with mode 0600, and never printed.
"""

from __future__ import annotations

import argparse
import os
import secrets
import shlex
import subprocess
from pathlib import Path

from dotenv import dotenv_values

DEFAULTS = {
    "VOICE_AGENT_MEDIA_TUNNEL_ENABLED": "true",
    "VOICE_AGENT_MEDIA_TUNNEL_LISTEN_PORT": "12345",
    "VOICE_AGENT_MEDIA_TUNNEL_TTL_SEC": "90",
    "VOICE_AGENT_MEDIA_TUNNEL_MARK": "100",
    "VOICE_AGENT_MEDIA_TUNNEL_FWMARK": "1",
    "VOICE_AGENT_MEDIA_TUNNEL_ROUTE_TABLE": "100",
    "VOICE_AGENT_MEDIA_TUNNEL_EXCLUDED_CIDRS": (
        "127.0.0.0/8,255.255.255.255/32,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"
    ),
    "VOICE_AGENT_MEDIA_PROXY_HOST": "host.docker.internal",
    "VOICE_AGENT_MEDIA_PROXY_PORT": "32080",
    "VOICE_AGENT_MEDIA_PROVISION_PROXY_HOST": "127.0.0.1",
    "VOICE_AGENT_MEDIA_PROVISION_PROXY_PORT": "3128",
    "VOICE_AGENT_MEDIA_SSH_HOST": "185.181.180.28",
    "VOICE_AGENT_MEDIA_SSH_PORT": "443",
    "VOICE_AGENT_MEDIA_SSH_USER": "dt09",
    "VOICE_AGENT_MEDIA_SSH_KEY_PATH": "/root/.ssh/id_ed25519_tunnel",
    "VOICE_AGENT_MEDIA_SSH_KNOWN_HOSTS_PATH": "/root/.ssh/known_hosts",
    "VOICE_AGENT_MEDIA_SSH_FORWARD_PORT": "18442",
    "VOICE_AGENT_MEDIA_SSH_KEEPALIVE_SEC": "15",
    "VOICE_AGENT_MEDIA_SSH_KEEPALIVE_COUNT": "3",
    "VOICE_AGENT_MEDIA_RELAY_REMOTE_PORT": "8442",
    "VOICE_AGENT_MEDIA_RELAY_USER": "voiceagent",
    "VOICE_AGENT_MEDIA_GOST_IMAGE": "gogost/gost:3",
    "VOICE_AGENT_MEDIA_STUN_HOST": "stun.l.google.com",
    "VOICE_AGENT_MEDIA_STUN_PORT": "19302",
    "VOICE_AGENT_MEDIA_STUN_TIMEOUT_SEC": "10",
}


def load_env(path: Path) -> dict[str, str]:
    values = dotenv_values(path)
    return {key: value for key, value in values.items() if value is not None}


def upsert_env(path: Path, updates: dict[str, str]) -> None:
    lines = path.read_text().splitlines() if path.exists() else []
    remaining = dict(updates)
    output: list[str] = []
    for line in lines:
        key = line.split("=", 1)[0] if "=" in line else ""
        if key in remaining:
            output.append(f"{key}={remaining.pop(key)}")
        else:
            output.append(line)
    output.extend(f"{key}={value}" for key, value in remaining.items())
    path.write_text("\n".join(output).rstrip() + "\n")
    os.chmod(path, 0o600)


def run_ssh(values: dict[str, str], remote_command: list[str]) -> None:
    command = [
        "ssh",
        "-i",
        values["VOICE_AGENT_MEDIA_SSH_KEY_PATH"],
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=15",
        "-o",
        (
            "ProxyCommand=nc -X connect -x "
            f"{values['VOICE_AGENT_MEDIA_PROVISION_PROXY_HOST']}:"
            f"{values['VOICE_AGENT_MEDIA_PROVISION_PROXY_PORT']} %h %p"
        ),
        "-p",
        values["VOICE_AGENT_MEDIA_SSH_PORT"],
        f"{values['VOICE_AGENT_MEDIA_SSH_USER']}@{values['VOICE_AGENT_MEDIA_SSH_HOST']}",
        shlex.join(remote_command),
    ]
    subprocess.run(command, check=True)


def provision(values: dict[str, str]) -> None:
    image = values["VOICE_AGENT_MEDIA_GOST_IMAGE"]
    relay_port = values["VOICE_AGENT_MEDIA_RELAY_REMOTE_PORT"]
    relay_user = values["VOICE_AGENT_MEDIA_RELAY_USER"]
    relay_password = values["VOICE_AGENT_MEDIA_RELAY_PASSWORD"]
    run_ssh(
        values,
        ["sh", "-c", "docker rm -f voice-agent-gost-relay >/dev/null 2>&1 || true"],
    )
    run_ssh(
        values,
        [
            "docker",
            "run",
            "-d",
            "--name",
            "voice-agent-gost-relay",
            "--restart",
            "unless-stopped",
            "-p",
            f"127.0.0.1:{relay_port}:{relay_port}/tcp",
            image,
            "-L",
            f"relay://{relay_user}:{relay_password}@:{relay_port}",
        ],
    )
    run_ssh(
        values,
        ["docker", "inspect", "--format", "{{.State.Running}}", "voice-agent-gost-relay"],
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", type=Path, default=Path(".env"))
    parser.add_argument("--rotate-password", action="store_true")
    parser.add_argument("--write-only", action="store_true")
    args = parser.parse_args()

    values = load_env(args.env)
    updates = {key: values.get(key, default) for key, default in DEFAULTS.items()}
    password = values.get("VOICE_AGENT_MEDIA_RELAY_PASSWORD", "")
    if args.rotate_password or not password:
        password = secrets.token_urlsafe(32)
    updates["VOICE_AGENT_MEDIA_RELAY_PASSWORD"] = password
    upsert_env(args.env, updates)
    values = load_env(args.env)

    if args.write_only:
        print(f"updated {args.env} with media-overlay settings; no secrets were printed")
        return
    provision(values)
    print("private media relay is running; no credentials were printed")


if __name__ == "__main__":
    main()
