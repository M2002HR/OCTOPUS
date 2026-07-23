#!/usr/bin/env python3
"""Create the root .env from approved existing local configuration without printing secrets."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import dotenv_values

UAG_PREFIXES = ("UAG_", "AI_CHAT_", "AI_TRANSCRIPTION_")
TELEGRAM_KEYS = {
    "TELEGRAM_API_ID",
    "TELEGRAM_API_HASH",
    "TELEGRAM_STRING_SESSION",
    "TELEGRAM_PROXY_ENABLED",
    "TELEGRAM_PROXY_TYPE",
    "TELEGRAM_PROXY_HOST",
    "TELEGRAM_PROXY_PORT",
    "TELEGRAM_PROXY_USERNAME",
    "TELEGRAM_PROXY_PASSWORD",
    "TELEGRAM_PROXY_RDNS",
}


def merge(
    target: dict[str, str], source: dict[str, str | None], keys: set[str] | tuple[str, ...]
) -> None:
    for key in keys:
        value = source.get(key)
        if value is not None:
            target[key] = value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gerdoo", type=Path, default=Path("/root/Gerdoo_AI/.env"))
    parser.add_argument("--triak", type=Path, default=Path("/root/Triak_Trade/.env.local"))
    parser.add_argument("--output", type=Path, default=Path(".env"))
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite existing {args.output}")
    gerdoo = dict(dotenv_values(args.gerdoo))
    triak = dict(dotenv_values(args.triak))
    target: dict[str, str] = {}
    merge(target, triak, TELEGRAM_KEYS)
    merge(target, gerdoo, tuple(key for key in gerdoo if key.startswith(UAG_PREFIXES)))
    target.update(
        {
            "APP_ENV": "development",
            "LOG_LEVEL": "INFO",
            "RUNTIME_DIR": "runtime",
            "AUDIT_DATABASE_PATH": "runtime/voice_agent.sqlite3",
            "AUDIT_JSONL_PATH": "runtime/events.jsonl",
            "VOICE_AGENT_ALLOWED_PEER_IDS": "121166433",
            "VOICE_AGENT_TEST_PEER_USERNAME": "we_are_waiting_for_him",
            "VOICE_AGENT_REQUIRE_DISCLOSURE": "true",
            "VOICE_AGENT_RECORDING_MODE": "transcript_only",
            "VOICE_AGENT_MAX_TURN_SECONDS": "45",
            "VOICE_AGENT_CALL_TIMEOUT_SEC": "120",
            "VOICE_AGENT_MAX_HISTORY_MESSAGES": "12",
            "VOICE_AGENT_LANGUAGE": "fa",
            "VOICE_AGENT_VAD_START_RMS": "350",
            "VOICE_AGENT_VAD_CONTINUE_RMS": "240",
            "VOICE_AGENT_VAD_START_MS": "80",
            "VOICE_AGENT_VAD_END_SILENCE_MS": "600",
            "VOICE_AGENT_VAD_MIN_UTTERANCE_MS": "250",
            "VOICE_AGENT_VAD_PRE_ROLL_MS": "200",
            "VOICE_AGENT_AUDIO_SAMPLE_RATE": "48000",
            "VOICE_AGENT_AUDIO_CHANNELS": "1",
            "VOICE_AGENT_SYSTEM_PROMPT": (
                "You are a helpful general voice assistant. Be concise, truthful, "
                "and disclose that you are automated."
            ),
            "EDGE_TTS_VOICE": "fa-IR-DilaraNeural",
            "EDGE_TTS_RATE": "+0%",
            "FFMPEG_BIN": "ffmpeg",
        }
    )
    content = "\n".join(f"{key}={value}" for key, value in sorted(target.items())) + "\n"
    args.output.write_text(content)
    os.chmod(args.output, 0o600)
    print(f"created {args.output} with {len(target)} keys; secret values were not printed")


if __name__ == "__main__":
    main()
