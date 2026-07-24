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


def test_settings_reads_multiple_inbound_usernames(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("VOICE_AGENT_INBOUND_USERNAMES", "primary_caller, test_caller")
    settings = Settings.load(tmp_path / "missing.env")
    assert settings.inbound_usernames == ("primary_caller", "test_caller")


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


def test_settings_rejects_non_english_speech_configuration(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("VOICE_AGENT_LANGUAGE", "fr")
    with pytest.raises(ConfigurationError, match="must be en"):
        Settings.load(tmp_path / "missing.env")


def test_settings_requires_explicit_inbound_enablement(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("VOICE_AGENT_INBOUND_ENABLED", "false")
    monkeypatch.setenv("VOICE_AGENT_INBOUND_USERNAMES", "we_are_waiting_for_him")
    settings = Settings.load(tmp_path / "missing.env")
    with pytest.raises(ConfigurationError, match="INBOUND_ENABLED"):
        settings.validate_inbound_service()


def test_settings_requires_inbound_usernames(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("VOICE_AGENT_INBOUND_ENABLED", "true")
    monkeypatch.setenv("VOICE_AGENT_INBOUND_USERNAME", "")
    monkeypatch.setenv("VOICE_AGENT_INBOUND_USERNAMES", "")
    settings = Settings.load(tmp_path / "missing.env")
    with pytest.raises(ConfigurationError, match="INBOUND_USERNAMES"):
        settings.validate_inbound_service()


def test_settings_requires_message_username_when_enabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("VOICE_AGENT_INBOUND_ENABLED", "true")
    monkeypatch.setenv("VOICE_AGENT_INBOUND_USERNAMES", "we_are_waiting_for_him")
    monkeypatch.setenv("VOICE_AGENT_MESSAGE_ENABLED", "true")
    monkeypatch.setenv("VOICE_AGENT_MESSAGE_USERNAME", "")
    settings = Settings.load(tmp_path / "missing.env")

    with pytest.raises(ConfigurationError, match="MESSAGE_USERNAME"):
        settings.validate_inbound_service()


def test_message_library_relative_paths_are_inside_runtime_volume(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runtime = tmp_path / "runtime"
    monkeypatch.setenv("RUNTIME_DIR", str(runtime))
    monkeypatch.setenv("VOICE_AGENT_MESSAGE_MEDIA_LIBRARY_DIR", "approved-assets")
    monkeypatch.setenv("VOICE_AGENT_MESSAGE_MEDIA_MANIFEST", "approved-assets/index.json")

    settings = Settings.load(tmp_path / "missing.env")

    assert settings.message_media_library_dir == runtime / "approved-assets"
    assert settings.message_media_manifest == runtime / "approved-assets" / "index.json"
