#!/usr/bin/env python3
"""Run a consented real call from the primary session to the tester session.

The primary account runs the project's real outbound voice pipeline.  The tester account answers
the incoming Telegram call, sends two generated English utterances, and records the agent's audio.
No external or personal account is contacted by this script.
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
    ChatUpdate,
    Device,
    Direction,
    MediaStream,
    RecordStream,
    StreamFrames,
)
from telethon import TelegramClient
from telethon.sessions import StringSession

from voice_agent.adapters.edge_tts import EdgeSpeechSynthesizer
from voice_agent.config import Settings
from voice_agent.live import LiveVoiceAssistant

SAMPLE_RATE = 48_000
CHANNELS = 1
INITIAL_DELAY_SECONDS = 5
TURN_WINDOW_SECONDS = int(os.getenv("OUTBOUND_TEST_TURN_WINDOW_SECONDS", "42"))


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
    target_username = os.environ["OUTBOUND_TEST_TARGET_USERNAME"].strip()
    if target_username.casefold() != "ir_rz_mohraz1":
        raise RuntimeError("this consented test must target only the second tester session")
    run_id = f"first-to-second-{uuid4()}"
    runtime = Path(os.getenv("RUNTIME_DIR", "/runtime")) / "dual-account-tests" / run_id
    synthesizer = EdgeSpeechSynthesizer(
        voice=os.getenv("EDGE_TTS_VOICE", "en-US-AndrewMultilingualNeural"),
        rate=os.getenv("EDGE_TTS_RATE", "+0%"),
        ffmpeg_bin=os.getenv("FFMPEG_BIN", "ffmpeg"),
    )
    scenario = os.getenv("OUTBOUND_TEST_SCENARIO", "smoke").strip().casefold()
    if scenario == "project_manager":
        texts = (
            "I have started the authentication feature. The login screen is ready, but I need "
            "confirmation on password reset requirements.",
            "I will add email reset links that expire after fifteen minutes and log every reset "
            "attempt. Should I also require two factor authentication?",
            "The API tests are passing. I found one issue: the mobile layout clips the reset "
            "button on small screens. I can fix it today.",
            "I will fix the mobile layout, add the reset audit logs, and open a pull request "
            "with tests before the end of the day.",
        )
    else:
        texts = (
            "Please tell me a short fact about octopuses.",
            "Please tell me another interesting fact about octopuses.",
        )
    utterances = [
        await _delayed_audio(synthesizer, text, runtime / f"turn-{number}.ogg")
        for number, text in enumerate(texts, start=1)
    ]
    captured = bytearray()
    captured_frames = 0
    answer_started = asyncio.Event()
    answer_finished = asyncio.Event()
    answer_error: Exception | None = None
    answer_task: asyncio.Task[None] | None = None
    tester = TelegramClient(
        StringSession(os.environ["TELEGRAM_TESTER_STRING_SESSION"]),
        int(os.getenv("TELEGRAM_TESTER_API_ID") or os.environ["TELEGRAM_API_ID"]),
        os.getenv("TELEGRAM_TESTER_API_HASH") or os.environ["TELEGRAM_API_HASH"],
        proxy=_proxy(),
    )
    calls = PyTgCalls(tester)

    @calls.on_update()
    async def _on_update(_: PyTgCalls, update: object) -> None:
        nonlocal answer_task, captured_frames
        if isinstance(update, StreamFrames):
            if update.direction == Direction.INCOMING and update.device == Device.MICROPHONE:
                for frame in update.frames:
                    captured.extend(frame.frame)
                    captured_frames += 1
            return
        if not isinstance(update, ChatUpdate) or not (
            update.status & ChatUpdate.Status.INCOMING_CALL
        ):
            return
        if answer_started.is_set():
            return
        answer_started.set()

        async def answer() -> None:
            nonlocal answer_error
            try:
                for number, audio in enumerate(utterances, start=1):
                    stream = MediaStream(audio)
                    await stream.check_stream()
                    await calls.play(update.chat_id, stream, config=CallConfig(timeout=120))
                    await calls.record(update.chat_id, RecordStream(audio=True))
                    print(
                        json.dumps(
                            {"event": "tester.turn.playing", "run_id": run_id, "turn": number}
                        )
                    )
                    await asyncio.sleep(TURN_WINDOW_SECONDS)
                await calls.leave_call(update.chat_id)
            except Exception as exc:  # pragma: no cover - live Telegram integration failure
                answer_error = exc
            finally:
                answer_finished.set()

        answer_task = asyncio.create_task(answer())

    assistant = LiveVoiceAssistant(Settings.load())
    await tester.connect()
    try:
        if not await tester.is_user_authorized():
            raise RuntimeError("tester session is not authorized")
        await calls.start()
        print(json.dumps({"event": "tester.waiting_for_call", "run_id": run_id}))
        call = await assistant.place_test_call(target_username)
        await asyncio.wait_for(answer_started.wait(), timeout=60)
        timeout = TURN_WINDOW_SECONDS * len(utterances) + 60
        await asyncio.wait_for(answer_finished.wait(), timeout=timeout)
        if answer_error is not None:
            raise answer_error
        output = runtime / "agent-replies.wav"
        duration_ms = _write_capture(output, bytes(captured))
        summary = {
            "call_id": call.id,
            "captured_duration_ms": duration_ms,
            "captured_frames": captured_frames,
            "capture_path": str(output),
            "event": "tester.call.completed",
            "run_id": run_id,
            "timestamp": time(),
        }
        (runtime / "summary.json").write_text(json.dumps(summary, sort_keys=True) + "\n")
        print(json.dumps(summary, sort_keys=True))
    finally:
        if answer_task is not None and not answer_task.done():
            answer_task.cancel()
            await asyncio.gather(answer_task, return_exceptions=True)
        await assistant.close()
        await tester.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
