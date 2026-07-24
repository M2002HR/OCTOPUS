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


def _runtime_path(name: str, default: str, runtime: Path) -> Path:
    """Resolve relative runtime settings inside the configured runtime volume."""
    path = Path(os.getenv(name, default))
    return path if path.is_absolute() else runtime / path


@dataclass(frozen=True, slots=True)
class Settings:
    runtime_dir: Path
    audit_database_path: Path
    audit_jsonl_path: Path
    allowed_peer_ids: frozenset[int]
    test_peer_username: str
    inbound_enabled: bool
    inbound_usernames: tuple[str, ...]
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
    max_voice_reply_characters: int
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
    message_enabled: bool
    message_username: str
    message_default_response: str
    message_max_media_bytes: int
    message_media_library_dir: Path
    message_media_manifest: Path
    message_vision_enabled: bool
    message_stt_language: str | None
    vision_models: tuple[str, ...]
    vision_providers: tuple[str, ...]
    completion_calls_enabled: bool
    completion_call_redis_url: str
    completion_call_stream: str
    completion_call_consumer_group: str
    completion_call_retry_attempts: int
    completion_call_retry_delay_seconds: int
    completion_call_post_playback_seconds: int

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
            raise ConfigurationError("VOICE_AGENT_RECORDING_MODE must be off or transcript_only")
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

        legacy_inbound_username = os.getenv("VOICE_AGENT_INBOUND_USERNAME", "").strip()
        inbound_usernames = csv("VOICE_AGENT_INBOUND_USERNAMES") or (
            (legacy_inbound_username,) if legacy_inbound_username else ()
        )
        if len({username.casefold() for username in inbound_usernames}) != len(inbound_usernames):
            raise ConfigurationError("VOICE_AGENT_INBOUND_USERNAMES must not contain duplicates")

        language = os.getenv("VOICE_AGENT_LANGUAGE", "en").strip().casefold() or "en"
        if language != "en":
            raise ConfigurationError("VOICE_AGENT_LANGUAGE must be en")
        message_stt_language = (
            os.getenv("VOICE_AGENT_MESSAGE_STT_LANGUAGE", "en").strip().casefold() or "en"
        )
        if message_stt_language != "en":
            raise ConfigurationError("VOICE_AGENT_MESSAGE_STT_LANGUAGE must be en")

        return cls(
            runtime_dir=runtime,
            audit_database_path=database,
            audit_jsonl_path=events,
            allowed_peer_ids=_csv_int("VOICE_AGENT_ALLOWED_PEER_IDS"),
            test_peer_username=os.getenv("VOICE_AGENT_TEST_PEER_USERNAME", "").strip(),
            inbound_enabled=_bool("VOICE_AGENT_INBOUND_ENABLED", False),
            inbound_usernames=inbound_usernames,
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
            language=language,
            system_prompt=os.getenv(
                "VOICE_AGENT_SYSTEM_PROMPT",
                "Always reply in English. Reply naturally, directly, and concisely. "
                "Do not introduce yourself or mention implementation details.",
            ).strip(),
            max_voice_reply_characters=_int(
                "VOICE_AGENT_MAX_VOICE_REPLY_CHARS", 480, minimum=80
            ),
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
            edge_voice=os.getenv("EDGE_TTS_VOICE", "en-US-AndrewMultilingualNeural").strip(),
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
            message_enabled=_bool("VOICE_AGENT_MESSAGE_ENABLED", True),
            message_username=os.getenv(
                "VOICE_AGENT_MESSAGE_USERNAME",
                inbound_usernames[0] if inbound_usernames else "",
            ).strip(),
            message_default_response=os.getenv("VOICE_AGENT_MESSAGE_DEFAULT_RESPONSE", "text")
            .strip()
            .casefold(),
            message_max_media_bytes=_int(
                "VOICE_AGENT_MESSAGE_MAX_MEDIA_BYTES", 12 * 1024 * 1024, minimum=1
            ),
            message_media_library_dir=_runtime_path(
                "VOICE_AGENT_MESSAGE_MEDIA_LIBRARY_DIR", "media-library", runtime
            ),
            message_media_manifest=_runtime_path(
                "VOICE_AGENT_MESSAGE_MEDIA_MANIFEST", "media-library/manifest.json", runtime
            ),
            message_vision_enabled=_bool("VOICE_AGENT_MESSAGE_VISION_ENABLED", True),
            message_stt_language=message_stt_language,
            vision_models=csv("VOICE_AGENT_VISION_MODELS") or ("gemini/gemini-2.5-flash",),
            vision_providers=csv("VOICE_AGENT_VISION_PROVIDERS") or ("gemini",),
            completion_calls_enabled=_bool("CODEX_COMPLETION_CALLS_ENABLED", True),
            completion_call_redis_url=os.getenv(
                "CODEX_COMPLETION_CALL_REDIS_URL", ""
            ).strip(),
            completion_call_stream=os.getenv(
                "CODEX_COMPLETION_CALL_STREAM",
                "telegram_codex_agent.completion_calls",
            ).strip()
            or "telegram_codex_agent.completion_calls",
            completion_call_consumer_group=os.getenv(
                "CODEX_COMPLETION_CALL_CONSUMER_GROUP",
                "voice_agent.completion_calls",
            ).strip()
            or "voice_agent.completion_calls",
            completion_call_retry_attempts=_int(
                "CODEX_COMPLETION_CALL_RETRY_ATTEMPTS", 3, minimum=1
            ),
            completion_call_retry_delay_seconds=_int(
                "CODEX_COMPLETION_CALL_RETRY_DELAY_SEC", 10, minimum=1
            ),
            completion_call_post_playback_seconds=_int(
                "CODEX_COMPLETION_CALL_POST_PLAYBACK_SEC", 2, minimum=0
            ),
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

    def validate_inbound_service(self) -> None:
        if not self.inbound_enabled:
            raise ConfigurationError("VOICE_AGENT_INBOUND_ENABLED must be true for serve mode")
        if not self.inbound_usernames:
            raise ConfigurationError("VOICE_AGENT_INBOUND_USERNAMES is required for serve mode")
        if self.message_default_response not in {"voice", "text"}:
            raise ConfigurationError("VOICE_AGENT_MESSAGE_DEFAULT_RESPONSE must be voice or text")
        if self.message_enabled and not self.message_username:
            raise ConfigurationError(
                "VOICE_AGENT_MESSAGE_USERNAME is required when message service is enabled"
            )
        if self.completion_calls_enabled and not self.completion_call_redis_url:
            raise ConfigurationError(
                "CODEX_COMPLETION_CALL_REDIS_URL is required when completion calls are enabled"
            )
