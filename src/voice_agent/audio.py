from __future__ import annotations

from dataclasses import dataclass
from math import isqrt
from struct import iter_unpack


@dataclass(frozen=True, slots=True)
class VoiceActivityDetector:
    """Deterministic PCM16 energy gate with hysteresis for real-time call audio."""

    start_threshold_rms: int = 350
    continue_threshold_rms: int = 240

    def rms(self, pcm16: bytes) -> int:
        if not pcm16:
            return 0
        samples = [sample[0] for sample in iter_unpack("<h", pcm16[: len(pcm16) - len(pcm16) % 2])]
        if not samples:
            return 0
        return isqrt(sum(sample * sample for sample in samples) // len(samples))

    def is_speech(self, pcm16: bytes, *, continuing: bool = False) -> bool:
        threshold = self.continue_threshold_rms if continuing else self.start_threshold_rms
        return self.rms(pcm16) >= threshold
