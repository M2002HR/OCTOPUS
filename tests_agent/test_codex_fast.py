import asyncio
from pathlib import Path
from typing import Any

from telegram_codex_agent.codex_fast import (
    fast_service_tier,
    model_catalog_has_data,
    preference_enabled,
)
from telegram_codex_agent.core.config import CodexConfig
from telegram_codex_agent.integrations.codex import CodexAppServer


def _catalog() -> dict[str, object]:
    return {
        "data": [
            {
                "id": "gpt-5.6-terra",
                "model": "gpt-5.6-terra",
                "serviceTiers": [
                    {
                        "id": "priority",
                        "name": "Fast",
                        "description": "1.5x speed, increased usage",
                    }
                ],
            },
            {
                "id": "unsupported-model",
                "model": "unsupported-model",
                "serviceTiers": [],
            },
        ]
    }


def test_resolves_catalog_fast_service_tier() -> None:
    assert model_catalog_has_data(_catalog()) is True
    assert fast_service_tier(_catalog(), "gpt-5.6-terra") == "priority"
    assert fast_service_tier(_catalog(), "unsupported-model") is None
    assert fast_service_tier({}, "gpt-5.6-terra") is None
    assert preference_enabled(True) is True
    assert preference_enabled("on") is True
    assert preference_enabled(False) is False
    assert preference_enabled("false") is False


def test_fast_service_tier_is_sent_to_start_resume_and_turn() -> None:
    class RecordingAppServer(CodexAppServer):
        def __init__(self) -> None:
            super().__init__(
                CodexConfig(
                    model="gpt-5.6-terra",
                    reasoning_effort="high",
                    service_tier="priority",
                )
            )
            self.requests: list[tuple[str, dict[str, Any] | None]] = []

        async def request(
            self,
            method: str,
            params: dict[str, Any] | None,
            *,
            timeout: float = 60,
        ) -> dict[str, Any]:
            self.requests.append((method, params))
            if method == "thread/start":
                return {"thread": {"id": "new-thread"}}
            if method == "thread/resume":
                return {"thread": {"id": "saved-thread"}}
            if method == "turn/start":
                asyncio.get_running_loop().call_soon(
                    asyncio.create_task,
                    self._dispatch(
                        {
                            "method": "turn/completed",
                            "params": {
                                "threadId": "new-thread",
                                "turn": {"id": "turn-1", "status": "completed"},
                            },
                        }
                    ),
                )
                return {"turn": {"id": "turn-1"}}
            raise AssertionError(method)

    async def exercise() -> list[tuple[str, dict[str, Any] | None]]:
        client = RecordingAppServer()
        thread = await client.start_thread(Path.cwd(), ephemeral=True)
        await client.resume_thread("saved-thread", Path.cwd())
        await client.run_turn(thread, "test", timeout=2)
        return client.requests

    requests = asyncio.run(exercise())
    params_by_method = {method: params for method, params in requests}
    for method in ("thread/start", "thread/resume", "turn/start"):
        params = params_by_method[method]
        assert params is not None
        assert params["serviceTier"] == "priority"


def test_standard_mode_omits_service_tier() -> None:
    class StandardAppServer(CodexAppServer):
        def __init__(self) -> None:
            super().__init__(CodexConfig(model="gpt-5.6-terra"))
            self.params: dict[str, Any] = {}

        async def request(
            self,
            method: str,
            params: dict[str, Any] | None,
            *,
            timeout: float = 60,
        ) -> dict[str, Any]:
            assert method == "thread/start"
            assert params is not None
            self.params = params
            return {"thread": {"id": "standard-thread"}}

    async def exercise() -> dict[str, Any]:
        client = StandardAppServer()
        await client.start_thread(Path.cwd())
        return client.params

    assert "serviceTier" not in asyncio.run(exercise())
