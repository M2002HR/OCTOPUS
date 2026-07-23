from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


class ConfigurationError(ValueError):
    """Raised before network work when a required setting is missing or invalid."""


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().casefold() in {"1", "true", "yes", "on"}


def _int(name: str, default: int, *, minimum: int | None = None) -> int:
    raw = os.getenv(name)
    value = default if raw is None or not raw.strip() else int(raw)
    if minimum is not None and value < minimum:
        raise ConfigurationError(f"{name} must be at least {minimum}")
    return value


def _csv_int(name: str) -> frozenset[int]:
    raw = os.getenv(name, "")
    try:
        return frozenset(int(value.strip()) for value in raw.split(",") if value.strip())
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a comma-separated list of numeric IDs") from exc


@dataclass(frozen=True, slots=True)
class Settings:
    runtime_dir: Path
    audit_database_path: Path
    audit_jsonl_path: Path
    allowed_peer_ids: frozenset[int]
    test_peer_username: str
    require_disclosure: bool
    recording_mode: str
    max_turn_seconds: int
    call_timeout_seconds: int
    vad_start_rms: int
    vad_continue_rms: int
    vad_start_ms: int
    vad_end_silence_ms: int
    vad_min_utterance_ms: int
    vad_pre_roll_ms: int
    audio_sample_rate: int
    audio_channels: int
    language: str
    system_prompt: str
    max_history_messages: int
    uag_base_url: str
    uag_chat_endpoint: str
    uag_transcriptions_endpoint: str
    uag_auth_token: str
    uag_auth_header_name: str
    uag_timeout_seconds: int
    chat_models: tuple[str, ...]
    chat_providers: tuple[str, ...]
    transcription_provider: str
    transcription_models: tuple[str, ...]
    edge_voice: str
    edge_rate: str
    ffmpeg_bin: str
    telegram_api_id: int
    telegram_api_hash: str
    telegram_string_session: str
    telegram_proxy_enabled: bool
    telegram_proxy_type: str
    telegram_proxy_host: str
    telegram_proxy_port: int
    telegram_proxy_username: str
    telegram_proxy_password: str
    telegram_proxy_rdns: bool

    @classmethod
    def load(cls, env_file: Path | None = None) -> Settings:
        if env_file is not None:
            load_dotenv(env_file, override=False)
        else:
            load_dotenv(Path.cwd() / ".env", override=False)
        runtime = Path(os.getenv("RUNTIME_DIR", "runtime"))
        database = Path(os.getenv("AUDIT_DATABASE_PATH", str(runtime / "voice_agent.sqlite3")))
        events = Path(os.getenv("AUDIT_JSONL_PATH", str(runtime / "events.jsonl")))
        recording_mode = os.getenv("VOICE_AGENT_RECORDING_MODE", "transcript_only").strip()
        if recording_mode not in {"off", "transcript_only"}:
            raise ConfigurationError(
                "VOICE_AGENT_RECORDING_MODE must be off or transcript_only"
            )
        vad_start_rms = _int("VOICE_AGENT_VAD_START_RMS", 350, minimum=1)
        vad_continue_rms = _int("VOICE_AGENT_VAD_CONTINUE_RMS", 240, minimum=1)
        if vad_continue_rms > vad_start_rms:
            raise ConfigurationError("VOICE_AGENT_VAD_CONTINUE_RMS must not exceed START_RMS")
        audio_sample_rate = _int("VOICE_AGENT_AUDIO_SAMPLE_RATE", 48_000, minimum=8_000)
        audio_channels = _int("VOICE_AGENT_AUDIO_CHANNELS", 1, minimum=1)
        if audio_channels > 2:
            raise ConfigurationError("VOICE_AGENT_AUDIO_CHANNELS must be 1 or 2")

        def csv(name: str) -> tuple[str, ...]:
            return tuple(part.strip() for part in os.getenv(name, "").split(",") if part.strip())

        return cls(
            runtime_dir=runtime,
            audit_database_path=database,
            audit_jsonl_path=events,
            allowed_peer_ids=_csv_int("VOICE_AGENT_ALLOWED_PEER_IDS"),
            test_peer_username=os.getenv("VOICE_AGENT_TEST_PEER_USERNAME", "").strip(),
            require_disclosure=_bool("VOICE_AGENT_REQUIRE_DISCLOSURE", True),
            recording_mode=recording_mode,
            max_turn_seconds=_int("VOICE_AGENT_MAX_TURN_SECONDS", 45, minimum=1),
            call_timeout_seconds=_int("VOICE_AGENT_CALL_TIMEOUT_SEC", 120, minimum=10),
            vad_start_rms=vad_start_rms,
            vad_continue_rms=vad_continue_rms,
            vad_start_ms=_int("VOICE_AGENT_VAD_START_MS", 80, minimum=20),
            vad_end_silence_ms=_int(
                "VOICE_AGENT_VAD_END_SILENCE_MS",
                _int("VOICE_AGENT_SILENCE_MS", 600, minimum=100),
                minimum=100,
            ),
            vad_min_utterance_ms=_int("VOICE_AGENT_VAD_MIN_UTTERANCE_MS", 250, minimum=20),
            vad_pre_roll_ms=_int("VOICE_AGENT_VAD_PRE_ROLL_MS", 200, minimum=0),
            audio_sample_rate=audio_sample_rate,
            audio_channels=audio_channels,
            language=os.getenv("VOICE_AGENT_LANGUAGE", "fa").strip() or "fa",
            system_prompt=os.getenv(
                "VOICE_AGENT_SYSTEM_PROMPT", "You are a helpful voice assistant."
            ).strip(),
            max_history_messages=_int("VOICE_AGENT_MAX_HISTORY_MESSAGES", 12, minimum=1),
            uag_base_url=os.getenv("UAG_BASE_URL", "http://127.0.0.1:8080").rstrip("/"),
            uag_chat_endpoint=os.getenv("UAG_CHAT_ENDPOINT", "/v1/chat/completions"),
            uag_transcriptions_endpoint=os.getenv(
                "UAG_AUDIO_TRANSCRIPTIONS_ENDPOINT", "/v1/audio/transcriptions"
            ),
            uag_auth_token=os.getenv("UAG_AUTH_TOKEN", "").strip(),
            uag_auth_header_name=os.getenv("UAG_AUTH_HEADER_NAME", "x-api-token").strip()
            or "x-api-token",
            uag_timeout_seconds=_int("UAG_TIMEOUT_SEC", 45, minimum=1),
            chat_models=csv("AI_CHAT_MODELS"),
            chat_providers=csv("AI_CHAT_PROVIDERS"),
            transcription_provider=os.getenv("AI_TRANSCRIPTION_PROVIDER", "").strip(),
            transcription_models=csv("AI_TRANSCRIPTION_MODELS"),
            edge_voice=os.getenv("EDGE_TTS_VOICE", "fa-IR-DilaraNeural").strip(),
            edge_rate=os.getenv("EDGE_TTS_RATE", "+0%").strip(),
            ffmpeg_bin=os.getenv("FFMPEG_BIN", "ffmpeg").strip(),
            telegram_api_id=_int("TELEGRAM_API_ID", 0, minimum=0),
            telegram_api_hash=os.getenv("TELEGRAM_API_HASH", "").strip(),
            telegram_string_session=os.getenv("TELEGRAM_STRING_SESSION", "").strip(),
            telegram_proxy_enabled=_bool("TELEGRAM_PROXY_ENABLED", False),
            telegram_proxy_type=os.getenv("TELEGRAM_PROXY_TYPE", "socks5").strip(),
            telegram_proxy_host=os.getenv("TELEGRAM_PROXY_HOST", "").strip(),
            telegram_proxy_port=_int("TELEGRAM_PROXY_PORT", 0, minimum=0),
            telegram_proxy_username=os.getenv("TELEGRAM_PROXY_USERNAME", "").strip(),
            telegram_proxy_password=os.getenv("TELEGRAM_PROXY_PASSWORD", "").strip(),
            telegram_proxy_rdns=_bool("TELEGRAM_PROXY_RDNS", True),
        )

    def validate_telegram(self) -> None:
        if (
            self.telegram_api_id <= 0
            or not self.telegram_api_hash
            or not self.telegram_string_session
        ):
            raise ConfigurationError(
                "TELEGRAM_API_ID, TELEGRAM_API_HASH, and TELEGRAM_STRING_SESSION are required"
            )
        if self.telegram_proxy_enabled and (
            not self.telegram_proxy_host or self.telegram_proxy_port <= 0
        ):
            raise ConfigurationError("enabled Telegram proxy requires host and port")
