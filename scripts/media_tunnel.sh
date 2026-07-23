#!/bin/sh
# Route locally-originated UDP through GOST's transparent REDU listener.
# The GOST relay is reached only through the SSH sidecar, whose transport uses
# the required HTTP CONNECT proxy on port 3128 (exposed to Docker separately).
set -eu

required() {
    name="$1"
    eval "value=\${$name:-}"
    if [ -z "$value" ]; then
        echo "media tunnel: $name is required" >&2
        exit 64
    fi
}

for name in \
    VOICE_AGENT_MEDIA_TUNNEL_ENABLED \
    VOICE_AGENT_MEDIA_TUNNEL_LISTEN_PORT \
    VOICE_AGENT_MEDIA_TUNNEL_TTL_SEC \
    VOICE_AGENT_MEDIA_TUNNEL_MARK \
    VOICE_AGENT_MEDIA_TUNNEL_FWMARK \
    VOICE_AGENT_MEDIA_TUNNEL_ROUTE_TABLE \
    VOICE_AGENT_MEDIA_SSH_FORWARD_PORT \
    VOICE_AGENT_MEDIA_RELAY_USER \
    VOICE_AGENT_MEDIA_RELAY_PASSWORD; do
    required "$name"
done

if [ "$VOICE_AGENT_MEDIA_TUNNEL_ENABLED" != "true" ]; then
    echo "media tunnel: VOICE_AGENT_MEDIA_TUNNEL_ENABLED must be true" >&2
    exit 64
fi

chain="VOICE_AGENT_GOST_LOCAL"
prerouting_chain="VOICE_AGENT_GOST"
mark="$VOICE_AGENT_MEDIA_TUNNEL_MARK"
fwmark="$VOICE_AGENT_MEDIA_TUNNEL_FWMARK"
table="$VOICE_AGENT_MEDIA_TUNNEL_ROUTE_TABLE"
listen="$VOICE_AGENT_MEDIA_TUNNEL_LISTEN_PORT"

# A restarted container can retain its network namespace. Remove only this
# service's rules first, then recreate them deterministically.
iptables -t mangle -D OUTPUT -p udp -j "$chain" 2>/dev/null || true
iptables -t mangle -F "$chain" 2>/dev/null || true
iptables -t mangle -X "$chain" 2>/dev/null || true
iptables -t mangle -D PREROUTING -p udp -j "$prerouting_chain" 2>/dev/null || true
iptables -t mangle -F "$prerouting_chain" 2>/dev/null || true
iptables -t mangle -X "$prerouting_chain" 2>/dev/null || true
ip rule del fwmark "$fwmark" lookup "$table" 2>/dev/null || true

ip rule add fwmark "$fwmark" lookup "$table"
ip route replace local default dev lo table "$table"
iptables -t mangle -N "$chain"
iptables -t mangle -N "$prerouting_chain"

# Do not capture loopback, broadcast, Docker-private, or GOST's marked egress.
for cidr in ${VOICE_AGENT_MEDIA_TUNNEL_EXCLUDED_CIDRS//,/ }; do
    iptables -t mangle -A "$chain" -p udp -d "$cidr" -j RETURN
    iptables -t mangle -A "$prerouting_chain" -p udp -d "$cidr" -j RETURN
done
iptables -t mangle -A "$chain" -p udp -m mark --mark "$mark" -j RETURN
iptables -t mangle -A "$prerouting_chain" -p udp -m mark --mark "$mark" -j RETURN
iptables -t mangle -A "$chain" -p udp -j MARK --set-mark "$fwmark"
iptables -t mangle -A OUTPUT -p udp -j "$chain"
iptables -t mangle -A "$prerouting_chain" -p udp \
    -j TPROXY --tproxy-mark "${fwmark}/${fwmark}" --on-port "$listen"
iptables -t mangle -A PREROUTING -p udp -j "$prerouting_chain"

relay="relay://${VOICE_AGENT_MEDIA_RELAY_USER}:${VOICE_AGENT_MEDIA_RELAY_PASSWORD}@voice-media-ssh-tunnel:${VOICE_AGENT_MEDIA_SSH_FORWARD_PORT}?so_mark=${mark}"
exec /bin/gost \
    -L "redu://:${listen}?ttl=${VOICE_AGENT_MEDIA_TUNNEL_TTL_SEC}s&so_mark=${mark}" \
    -F "$relay"
