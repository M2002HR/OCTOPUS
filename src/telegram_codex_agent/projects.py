"""Explicit project registry; executors never infer a host path from user text."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from telegram_codex_agent.db.models import Project


class ProjectRegistry:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], projects: list[dict[str, Any]]) -> None:
        self.sessions = sessions
        self.projects = projects

    async def sync(self) -> None:
        """Upsert only configured project definitions; never discover arbitrary directories."""
        async with self.sessions() as session:
            for spec in self.projects:
                slug = str(spec.get("slug", "")).strip()
                root = str(spec.get("root_path", "")).strip()
                if not slug or not root:
                    continue
                project = await session.scalar(select(Project).where(Project.slug == slug))
                values = {
                    "name": str(spec.get("name") or slug),
                    "root_path": str(Path(root).resolve()),
                    "description": str(spec.get("description", "")),
                    "default_branch": str(spec.get("default_branch", "")),
                    "default_remote": str(spec.get("default_remote", "")),
                    "run_commands_json": list(spec.get("run_commands", [])),
                    "test_commands_json": list(spec.get("test_commands", [])),
                    "lint_commands_json": list(spec.get("lint_commands", [])),
                    "build_commands_json": list(spec.get("build_commands", [])),
                    "browser_url": str(spec.get("browser_url", "")),
                    "browser_config_json": dict(spec.get("browser_config", {})),
                    "environment_json": dict(spec.get("environment", {})),
                    "is_active": bool(spec.get("is_active", True)),
                }
                if project is None:
                    session.add(Project(slug=slug, **values))
                else:
                    for key, value in values.items():
                        setattr(project, key, value)
            await session.commit()
