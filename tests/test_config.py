from pathlib import Path

import pytest

from voice_agent.config import ConfigurationError, Settings


def test_settings_validates_recording_mode(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VOICE_AGENT_RECORDING_MODE", "everything")
    with pytest.raises(ConfigurationError):
        Settings.load(tmp_path / "missing.env")


def test_settings_rejects_unimplemented_audio_retention(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("VOICE_AGENT_RECORDING_MODE", "encrypted_audio")
    with pytest.raises(ConfigurationError):
        Settings.load(tmp_path / "missing.env")


def test_settings_reads_allowlist(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VOICE_AGENT_ALLOWED_PEER_IDS", "11, 22")
    settings = Settings.load(tmp_path / "missing.env")
    assert settings.allowed_peer_ids == frozenset({11, 22})


def test_settings_rejects_too_short_call_timeout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("VOICE_AGENT_CALL_TIMEOUT_SEC", "9")
    with pytest.raises(ConfigurationError):
        Settings.load(tmp_path / "missing.env")


def test_settings_rejects_invalid_vad_hysteresis(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("VOICE_AGENT_VAD_START_RMS", "100")
    monkeypatch.setenv("VOICE_AGENT_VAD_CONTINUE_RMS", "101")
    with pytest.raises(ConfigurationError, match="CONTINUE_RMS"):
        Settings.load(tmp_path / "missing.env")
