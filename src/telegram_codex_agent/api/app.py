from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from telegram_codex_agent import __version__
from telegram_codex_agent.core.config import Settings

HealthCheck = Callable[[], Awaitable[dict[str, Any]]]


class HealthRegistry:
    def __init__(self, checks: dict[str, HealthCheck] | None = None) -> None:
        self.checks = checks or {}

    async def run(self) -> dict[str, Any]:
        results: dict[str, Any] = {}
        for name, check in self.checks.items():
            try:
                results[name] = await check()
            except Exception as exc:
                results[name] = {"ok": False, "error": type(exc).__name__}
        return results


class CancelResponse(BaseModel):
    job_id: str
    state: str


def create_app(settings: Settings, registry: HealthRegistry | None = None) -> FastAPI:
    app = FastAPI(
        title=settings.app.name,
        version=__version__,
        docs_url=None if settings.app.environment == "production" else "/docs",
    )
    health = registry or HealthRegistry()

    @app.get("/health")
    async def liveness() -> dict[str, object]:
        return {"ok": True, "service": settings.app.name, "version": __version__}

    @app.get("/ready")
    async def readiness() -> dict[str, object]:
        checks = await health.run()
        ok = all(value.get("ok", True) for value in checks.values())
        return {"ok": ok, "checks": checks}

    @app.get("/version")
    async def version() -> dict[str, str]:
        return {"version": __version__}

    @app.get("/config/redacted")
    async def config() -> dict[str, object]:
        return settings.redacted()

    @app.get("/projects")
    async def projects() -> list[dict[str, object]]:
        return settings.projects

    @app.get("/jobs/{job_id}")
    async def job(job_id: str) -> dict[str, str]:
        raise HTTPException(status_code=404, detail=f"job {job_id} was not found")

    @app.post("/jobs/{job_id}/cancel", response_model=CancelResponse)
    async def cancel(job_id: str) -> CancelResponse:
        return CancelResponse(job_id=job_id, state="cancel_requested")

    return app
