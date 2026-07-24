from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func


def id_column() -> Mapped[str]:
    return mapped_column(String(40), primary_key=True, default=lambda: uuid4().hex)


class Base(DeclarativeBase):
    pass


class Timestamped:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class User(Base, Timestamped):
    __tablename__ = "users"
    id = id_column()
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(255))
    first_name: Mapped[str] = mapped_column(String(255), default="")
    last_name: Mapped[str] = mapped_column(String(255), default="")
    language_code: Mapped[str] = mapped_column(String(16), default="fa")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    preferences_json: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)


class Chat(Base, Timestamped):
    __tablename__ = "chats"
    id = id_column()
    telegram_chat_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    chat_type: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(255), default="")


class Project(Base, Timestamped):
    __tablename__ = "projects"
    id = id_column()
    slug: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    root_path: Mapped[str] = mapped_column(Text, unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    default_branch: Mapped[str] = mapped_column(String(255), default="")
    default_remote: Mapped[str] = mapped_column(String(1024), default="")
    run_commands_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    test_commands_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    lint_commands_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    build_commands_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    browser_url: Mapped[str] = mapped_column(String(2048), default="")
    browser_config_json: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    environment_json: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Conversation(Base, Timestamped):
    __tablename__ = "conversations"
    id = id_column()
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    chat_id: Mapped[str] = mapped_column(ForeignKey("chats.id"), index=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(32), default="active")
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    summary: Mapped[str] = mapped_column(Text, default="")
    metadata_json: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)


class Message(Base):
    __tablename__ = "messages"
    id = id_column()
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    role: Mapped[str] = mapped_column(String(32))
    content_type: Mapped[str] = mapped_column(String(32))
    text: Mapped[str] = mapped_column(Text, default="")
    file_path: Mapped[str | None] = mapped_column(Text)
    mime_type: Mapped[str | None] = mapped_column(String(255))
    metadata_json: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    embedding: Mapped[list[float] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Job(Base):
    __tablename__ = "jobs"
    id = id_column()
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    parent_job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.id"), nullable=True)
    request_message_id: Mapped[str | None] = mapped_column(ForeignKey("messages.id"), nullable=True)
    intent: Mapped[str] = mapped_column(String(64), default="unknown")
    objective: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(32), default="received", index=True)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    execution_mode: Mapped[str] = mapped_column(String(32), default="auto")
    planner_output_json: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    verification_policy_json: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    result_summary: Mapped[str] = mapped_column(Text, default="")
    error_code: Mapped[str] = mapped_column(String(128), default="")
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    worker_id: Mapped[str] = mapped_column(String(255), default="")
    codex_thread_id: Mapped[str | None] = mapped_column(String(255))
    codex_turn_id: Mapped[str | None] = mapped_column(String(255))
    metadata_json: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)


class JobStep(Base):
    __tablename__ = "job_steps"
    id = id_column()
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    tool_name: Mapped[str | None] = mapped_column(String(128))
    input_json: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    output_json: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    state: Mapped[str] = mapped_column(String(32), default="pending")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str] = mapped_column(Text, default="")
    __table_args__ = (Index("ix_job_steps_job_sequence", "job_id", "sequence", unique=True),)


class JobEventRow(Base):
    __tablename__ = "job_events"
    id = id_column()
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(128))
    level: Mapped[str] = mapped_column(String(16), default="info")
    message: Mapped[str] = mapped_column(Text)
    data_json: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (Index("ix_job_events_job_sequence", "job_id", "sequence", unique=True),)


class CodexThread(Base, Timestamped):
    __tablename__ = "codex_threads"
    id = id_column()
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    codex_thread_id: Mapped[str] = mapped_column(String(255), unique=True)
    status: Mapped[str] = mapped_column(String(32), default="active")
    cwd: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(255), default="")
    approval_policy: Mapped[str] = mapped_column(String(64), default="never")
    sandbox_mode: Mapped[str] = mapped_column(String(64), default="danger-full-access")
    last_turn_id: Mapped[str] = mapped_column(String(255), default="")
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)


class Artifact(Base):
    __tablename__ = "artifacts"
    id = id_column()
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(512))
    path: Mapped[str] = mapped_column(Text)
    mime_type: Mapped[str] = mapped_column(String(255))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    telegram_file_id: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)


class MemoryRecord(Base, Timestamped):
    __tablename__ = "memory_records"
    id = id_column()
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    conversation_id: Mapped[str | None] = mapped_column(
        ForeignKey("conversations.id"), nullable=True
    )
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    memory_type: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text)
    source_message_ids_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    importance: Mapped[int] = mapped_column(Integer, default=50)
    embedding: Mapped[list[float] | None] = mapped_column(JSON)
    last_accessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)


class WorkerLease(Base):
    __tablename__ = "worker_leases"
    id = id_column()
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), unique=True)
    worker_id: Mapped[str] = mapped_column(String(255))
    acquired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    heartbeat_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class ApprovalRecord(Base):
    __tablename__ = "approval_records"
    id = id_column()
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    codex_request_id: Mapped[str] = mapped_column(String(255))
    approval_type: Mapped[str] = mapped_column(String(128))
    request_json: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    decision: Mapped[str] = mapped_column(String(64))
    scope: Mapped[str] = mapped_column(String(64), default="session")
    auto_approved: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
