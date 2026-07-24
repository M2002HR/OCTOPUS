from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from pathlib import Path


class EdgeTTSError(RuntimeError):
    pass


class EdgeSpeechSynthesizer:
    def __init__(
        self, *, voice: str, rate: str, ffmpeg_bin: str
    ) -> None:
        self.voice = voice
        self.rate = rate
        self.ffmpeg_bin = ffmpeg_bin

    async def synthesize(
        self, text: str, destination: Path, *, language: str | None = None
    ) -> int:
        if not text.strip():
            raise EdgeTTSError("cannot synthesize an empty response")
        destination.parent.mkdir(parents=True, exist_ok=True)
        mp3 = destination.with_suffix(".mp3")
        try:
            import edge_tts
        except ImportError as exc:  # pragma: no cover - dependency is required in production
            raise EdgeTTSError("edge-tts is not installed") from exc
        voice = self._voice_for(text, language)
        communicate = edge_tts.Communicate(text=text, voice=voice, rate=self.rate)
        await communicate.save(str(mp3))
        try:
            await asyncio.to_thread(self._to_ogg_opus, mp3, destination)
            return await asyncio.to_thread(self._duration_ms, destination)
        finally:
            mp3.unlink(missing_ok=True)

    def _voice_for(self, text: str, language: str | None) -> str:
        return self.voice

    def _to_ogg_opus(self, source: Path, destination: Path) -> None:
        executable = shutil.which(self.ffmpeg_bin)
        if executable is None:
            raise EdgeTTSError(f"ffmpeg executable {self.ffmpeg_bin!r} was not found")
        result = subprocess.run(
            [
                executable,
                "-y",
                "-i",
                str(source),
                "-ac",
                "1",
                "-ar",
                "48000",
                "-c:a",
                "libopus",
                "-application",
                "voip",
                str(destination),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise EdgeTTSError(result.stderr.strip() or "ffmpeg failed to create Opus audio")

    def _duration_ms(self, path: Path) -> int:
        probe = shutil.which("ffprobe")
        if probe is None:
            return 0
        result = subprocess.run(
            [probe, "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return 0
        try:
            return max(0, round(float(json.loads(result.stdout)["format"]["duration"]) * 1000))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return 0
