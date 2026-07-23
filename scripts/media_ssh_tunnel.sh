#!/bin/sh
# Keep a private relay port available to the media tunnel.  The SSH transport
# itself is always established through the existing HTTP CONNECT proxy.
set -eu

required() {
    name="$1"
    eval "value=\${$name:-}"
    if [ -z "$value" ]; then
        echo "media SSH tunnel: $name is required" >&2
        exit 64
    fi
}

required VOICE_AGENT_MEDIA_SSH_HOST
required VOICE_AGENT_MEDIA_SSH_USER
required VOICE_AGENT_MEDIA_SSH_KEY_PATH
required VOICE_AGENT_MEDIA_SSH_KNOWN_HOSTS_PATH
required VOICE_AGENT_MEDIA_PROXY_HOST
required VOICE_AGENT_MEDIA_PROXY_PORT
required VOICE_AGENT_MEDIA_SSH_FORWARD_PORT
required VOICE_AGENT_MEDIA_RELAY_REMOTE_PORT

if [ ! -r "$VOICE_AGENT_MEDIA_SSH_KEY_PATH" ]; then
    echo "media SSH tunnel: private key is not readable" >&2
    exit 64
fi
if [ ! -r "$VOICE_AGENT_MEDIA_SSH_KNOWN_HOSTS_PATH" ]; then
    echo "media SSH tunnel: known_hosts is not readable" >&2
    exit 64
fi

exec ssh \
    -N \
    -g \
    -i "$VOICE_AGENT_MEDIA_SSH_KEY_PATH" \
    -p "${VOICE_AGENT_MEDIA_SSH_PORT:-443}" \
    -o BatchMode=yes \
    -o ExitOnForwardFailure=yes \
    -o ServerAliveInterval="${VOICE_AGENT_MEDIA_SSH_KEEPALIVE_SEC:-15}" \
    -o ServerAliveCountMax="${VOICE_AGENT_MEDIA_SSH_KEEPALIVE_COUNT:-3}" \
    -o StrictHostKeyChecking=yes \
    -o UserKnownHostsFile="$VOICE_AGENT_MEDIA_SSH_KNOWN_HOSTS_PATH" \
    -o GlobalKnownHostsFile=/dev/null \
    -o "ProxyCommand=nc -X connect -x ${VOICE_AGENT_MEDIA_PROXY_HOST}:${VOICE_AGENT_MEDIA_PROXY_PORT} %h %p" \
    -L "0.0.0.0:${VOICE_AGENT_MEDIA_SSH_FORWARD_PORT}:127.0.0.1:${VOICE_AGENT_MEDIA_RELAY_REMOTE_PORT}" \
    "${VOICE_AGENT_MEDIA_SSH_USER}@${VOICE_AGENT_MEDIA_SSH_HOST}"
