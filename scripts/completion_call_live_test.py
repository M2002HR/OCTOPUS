#!/usr/bin/env python3
"""Exercise Bot opt-in -> real Codex job -> primary-to-tester completion call.

The script uses only the configured second Telethon session as the consenting test user. It
records the primary session's notification audio, verifies automatic hangup, and transcribes the
capture through the deployed Ajil STT path. Credentials and raw session values are never printed.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import wave
from collections import Counter
from pathlib import Path
from time import time
from uuid import uuid4

import aiohttp
from pytgcalls import PyTgCalls
from pytgcalls.types import (
    CallConfig,
    ChatUpdate,
    Device,
    Direction,
    MediaStream,
    RecordStream,
    StreamFrames,
)
from telethon import TelegramClient, events
from telethon.sessions import StringSession

from voice_agent.adapters.uag import UAGClient

SAMPLE_RATE = 48_000
CHANNELS = 1


def _proxy() -> dict[str, object] | None:
    if os.getenv("TELEGRAM_PROXY_ENABLED", "false").strip().casefold() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return None
    proxy: dict[str, object] = {
        "proxy_type": os.environ["TELEGRAM_PROXY_TYPE"],
        "addr": os.environ["TELEGRAM_PROXY_HOST"],
        "port": int(os.environ["TELEGRAM_PROXY_PORT"]),
        "rdns": os.getenv("TELEGRAM_PROXY_RDNS", "true").strip().casefold()
        in {"1", "true", "yes", "on"},
    }
    if os.getenv("TELEGRAM_PROXY_USERNAME", "").strip():
        proxy["username"] = os.environ["TELEGRAM_PROXY_USERNAME"]
    if os.getenv("TELEGRAM_PROXY_PASSWORD", "").strip():
        proxy["password"] = os.environ["TELEGRAM_PROXY_PASSWORD"]
    return proxy


async def _bot_identity() -> tuple[int, str]:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    proxy = os.getenv("TELEGRAM_BOT_PROXY_URL", "").strip() or None
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(
            f"https://api.telegram.org/bot{token}/getMe",
            proxy=proxy,
        ) as response:
            response.raise_for_status()
            payload = await response.json()
    result = payload.get("result") if isinstance(payload, dict) else None
    if not isinstance(result, dict) or not result.get("id") or not result.get("username"):
        raise RuntimeError("Bot API getMe returned no usable identity")
    return int(result["id"]), str(result["username"])


async def _silence(path: Path, duration_seconds: int = 180) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    process = await asyncio.create_subprocess_exec(
        os.getenv("FFMPEG_BIN", "ffmpeg"),
        "-y",
        "-f",
        "lavfi",
        "-i",
        "anullsrc=r=48000:cl=mono",
        "-t",
        str(duration_seconds),
        "-c:a",
        "libopus",
        str(path),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    if await process.wait() != 0:
        raise RuntimeError("ffmpeg could not create the silent answer stream")


def _write_capture(path: Path, pcm: bytes) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(CHANNELS)
        stream.setsampwidth(2)
        stream.setframerate(SAMPLE_RATE)
        stream.writeframes(pcm)
    return round(len(pcm) * 1000 / (SAMPLE_RATE * CHANNELS * 2))


def _has_three_repetitions(transcript: str) -> bool:
    tokens = re.findall(r"[a-z0-9']+", transcript.casefold())
    if len(tokens) < 12:
        return False
    ngrams = Counter(tuple(tokens[index : index + 4]) for index in range(len(tokens) - 3))
    return bool(ngrams) and max(ngrams.values()) >= 3


async def main() -> None:
    run_id = f"completion-call-{uuid4().hex}"
    runtime = Path(os.getenv("RUNTIME_DIR", "/runtime")) / "completion-call-tests" / run_id
    silence = runtime / "answer-silence.ogg"
    capture_path = runtime / "notification.wav"
    await _silence(silence)

    bot_id, bot_username = await _bot_identity()
    primary_username = os.getenv(
        "COMPLETION_CALL_TEST_PRIMARY_USERNAME",
        "sugar_cane_door",
    ).strip()
    tester = TelegramClient(
        StringSession(os.environ["TELEGRAM_TESTER_STRING_SESSION"]),
        int(os.getenv("TELEGRAM_TESTER_API_ID") or os.environ["TELEGRAM_API_ID"]),
        os.getenv("TELEGRAM_TESTER_API_HASH") or os.environ["TELEGRAM_API_HASH"],
        proxy=_proxy(),
    )
    calls = PyTgCalls(tester)
    bot_messages: asyncio.Queue[str] = asyncio.Queue()
    incoming = asyncio.Event()
    ended = asyncio.Event()
    captured = bytearray()
    captured_frames = 0
    answer_error: Exception | None = None
    answer_task: asyncio.Task[None] | None = None
    job_id = ""
    primary_user_id = 0

    @tester.on(events.NewMessage(from_users=bot_id))
    async def _bot_message(event: object) -> None:
        await bot_messages.put(str(getattr(event, "raw_text", "") or ""))

    @calls.on_update()
    async def _call_update(_: PyTgCalls, update: object) -> None:
        nonlocal answer_error, answer_task, captured_frames
        if isinstance(update, StreamFrames):
            if update.direction == Direction.INCOMING and update.device == Device.MICROPHONE:
                for frame in update.frames:
                    captured.extend(frame.frame)
                    captured_frames += 1
            return
        if not isinstance(update, ChatUpdate):
            return
        if (
            update.status & ChatUpdate.Status.INCOMING_CALL
            and update.chat_id == primary_user_id
            and not incoming.is_set()
        ):
            incoming.set()

            async def answer() -> None:
                nonlocal answer_error
                try:
                    stream = MediaStream(silence)
                    await stream.check_stream()
                    await calls.play(
                        update.chat_id,
                        stream,
                        config=CallConfig(timeout=120),
                    )
                    await calls.record(update.chat_id, RecordStream(audio=True))
                except Exception as exc:
                    answer_error = exc
                    ended.set()

            answer_task = asyncio.create_task(answer())
            return
        if update.status & ChatUpdate.Status.DISCARDED_CALL and incoming.is_set():
            ended.set()

    async def wait_bot(pattern: str, timeout: float = 120) -> str:
        deadline = asyncio.get_running_loop().time() + timeout
        regex = re.compile(pattern, re.IGNORECASE | re.DOTALL)
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise TimeoutError(f"Bot response did not match {pattern!r}")
            text = await asyncio.wait_for(bot_messages.get(), timeout=remaining)
            if regex.search(text):
                return text

    await tester.connect()
    try:
        if not await tester.is_user_authorized():
            raise RuntimeError("tester session is not authorized")
        me = await tester.get_me()
        primary = await tester.get_entity(primary_username)
        primary_user_id = int(getattr(primary, "id", 0))
        if int(getattr(primary, "id", 0)) == int(getattr(me, "id", 0)):
            raise RuntimeError("primary and tester sessions resolved to the same account")
        await calls.start()
        bot = await tester.get_entity(bot_username)

        await tester.send_message(bot, "/completion_call on")
        toggle = await wait_bot(r"(enabled|Send one task first)")
        if "Send one task first" in toggle:
            await tester.send_message(bot, "Reply with exactly: tester registered.")
            await wait_bot(r"Request queued", timeout=60)
            await asyncio.sleep(2)
            await tester.send_message(bot, "/completion_call on")
            await wait_bot(r"completion calls are now enabled", timeout=60)

        await tester.send_message(bot, "/project octopus")
        await wait_bot(r"Workspace selected: octopus", timeout=60)
        objective = (
            "Inspect the OCTOPUS README and report the configured default Codex model. "
            "Do not modify any files. Keep the final answer under two sentences."
        )
        await tester.send_message(bot, objective)
        queued = await wait_bot(r"Job ID:\s*([A-Za-z0-9_-]+)", timeout=60)
        match = re.search(r"Job ID:\s*([A-Za-z0-9_-]+)", queued)
        if match is None:
            raise RuntimeError("queued Bot response did not include a job ID")
        job_id = match.group(1)

        await asyncio.wait_for(incoming.wait(), timeout=900)
        await asyncio.wait_for(ended.wait(), timeout=240)
        if answer_error is not None:
            raise answer_error
        if answer_task is not None:
            await asyncio.wait_for(answer_task, timeout=10)

        duration_ms = _write_capture(capture_path, bytes(captured))
        if captured_frames <= 0 or duration_ms < 3_000:
            raise RuntimeError("completion call produced no usable remote audio")

        uag = UAGClient(
            base_url=os.getenv("UAG_BASE_URL", "http://ajil_gateway:8080"),
            chat_endpoint=os.getenv("UAG_CHAT_ENDPOINT", "/v1/chat/completions"),
            transcriptions_endpoint=os.getenv(
                "UAG_AUDIO_TRANSCRIPTIONS_ENDPOINT",
                "/v1/audio/transcriptions",
            ),
            timeout_seconds=int(os.getenv("UAG_TIMEOUT_SEC", "45")),
            auth_token=os.getenv("UAG_AUTH_TOKEN", ""),
            auth_header_name=os.getenv("UAG_AUTH_HEADER_NAME", "x-api-token"),
            models=(),
            providers=(),
            transcription_provider=os.getenv("AI_TRANSCRIPTION_PROVIDER", ""),
            transcription_models=(),
        )
        try:
            transcript = ""
            last_error: Exception | None = None
            for attempt in range(1, 5):
                try:
                    transcript = await uag.transcribe(capture_path, language="en")
                    break
                except Exception as exc:
                    last_error = exc
                    if attempt < 4:
                        await asyncio.sleep(attempt * 5)
            if not transcript:
                raise RuntimeError(
                    "Ajil STT failed after four bounded attempts"
                ) from last_error
        finally:
            await uag.aclose()
        if not _has_three_repetitions(transcript):
            raise RuntimeError("STT did not detect three repeated notification phrases")

        summary = {
            "auto_hangup_observed": ended.is_set(),
            "captured_duration_ms": duration_ms,
            "captured_frames": captured_frames,
            "event": "completion_call.live_test.completed",
            "job_id": job_id,
            "repetition_check": "passed",
            "run_id": run_id,
            "timestamp": time(),
            "transcript": transcript,
        }
        (runtime / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    finally:
        if answer_task is not None and not answer_task.done():
            answer_task.cancel()
            await asyncio.gather(answer_task, return_exceptions=True)
        await tester.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
