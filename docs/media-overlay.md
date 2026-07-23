# UDP media overlay

## Purpose

Telegram private-call signaling already uses the configured HTTP proxy. The host's direct UDP
egress is unavailable, however, so NTgCalls cannot complete its media handshake without an
overlay. This deployment uses GOST's Linux `redu` transparent UDP listener and its authenticated
relay protocol. The relay protocol is inside SSH encryption and is never exposed publicly.

## Traffic path

```text
voice-agent UDP
  -> shared voice-media-tunnel network namespace (TPROXY / GOST redu)
  -> authenticated GOST relay client
  -> voice-media-ssh-tunnel
  -> HTTP CONNECT proxy at host.docker.internal:32080
  -> host's existing 127.0.0.1:3128 proxy
  -> SSH on the remote server's port 443
  -> loopback-only GOST relay on remote port 8442
  -> Telegram/STUN UDP endpoint
```

`32080` is the Docker-visible forwarding endpoint for the mandatory host proxy on `3128`; it is
not an alternative proxy. The SSH `ProxyCommand` makes the dependency explicit. The relay server
is published as `127.0.0.1:8442` on the remote host, so only the SSH forward can reach it.

## Provisioning

1. Confirm the root `.env` contains the ordinary Telegram proxy variables and that the host proxy
   is running on port `3128`.
2. Ensure `VOICE_AGENT_MEDIA_SSH_KEY_PATH` and
   `VOICE_AGENT_MEDIA_SSH_KNOWN_HOSTS_PATH` are readable on the host. The known-hosts file is
   mounted read-only and strict host-key checking is enabled.
3. Run `python3 scripts/provision_media_relay.py` from the project root. It creates missing media
   settings in the root `.env`, generates an authenticated relay password without printing it,
   and starts/replaces only `voice-agent-gost-relay` on the configured remote host. Provisioning
   also reaches remote SSH through `127.0.0.1:3128` by default.
4. Start the stack with `docker compose --profile agent up -d --build`.

Use `--write-only` to prepare `.env` without changing the remote host. Use `--rotate-password`
only when you intend to reprovision the remote relay immediately; it invalidates the old relay
credential.

## Configuration

All deployment values live in the root `.env`; `.env.example` documents the full set.

| Variable | Meaning |
| --- | --- |
| `VOICE_AGENT_MEDIA_TUNNEL_ENABLED` | Must be `true` for the Compose agent profile. |
| `VOICE_AGENT_MEDIA_TUNNEL_LISTEN_PORT` | Local transparent GOST UDP listener; default `12345`. |
| `VOICE_AGENT_MEDIA_TUNNEL_TTL_SEC` | Idle lifetime for a UDP association; default `90`. |
| `VOICE_AGENT_MEDIA_TUNNEL_MARK`, `VOICE_AGENT_MEDIA_TUNNEL_FWMARK`, `VOICE_AGENT_MEDIA_TUNNEL_ROUTE_TABLE` | Linux policy-routing loop-prevention values. Keep unique if this host runs another transparent proxy. |
| `VOICE_AGENT_MEDIA_TUNNEL_EXCLUDED_CIDRS` | Comma-separated private/loopback traffic excluded from interception. |
| `VOICE_AGENT_MEDIA_PROXY_HOST`, `VOICE_AGENT_MEDIA_PROXY_PORT` | Docker-visible endpoint for the mandatory HTTP proxy. Use `host.docker.internal:32080` for the existing host port `3128`. |
| `VOICE_AGENT_MEDIA_PROVISION_PROXY_HOST`, `VOICE_AGENT_MEDIA_PROVISION_PROXY_PORT` | Host-side endpoint used by the provisioning script; use `127.0.0.1:3128`. |
| `VOICE_AGENT_MEDIA_SSH_*` | Remote SSH identity, verified host-key file, keepalive policy, and container-local forward. |
| `VOICE_AGENT_MEDIA_RELAY_*` | Private remote relay listener and authentication. Treat the password as a secret. |
| `VOICE_AGENT_MEDIA_GOST_IMAGE` | Approved GOST image reference for both ends. |

## Validation and operations

Check all three services before a real call:

```bash
docker compose --profile agent ps
docker logs agent-voice-media-ssh-tunnel-1 --tail 100
docker logs agent-voice-media-tunnel-1 --tail 100
docker logs agent-voice-agent-1 --tail 100
```

The `voice-media-ssh-tunnel` health check verifies the local SSH forward; the media-tunnel health
check verifies its policy-routing rule. Run the network acceptance test from the agent's shared
network namespace:

```bash
docker compose --profile agent exec -T voice-agent python /app/scripts/media_overlay_stun_probe.py
```

It must print `media overlay STUN preflight passed`. This proves the complete configured path
without placing a Telegram call.

For a failed call, retain the three container logs plus the application audit rows. Do not expose
the relay port or disable strict SSH host-key checking to troubleshoot it.

## Security model

- The remote relay only listens on remote loopback.
- The GOST relay has a generated password and runs inside the encrypted SSH channel.
- SSH is pinned to the existing `known_hosts` entry and does not accept interactive passwords.
- The SSH transport reaches the remote host only through the configured HTTP CONNECT proxy.
- The media sidecar has `NET_ADMIN` only because Linux transparent UDP routing requires it; the
  application process remains unprivileged in the same isolated network namespace.

GOST documents that its bare relay protocol carries TCP and UDP but does not itself encrypt data;
SSH supplies that encryption in this design. See the official [GOST relay documentation](https://gost.run/en/tutorials/protocols/relay/)
and [transparent UDP routing guide](https://gost.run/en/tutorials/redirect/).
