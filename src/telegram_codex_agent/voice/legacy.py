from __future__ import annotations

from dataclasses import dataclass

from telegram_codex_agent.core.config import Settings


@dataclass(frozen=True, slots=True)
class LegacyVoiceStatus:
    enabled: bool
    command: tuple[str, ...]
    reason: str


def legacy_voice_status(settings: Settings) -> LegacyVoiceStatus:
    """Expose the already-tested Telethon service without duplicating its credentials or media stack."""
    if not settings.voice.legacy_telethon_service:
        return LegacyVoiceStatus(False, (), "disabled in config")
    return LegacyVoiceStatus(
        True, ("telegram-voice-agent", "serve"), "managed by the legacy-compatible Compose profile"
    )
