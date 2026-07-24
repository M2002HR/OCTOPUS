from __future__ import annotations

import wave
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from voice_agent.audio import VoiceActivityDetector


@dataclass(slots=True)
class PcmTurnAssembler:
    """Convert PCM frames to complete low-latency turns using a deterministic VAD.

    A turn starts only after sustained speech, includes a short pre-roll so the
    first phoneme is preserved, and ends only after a sustained trailing pause.
    """

    output_dir: Path
    on_utterance: Callable[[Path], None]
    end_silence_ms: int = 600
    min_speech_ms: int = 80
    min_utterance_ms: int = 250
    pre_roll_ms: int = 200
    max_turn_ms: int = 45_000
    detector: VoiceActivityDetector = field(default_factory=VoiceActivityDetector)
    sample_rate: int = 48_000
    # The explicit speaker capture configured in ``TelethonVoipEngine`` emits
    # 48 kHz mono signed PCM frames.
    channels: int = 1
    _frames: list[bytes] = field(default_factory=list, init=False)
    _pre_roll: list[tuple[bytes, int]] = field(default_factory=list, init=False)
    _candidate_frames: list[tuple[bytes, int]] = field(default_factory=list, init=False)
    _candidate_speech_ms: int = field(default=0, init=False)
    _silence_ms: int = field(default=0, init=False)
    _utterance_ms: int = field(default=0, init=False)
    _speech_ms: int = field(default=0, init=False)
    _active: bool = field(default=False, init=False)
    _counter: int = field(default=0, init=False)

    def feed(self, pcm16: bytes, *, duration_ms: int | None = None) -> None:
        if not pcm16:
            return
        frame_ms = duration_ms if duration_ms is not None else self._duration_ms(pcm16)
        if not self._active:
            if self.detector.is_speech(pcm16):
                self._candidate_frames.append((pcm16, frame_ms))
                self._candidate_speech_ms += frame_ms
                if self._candidate_speech_ms >= self.min_speech_ms:
                    self._active = True
                    source_frames = [*self._pre_roll, *self._candidate_frames]
                    self._frames = [frame for frame, _ in source_frames]
                    self._utterance_ms = sum(frame_duration for _, frame_duration in source_frames)
                    self._speech_ms = self._candidate_speech_ms
                    self._silence_ms = 0
            else:
                self._candidate_speech_ms = 0
                self._candidate_frames.clear()
            if not self._active:
                self._append_pre_roll(pcm16, frame_ms)
            return

        self._frames.append(pcm16)
        self._utterance_ms += frame_ms
        if self.detector.is_speech(pcm16, continuing=True):
            self._speech_ms += frame_ms
            self._silence_ms = 0
        else:
            self._silence_ms += frame_ms
        if self._utterance_ms >= self.max_turn_ms:
            self.flush(force=True)
        elif self._silence_ms >= self.end_silence_ms:
            self.flush()

    def flush(self, *, force: bool = False) -> Path | None:
        if not self._active or not self._frames:
            return None
        if not force and self._speech_ms < self.min_utterance_ms:
            self._reset()
            return None
        self.output_dir.mkdir(parents=True, exist_ok=True)
        path = self.output_dir / f"utterance-{self._counter:06d}.wav"
        self._counter += 1
        with wave.open(str(path), "wb") as stream:
            stream.setnchannels(self.channels)
            stream.setsampwidth(2)
            stream.setframerate(self.sample_rate)
            stream.writeframes(b"".join(self._frames))
        self._reset()
        self.on_utterance(path)
        return path

    def discard(self) -> None:
        """Forget buffered capture without emitting a partial caller turn."""
        self._reset()

    def _append_pre_roll(self, pcm16: bytes, duration_ms: int) -> None:
        self._pre_roll.append((pcm16, duration_ms))
        total_ms = sum(frame_duration for _, frame_duration in self._pre_roll)
        while self._pre_roll and total_ms > self.pre_roll_ms:
            _, removed_ms = self._pre_roll.pop(0)
            total_ms -= removed_ms

    def _duration_ms(self, pcm16: bytes) -> int:
        bytes_per_second = self.sample_rate * self.channels * 2
        return max(1, round(len(pcm16) * 1000 / bytes_per_second))

    def _reset(self) -> None:
        self._frames.clear()
        self._pre_roll.clear()
        self._candidate_frames.clear()
        self._candidate_speech_ms = 0
        self._silence_ms = 0
        self._utterance_ms = 0
        self._speech_ms = 0
        self._active = False
