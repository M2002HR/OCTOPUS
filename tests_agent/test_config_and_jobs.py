from __future__ import annotations

from pathlib import Path

import pytest

from telegram_codex_agent.core.config import load_settings
from telegram_codex_agent.jobs.models import JobRecord, JobState
from telegram_codex_agent.jobs.state_machine import JobStateMachine


def test_root_config_loads_from_single_yaml(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    settings = load_settings(Path("config/agent.yaml"), Path(".env.example"))
    assert settings.app.environment == "test"
    assert settings.voice.legacy_telethon_service is True
    assert settings.redis.url.endswith("/1")
    assert settings.codex.model == "gpt-5.6-terra"
    assert settings.app.language == "en"
    assert settings.voice.stt_language == "en"
    assert settings.workspace.root == Path("/home/mhr/Code")
    assert settings.workspace.discover_git_projects is True


def test_job_state_machine_rejects_skipped_transitions() -> None:
    machine = JobStateMachine(JobRecord(conversation_id="conversation", objective="test"))
    with pytest.raises(ValueError, match="invalid job transition"):
        machine.transition(JobState.RUNNING, "cannot skip normalizing")


def test_job_state_machine_emits_events() -> None:
    machine = JobStateMachine(JobRecord(conversation_id="conversation", objective="test"))
    machine.transition(JobState.NORMALIZING, "normalize")
    event = machine.transition(JobState.CONTEXT_RESOLUTION, "resolve context")
    assert event.sequence == 2
    assert event.data["from"] == JobState.NORMALIZING
