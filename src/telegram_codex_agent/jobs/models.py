from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class StringEnum(str, Enum):
    """Compatibility equivalent of enum.StrEnum for the supported 3.11+ runtime."""


class JobState(StringEnum):
    RECEIVED = "received"
    NORMALIZING = "normalizing"
    CONTEXT_RESOLUTION = "context_resolution"
    MEMORY_RETRIEVAL = "memory_retrieval"
    CLASSIFYING = "classifying"
    PLANNING = "planning"
    PLANNED = "planned"
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_EXTERNAL = "waiting_external"
    VERIFYING = "verifying"
    REPORTING = "reporting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"
    RECOVERING = "recovering"


class IntentType(StringEnum):
    CHAT = "chat"
    QUESTION = "question"
    CODE_TASK = "code_task"
    PROJECT_TASK = "project_task"
    SHELL_TASK = "shell_task"
    GIT_TASK = "git_task"
    DOCKER_TASK = "docker_task"
    SYSTEM_TASK = "system_task"
    BROWSER_TASK = "browser_task"
    FILE_ANALYSIS = "file_analysis"
    IMAGE_ANALYSIS = "image_analysis"
    VOICE_CHAT = "voice_chat"
    HYBRID_TASK = "hybrid_task"
    MEMORY_TASK = "memory_task"
    STATUS_TASK = "status_task"
    UNKNOWN = "unknown"


class ExecutionTarget(StringEnum):
    DIRECT_AJIL = "direct_ajil"
    CODEX = "codex"
    SHELL = "shell"
    GIT = "git"
    DOCKER = "docker"
    SYSTEMD = "systemd"
    PLAYWRIGHT = "playwright"
    FILE_TOOLS = "file_tools"
    MEMORY = "memory"
    HYBRID = "hybrid"
    NONE = "none"


class PlannedStep(BaseModel):
    sequence: int = Field(ge=1)
    name: str
    description: str
    executor: Literal[
        "ajil", "codex", "shell", "git", "docker", "systemd", "playwright", "filesystem", "memory"
    ]
    command_hint: str | None = None
    expected_output: str | None = None
    continue_on_failure: bool = False


class VerificationPlan(BaseModel):
    required: bool = False
    run_tests: bool = False
    run_lint: bool = False
    run_build: bool = False
    browser_check: bool = False
    capture_screenshot: bool = False
    capture_video: bool = False
    capture_trace: bool = False
    inspect_console_errors: bool = False
    inspect_http_errors: bool = False


class ExecutionPlan(BaseModel):
    intent: IntentType
    objective: str
    project_id: str | None = None
    requires_job: bool
    primary_executor: ExecutionTarget
    use_codex: bool = False
    use_memory: bool = True
    response_mode: Literal["text", "voice", "text_and_voice"] = "text"
    steps: list[PlannedStep] = Field(default_factory=list, max_length=12)
    verification: VerificationPlan = Field(default_factory=VerificationPlan)
    success_criteria: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)


class Attachment(BaseModel):
    kind: str
    telegram_file_id: str
    file_unique_id: str = ""
    local_path: str = ""
    mime_type: str = "application/octet-stream"
    size_bytes: int = 0
    sha256: str = ""
    caption: str = ""


class NormalizedInput(BaseModel):
    input_id: str = Field(default_factory=lambda: new_id("inp"))
    user_id: str
    chat_id: str
    conversation_id: str
    telegram_message_id: int | None = None
    kind: str
    text: str = ""
    attachments: list[Attachment] = Field(default_factory=list)
    reply_to: dict[str, object] | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
    received_at: datetime = Field(default_factory=utcnow)


class JobEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: new_id("evt"))
    job_id: str
    sequence: int
    event_type: str
    level: Literal["debug", "info", "warning", "error"] = "info"
    message: str
    data: dict[str, object] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)


class JobRecord(BaseModel):
    id: str = Field(default_factory=lambda: new_id("job"))
    conversation_id: str
    project_id: str | None = None
    parent_job_id: str | None = None
    request_message_id: str | None = None
    intent: IntentType = IntentType.UNKNOWN
    objective: str
    state: JobState = JobState.RECEIVED
    priority: int = 0
    attempt: int = 1
    max_attempts: int = 3
    execution_mode: str = "auto"
    planner_output: ExecutionPlan | None = None
    verification_policy: VerificationPlan = Field(default_factory=VerificationPlan)
    result_summary: str = ""
    error_code: str = ""
    error_message: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    queued_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    cancelled_at: datetime | None = None
    heartbeat_at: datetime | None = None
    worker_id: str = ""
    codex_thread_id: str | None = None
    codex_turn_id: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
