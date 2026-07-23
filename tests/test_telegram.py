from pathlib import Path

import pytest

from voice_agent.adapters.telegram import TelethonSession
from voice_agent.config import ConfigurationError, Settings


def test_telegram_settings_must_be_complete(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("TELEGRAM_API_ID", raising=False)
    monkeypatch.delenv("TELEGRAM_API_HASH", raising=False)
    monkeypatch.delenv("TELEGRAM_STRING_SESSION", raising=False)
    settings = Settings.load(tmp_path / "missing.env")
    with pytest.raises(ConfigurationError):
        TelethonSession(settings)
