#!/usr/bin/env python3
"""Verify that a STUN binding request traverses the configured media overlay."""

from __future__ import annotations

import os
import secrets
import socket


def main() -> None:
    host = os.getenv("VOICE_AGENT_MEDIA_STUN_HOST", "stun.l.google.com")
    port = int(os.getenv("VOICE_AGENT_MEDIA_STUN_PORT", "19302"))
    timeout = float(os.getenv("VOICE_AGENT_MEDIA_STUN_TIMEOUT_SEC", "10"))
    transaction_id = secrets.token_bytes(12)
    request = b"\x00\x01\x00\x00\x21\x12\xa4\x42" + transaction_id

    addresses = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_DGRAM)
    if not addresses:
        raise SystemExit("no IPv4 STUN address resolved")
    target = addresses[0][4]
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        sock.sendto(request, target)
        response, _ = sock.recvfrom(2048)
    if len(response) < 20 or response[:2] != b"\x01\x01":
        raise SystemExit("STUN did not return a binding success response")
    if response[4:8] != b"\x21\x12\xa4\x42" or response[8:20] != transaction_id:
        raise SystemExit("STUN response transaction ID did not match")
    print("media overlay STUN preflight passed")


if __name__ == "__main__":
    main()
