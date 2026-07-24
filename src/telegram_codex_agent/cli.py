from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from pathlib import Path

import typer
import uvicorn

from telegram_codex_agent.api.app import create_app
from telegram_codex_agent.core.config import load_settings
from telegram_codex_agent.integrations.ajil import AjilClient
from telegram_codex_agent.runtime import health_registry

app = typer.Typer(no_args_is_help=True)
config_app = typer.Typer(no_args_is_help=True)
codex_app = typer.Typer(no_args_is_help=True)
app.add_typer(config_app, name="config")
app.add_typer(codex_app, name="codex")


def _settings(path: Path | None = None):
    return load_settings(path)


@config_app.command("validate")
def config_validate(path: Path | None = typer.Option(None, "--config")) -> None:
    settings = _settings(path)
    typer.echo(f"valid: {settings.config_path}")


@config_app.command("dump")
def config_dump(
    redact: bool = typer.Option(True, "--redact/--no-redact"),
    path: Path | None = typer.Option(None, "--config"),
) -> None:
    settings = _settings(path)
    typer.echo(
        json.dumps(
            settings.redacted() if redact else settings.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )


@app.command("api")
def api(path: Path | None = typer.Option(None, "--config")) -> None:
    settings = _settings(path)
    uvicorn.run(
        create_app(settings, health_registry(settings)),
        host=settings.app.api_host,
        port=settings.app.api_port,
    )


@app.command("ajil-smoke")
def ajil_smoke(path: Path | None = typer.Option(None, "--config")) -> None:
    async def run() -> None:
        client = AjilClient(_settings(path).ajil)
        try:
            typer.echo(json.dumps(await client.health(), ensure_ascii=False))
        finally:
            await client.aclose()

    asyncio.run(run())


@codex_app.command("status")
def codex_status(path: Path | None = typer.Option(None, "--config")) -> None:
    settings = _settings(path)
    binary = shutil.which(settings.codex.binary)
    version = "unavailable"
    if binary:
        version = subprocess.run(
            [binary, "--version"], text=True, capture_output=True, check=False
        ).stdout.strip()
    typer.echo(
        json.dumps(
            {
                "binary": binary,
                "version": version,
                "approval_policy": settings.codex.approval_policy,
                "sandbox_mode": settings.codex.sandbox_mode,
            },
            indent=2,
        )
    )


def main() -> None:
    app()


if __name__ == "__main__":
    main()
