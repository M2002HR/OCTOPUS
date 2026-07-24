"""Explicit project registry; executors never infer a host path from user text."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from telegram_codex_agent.core.config import WorkspaceConfig
from telegram_codex_agent.db.models import Project


class ProjectRegistry:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        projects: list[dict[str, Any]],
        workspace: WorkspaceConfig | None = None,
    ) -> None:
        self.sessions = sessions
        self.projects = projects
        self.workspace = workspace

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
            if self.workspace and self.workspace.discover_git_projects:
                root = self.workspace.root.resolve()
                if root.is_dir():
                    for candidate in sorted(root.iterdir(), key=lambda path: path.name.casefold()):
                        if not candidate.is_dir() or not (candidate / ".git").exists():
                            continue
                        slug = re.sub(r"[^a-z0-9_-]+", "-", candidate.name.casefold()).strip("-")
                        if not slug:
                            continue
                        project = await session.scalar(select(Project).where(Project.slug == slug))
                        if project is None:
                            session.add(
                                Project(
                                    slug=slug,
                                    name=candidate.name,
                                    root_path=str(candidate.resolve()),
                                    description="Discovered Git workspace",
                                    is_active=True,
                                )
                            )
            await session.commit()
