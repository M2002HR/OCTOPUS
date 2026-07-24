#!/usr/bin/env python3
"""Place a consented two-account Telegram call and capture the agent's audio replies.

The script deliberately uses a separate Telethon string session as the caller. It never prints
session strings, tokens, call keys, or the captured audio; it emits only test progress and writes
the captured remote PCM to the mounted runtime directory for authorized STT verification.
"""

from __future__ import annotations

import asyncio
import json
import os
import wave
from pathlib import Path
from time import time
from uuid import uuid4

from pytgcalls import PyTgCalls
from pytgcalls.types import (
    CallConfig,
    Device,
    Direction,
    MediaStream,
    RecordStream,
    StreamFrames,
)
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl import types

from voice_agent.adapters.edge_tts import EdgeSpeechSynthesizer

SAMPLE_RATE = 48_000
CHANNELS = 1
INITIAL_DELAY_SECONDS = 5
# The agent must finish VAD, STT, LLM, TTS and playback before the next synthetic
# caller turn begins. Sending during playback is intentionally discarded by the
# anti-echo guard, so this must exceed the longest expected first-turn path.
TURN_WINDOW_SECONDS = 38


def _proxy() -> dict[str, object] | None:
    if os.getenv("TELEGRAM_PROXY_ENABLED", "false").strip().casefold() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return None
    return {
        "proxy_type": os.environ["TELEGRAM_PROXY_TYPE"],
        "addr": os.environ["TELEGRAM_PROXY_HOST"],
        "port": int(os.environ["TELEGRAM_PROXY_PORT"]),
        "rdns": os.getenv("TELEGRAM_PROXY_RDNS", "true").strip().casefold()
        in {"1", "true", "yes", "on"},
    }


async def _delayed_audio(synthesizer: EdgeSpeechSynthesizer, text: str, destination: Path) -> Path:
    await synthesizer.synthesize(text, destination, language="en")
    delayed = destination.with_name(f"delayed-{destination.name}")
    process = await asyncio.create_subprocess_exec(
        os.getenv("FFMPEG_BIN", "ffmpeg"),
        "-y",
        "-i",
        str(destination),
        "-af",
        f"adelay={INITIAL_DELAY_SECONDS * 1000}:all=1",
        "-ac",
        str(CHANNELS),
        "-ar",
        str(SAMPLE_RATE),
        "-c:a",
        "libopus",
        str(delayed),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    if await process.wait() != 0:
        raise RuntimeError("ffmpeg could not create the delayed test utterance")
    return delayed


def _write_capture(path: Path, pcm: bytes) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(CHANNELS)
        stream.setsampwidth(2)
        stream.setframerate(SAMPLE_RATE)
        stream.writeframes(pcm)
    return round(len(pcm) * 1000 / (SAMPLE_RATE * CHANNELS * 2))


async def main() -> None:
    target_username = os.environ["DUAL_TEST_TARGET_USERNAME"].strip()
    if not target_username:
        raise RuntimeError("DUAL_TEST_TARGET_USERNAME is required")
    tester_session = os.environ["TELEGRAM_TESTER_STRING_SESSION"]
    api_id = int(os.getenv("TELEGRAM_TESTER_API_ID") or os.environ["TELEGRAM_API_ID"])
    api_hash = os.getenv("TELEGRAM_TESTER_API_HASH") or os.environ["TELEGRAM_API_HASH"]
    run_id = f"dual-call-{uuid4()}"
    runtime = Path(os.getenv("RUNTIME_DIR", "/runtime")) / "dual-account-tests" / run_id
    synthesizer = EdgeSpeechSynthesizer(
        voice=os.getenv("EDGE_TTS_VOICE", "en-US-AndrewMultilingualNeural"),
        rate=os.getenv("EDGE_TTS_RATE", "+0%"),
        ffmpeg_bin=os.getenv("FFMPEG_BIN", "ffmpeg"),
    )
    utterances = [
        await _delayed_audio(
            synthesizer,
            "Please tell me a short fact about octopuses.",
            runtime / "turn-1.ogg",
        ),
        await _delayed_audio(
            synthesizer,
            "Please tell me another interesting fact about octopuses.",
            runtime / "turn-2.ogg",
        ),
    ]
    captured = bytearray()
    captured_frames = 0
    client = TelegramClient(StringSession(tester_session), api_id, api_hash, proxy=_proxy())
    calls = PyTgCalls(client)

    @calls.on_update()
    async def _capture(_: PyTgCalls, update: object) -> None:
        nonlocal captured_frames
        if not isinstance(update, StreamFrames):
            return
        if update.direction != Direction.INCOMING or update.device != Device.MICROPHONE:
            return
        for frame in update.frames:
            captured.extend(frame.frame)
            captured_frames += 1

    await client.connect()
    try:
        if not await client.is_user_authorized():
            raise RuntimeError("tester session is not authorized")
        target = await client.get_entity(target_username)
        if not isinstance(target, types.User) or target.bot or target.deleted:
            raise RuntimeError("test target must be an active non-bot user")
        await calls.start()
        print(json.dumps({"event": "tester.call.starting", "run_id": run_id}))
        for number, audio in enumerate(utterances, start=1):
            stream = MediaStream(audio)
            await stream.check_stream()
            await calls.play(
                target.id,
                stream,
                config=CallConfig(timeout=120),
            )
            await calls.record(target.id, RecordStream(audio=True))
            print(json.dumps({"event": "tester.turn.playing", "run_id": run_id, "turn": number}))
            await asyncio.sleep(TURN_WINDOW_SECONDS)
        await calls.leave_call(target.id)
        output = runtime / "agent-replies.wav"
        duration_ms = _write_capture(output, bytes(captured))
        summary = {
            "captured_frames": captured_frames,
            "captured_duration_ms": duration_ms,
            "capture_path": str(output),
            "event": "tester.call.completed",
            "run_id": run_id,
            "timestamp": time(),
        }
        (runtime / "summary.json").write_text(json.dumps(summary, sort_keys=True) + "\n")
        print(json.dumps(summary, sort_keys=True))
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
