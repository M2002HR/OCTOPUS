"""One YAML policy file plus one root environment file, with explicit precedence."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Literal

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError

from telegram_codex_agent.core.errors import ConfigurationError

_INTERPOLATION = re.compile(r"\$\{([A-Z0-9_]+)(?::-(.*?))?\}")


def _expand(value: object) -> object:
    if isinstance(value, str):
        return _INTERPOLATION.sub(
            # An explicitly empty value in .env means "use the policy default".
            # This makes checked-in examples safe and avoids silently selecting a
            # provider's moving default model.
            lambda match: os.getenv(match.group(1)) or match.group(2) or "",
            value,
        )
    if isinstance(value, list):
        return [_expand(item) for item in value]
    if isinstance(value, dict):
        return {key: _expand(item) for key, item in value.items()}
    return value


class AppConfig(BaseModel):
    name: str = "telegram-codex-agent"
    environment: str = "development"
    timezone: str = "Asia/Tehran"
    language: str = "fa"
    api_host: str = "127.0.0.1"
    api_port: int = 8090
    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "json"


class TelegramConfig(BaseModel):
    transport: Literal["polling", "webhook"] = "polling"
    bot_token_env: str = "TELEGRAM_BOT_TOKEN"
    allowed_user_ids: list[int] = Field(default_factory=list)
    allowed_chat_ids: list[int] = Field(default_factory=list)
    webhook_public_url: str = ""
    webhook_secret_env: str = "TELEGRAM_WEBHOOK_SECRET"
    default_parse_mode: Literal["HTML", "MarkdownV2"] = "HTML"
    progress_edit_interval_seconds: float = 3.0
    max_message_length: int = 3800
    bot_proxy_url_env: str = "TELEGRAM_BOT_PROXY_URL"

    @property
    def bot_token(self) -> str:
        return os.getenv(self.bot_token_env, "").strip()

    @property
    def bot_proxy_url(self) -> str:
        return os.getenv(self.bot_proxy_url_env, "").strip()


class DatabaseConfig(BaseModel):
    url: str
    echo: bool = False
    pool_size: int = 8


class RedisConfig(BaseModel):
    url: str
    stream: str = "telegram_codex_agent.jobs"
    consumer_group: str = "telegram_codex_agent.workers"


class PlannerConfig(BaseModel):
    model: str = ""
    temperature: float = 0.0
    max_retries: int = 2
    reject_local_fallback: bool = True


class AjilConfig(BaseModel):
    base_url: str
    auth_token_env: str = "UAG_AUTH_TOKEN"
    auth_header_name: str = "x-api-token"
    timeout_seconds: float = 45.0
    planner: PlannerConfig = Field(default_factory=PlannerConfig)

    @property
    def auth_token(self) -> str:
        return os.getenv(self.auth_token_env, "").strip()


class CodexConfig(BaseModel):
    binary: str = "codex"
    model: str = "gpt-5.6-terra"
    reasoning_effort: str = "high"
    approval_policy: Literal["never", "on-request", "untrusted"] = "never"
    sandbox_mode: Literal["read-only", "workspace-write", "danger-full-access"] = (
        "danger-full-access"
    )
    network_access: bool = True
    startup_timeout_seconds: float = 30.0


class JobsConfig(BaseModel):
    worker_count: int = 1
    lease_seconds: int = 30
    heartbeat_seconds: int = 5
    timeout_seconds: int = 3600
    step_timeout_seconds: int = 900
    output_byte_cap: int = 1_048_576
    recovery_policy: Literal["resume_or_fail", "fail"] = "resume_or_fail"


class ArtifactConfig(BaseModel):
    root: Path = Path("data/artifacts")
    retention_days: int = 30
    telegram_direct_upload_max_bytes: int = 47_185_920


class VoiceConfig(BaseModel):
    enabled: bool = True
    telegram_voice_replies_default: bool = False
    stt_language: str = "fa"
    ffmpeg_binary: str = "ffmpeg"
    legacy_telethon_service: bool = True


class BrowserConfig(BaseModel):
    default_mode: Literal["isolated_headless", "isolated_headed", "cdp"] = "isolated_headless"
    headless: bool = True
    cdp_endpoint: str = "http://127.0.0.1:9222"


class MemoryConfig(BaseModel):
    enabled: bool = True
    summarize_after_messages: int = 30
    retrieval_limit: int = 8


class WorkspaceConfig(BaseModel):
    root: Path = Path("/home/mhr/Code")
    discover_git_projects: bool = True
    max_depth: int = 1


class Settings(BaseModel):
    app: AppConfig = Field(default_factory=AppConfig)
    telegram: TelegramConfig
    database: DatabaseConfig
    redis: RedisConfig
    ajil: AjilConfig
    codex: CodexConfig = Field(default_factory=CodexConfig)
    jobs: JobsConfig = Field(default_factory=JobsConfig)
    artifacts: ArtifactConfig = Field(default_factory=ArtifactConfig)
    voice: VoiceConfig = Field(default_factory=VoiceConfig)
    browser: BrowserConfig = Field(default_factory=BrowserConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    workspace: WorkspaceConfig = Field(default_factory=WorkspaceConfig)
    projects: list[dict[str, Any]] = Field(default_factory=list)
    config_path: Path = Path("config/agent.yaml")

    def redacted(self) -> dict[str, Any]:
        data = self.model_dump(mode="json")
        data["telegram"]["bot_token"] = "<configured>" if self.telegram.bot_token else "<missing>"
        data["ajil"]["auth_token"] = "<configured>" if self.ajil.auth_token else "<missing>"
        return data


def load_settings(
    config_path: Path | str | None = None, env_file: Path | str | None = None
) -> Settings:
    root = Path.cwd()
    load_dotenv(Path(env_file) if env_file else root / ".env", override=False)
    path = Path(config_path or os.getenv("CONFIG_PATH", "config/agent.yaml"))
    if not path.is_absolute():
        path = root / path
    if not path.exists():
        raise ConfigurationError(f"configuration file does not exist: {path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        settings = Settings.model_validate(_expand(raw) | {"config_path": path})
    except (OSError, yaml.YAMLError, ValidationError) as exc:
        raise ConfigurationError(f"invalid configuration: {exc}") from exc
    if settings.telegram.transport == "webhook" and not settings.telegram.webhook_public_url:
        raise ConfigurationError("telegram.webhook_public_url is required for webhook transport")
    return settings
