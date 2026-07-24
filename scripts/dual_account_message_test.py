#!/usr/bin/env python3
"""Run consented, end-to-end private-message checks between the two tester sessions.

The primary account is the running service; the second tester account sends every input and
collects only replies from that primary account.  The target is deliberately hard-coded to the
primary tester username so this script cannot contact the external account.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from time import time
from uuid import uuid4

from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl import types

from voice_agent.adapters.edge_tts import EdgeSpeechSynthesizer
from voice_agent.english import is_english_output

TARGET_USERNAME = "sugar_cane_door"
REPLY_TIMEOUT_SECONDS = 90


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


async def _make_colour_image(destination: Path, colour: str) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    process = await asyncio.create_subprocess_exec(
        os.getenv("FFMPEG_BIN", "ffmpeg"),
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c={colour}:s=320x240:d=1",
        "-frames:v",
        "1",
        str(destination),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    if await process.wait() != 0:
        raise RuntimeError("ffmpeg could not create the image fixture")
    return destination


def _response_kind(message: types.Message) -> str:
    if message.voice:
        return "voice"
    if message.photo:
        return "photo"
    return "text"


async def main() -> None:
    tester_session = os.environ["TELEGRAM_TESTER_STRING_SESSION"]
    api_id = int(os.getenv("TELEGRAM_TESTER_API_ID") or os.environ["TELEGRAM_API_ID"])
    api_hash = os.getenv("TELEGRAM_TESTER_API_HASH") or os.environ["TELEGRAM_API_HASH"]
    run_id = f"dual-message-{uuid4()}"
    runtime = Path(os.getenv("RUNTIME_DIR", "/runtime")) / "dual-account-tests" / run_id
    responses: asyncio.Queue[types.Message] = asyncio.Queue()
    results: list[dict[str, object]] = []
    client = TelegramClient(StringSession(tester_session), api_id, api_hash, proxy=_proxy())

    async def wait_for_reply(expected_kind: str, case: str) -> types.Message:
        response = await asyncio.wait_for(responses.get(), timeout=REPLY_TIMEOUT_SECONDS)
        actual_kind = _response_kind(response)
        if actual_kind != expected_kind:
            raise RuntimeError(f"{case}: expected {expected_kind}, received {actual_kind}")
        text = (response.message or "").strip()
        if actual_kind == "text" and not is_english_output(text):
            raise RuntimeError(f"{case}: text reply was not English ASCII")
        results.append(
            {
                "case": case,
                "response_kind": actual_kind,
                "text": text if actual_kind == "text" else "[voice note]",
                "message_id": response.id,
            }
        )
        return response

    await client.connect()
    try:
        if not await client.is_user_authorized():
            raise RuntimeError("tester session is not authorized")
        target = await client.get_entity(TARGET_USERNAME)
        target_id = int(target.id)

        @client.on(events.NewMessage(incoming=True, from_users=target_id))
        async def collect(event: events.NewMessage.Event) -> None:
            await responses.put(event.message)

        while not responses.empty():
            responses.get_nowait()

        await client.send_message(target, "/text Explain unit testing in one short sentence.")
        text_reply = await wait_for_reply("text", "explicit_text")

        await client.send_message(
            target,
            "What is a regression test? Answer in one short sentence.",
        )
        await wait_for_reply("text", "default_text")

        await client.send_message(target, "/voice Explain code review in one short sentence.")
        voice_reply = await wait_for_reply("voice", "explicit_voice")
        voice_path = runtime / "received-voice.ogg"
        downloaded = await voice_reply.download_media(file=voice_path)
        if not downloaded or not voice_path.is_file() or voice_path.stat().st_size == 0:
            raise RuntimeError("explicit_voice: response voice note was not downloadable")

        synthesizer = EdgeSpeechSynthesizer(
            voice=os.getenv("EDGE_TTS_VOICE", "en-US-AndrewMultilingualNeural"),
            rate=os.getenv("EDGE_TTS_RATE", "+0%"),
            ffmpeg_bin=os.getenv("FFMPEG_BIN", "ffmpeg"),
        )
        incoming_voice = runtime / "incoming-question.ogg"
        await synthesizer.synthesize(
            "What is a unit test? Answer in one short sentence.", incoming_voice, language="en"
        )
        await client.send_file(target, incoming_voice, voice_note=True)
        await wait_for_reply("text", "incoming_voice_stt")

        blue_image = await _make_colour_image(runtime / "blue.jpg", "blue")
        blue_message = await client.send_file(
            target,
            blue_image,
            caption=(
                "Analyze this image. What is its dominant color? "
                "Reply in one English sentence."
            ),
        )
        await wait_for_reply("text", "image_analysis")

        red_image = await _make_colour_image(runtime / "red.jpg", "red")
        await client.send_file(
            target,
            red_image,
            caption="Describe this image briefly in English.",
        )
        await wait_for_reply("text", "image_description")

        await client.send_message(
            target,
            "Please expand on the referenced unit-testing answer in one short sentence.",
            reply_to=text_reply.id,
        )
        await wait_for_reply("text", "reply_to_text")

        await client.send_message(
            target,
            "What was the main point of the referenced voice answer? Reply as text.",
            reply_to=voice_reply.id,
        )
        await wait_for_reply("text", "reply_to_voice")

        await client.send_message(
            target,
            "What color was the referenced image? Reply in one English sentence.",
            reply_to=blue_message.id,
        )
        await wait_for_reply("text", "reply_to_image")

        summary = {
            "event": "tester.messages.completed",
            "run_id": run_id,
            "results": results,
            "timestamp": time(),
        }
        runtime.mkdir(parents=True, exist_ok=True)
        (runtime / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        print(json.dumps(summary, ensure_ascii=True))
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
