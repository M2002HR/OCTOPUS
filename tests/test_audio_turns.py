from pathlib import Path

from voice_agent.audio import VoiceActivityDetector
from voice_agent.audio_turns import PcmTurnAssembler


def test_pcm_turn_assembler_writes_an_utterance_after_silence(tmp_path: Path) -> None:
    utterances: list[Path] = []
    assembler = PcmTurnAssembler(
        output_dir=tmp_path,
        on_utterance=utterances.append,
        end_silence_ms=40,
        min_speech_ms=20,
        min_utterance_ms=20,
        pre_roll_ms=0,
        detector=VoiceActivityDetector(start_threshold_rms=1, continue_threshold_rms=1),
    )
    assembler.feed((100).to_bytes(2, "little", signed=True) * 100, duration_ms=20)
    assembler.feed(b"\0\0" * 100, duration_ms=20)
    assembler.feed(b"\0\0" * 100, duration_ms=20)
    assert len(utterances) == 1
    assert utterances[0].read_bytes().startswith(b"RIFF")


def test_pcm_turn_assembler_enforces_maximum_turn_length(tmp_path: Path) -> None:
    utterances: list[Path] = []
    assembler = PcmTurnAssembler(
        output_dir=tmp_path,
        max_turn_ms=40,
        on_utterance=utterances.append,
        min_speech_ms=20,
        min_utterance_ms=20,
        pre_roll_ms=0,
        detector=VoiceActivityDetector(start_threshold_rms=1, continue_threshold_rms=1),
    )
    speech = (100).to_bytes(2, "little", signed=True) * 100
    assembler.feed(speech, duration_ms=20)
    assembler.feed(speech, duration_ms=20)
    assert len(utterances) == 1


def test_pcm_turn_assembler_keeps_pre_roll_and_ignores_short_noise(tmp_path: Path) -> None:
    utterances: list[Path] = []
    assembler = PcmTurnAssembler(
        output_dir=tmp_path,
        on_utterance=utterances.append,
        end_silence_ms=40,
        min_speech_ms=40,
        min_utterance_ms=40,
        pre_roll_ms=20,
        detector=VoiceActivityDetector(start_threshold_rms=10, continue_threshold_rms=5),
    )
    silence = b"\0\0" * 100
    speech = (100).to_bytes(2, "little", signed=True) * 100
    assembler.feed(silence, duration_ms=20)
    assembler.feed(speech, duration_ms=20)
    assembler.feed(silence, duration_ms=20)  # a short burst must not start a turn
    assembler.feed(speech, duration_ms=20)
    assembler.feed(speech, duration_ms=20)
    assembler.feed(silence, duration_ms=20)
    assembler.feed(silence, duration_ms=20)
    assert len(utterances) == 1
    assert utterances[0].read_bytes().startswith(b"RIFF")


def test_pcm_turn_assembler_uses_pcm_length_when_frame_duration_is_omitted(tmp_path: Path) -> None:
    utterances: list[Path] = []
    assembler = PcmTurnAssembler(
        output_dir=tmp_path,
        on_utterance=utterances.append,
        min_speech_ms=10,
        min_utterance_ms=10,
        end_silence_ms=10,
        pre_roll_ms=0,
        detector=VoiceActivityDetector(start_threshold_rms=1, continue_threshold_rms=1),
    )
    # 480 mono PCM16 samples equal 10 ms at 48 kHz.
    assembler.feed((100).to_bytes(2, "little", signed=True) * 480)
    assembler.feed(b"\0\0" * 480)
    assert len(utterances) == 1
