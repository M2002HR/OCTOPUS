from __future__ import annotations

import mimetypes
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import httpx

from voice_agent.domain import ChatMessage


class UAGError(RuntimeError):
    pass


class UAGClient:
    def __init__(
        self,
        *,
        base_url: str,
        chat_endpoint: str,
        transcriptions_endpoint: str,
        timeout_seconds: int,
        auth_token: str,
        auth_header_name: str,
        models: tuple[str, ...],
        providers: tuple[str, ...],
        transcription_provider: str,
        transcription_models: tuple[str, ...],
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.chat_endpoint = chat_endpoint if chat_endpoint.startswith("/") else f"/{chat_endpoint}"
        self.transcriptions_endpoint = (
            transcriptions_endpoint
            if transcriptions_endpoint.startswith("/")
            else f"/{transcriptions_endpoint}"
        )
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(timeout_seconds), trust_env=False)
        self.auth_token = auth_token
        self.auth_header_name = auth_header_name
        self.models = models
        self.providers = providers
        self.transcription_provider = transcription_provider
        self.transcription_models = transcription_models

    def _headers(self) -> dict[str, str]:
        return {self.auth_header_name: self.auth_token} if self.auth_token else {}

    async def aclose(self) -> None:
        await self.client.aclose()

    async def transcribe(self, audio_path: Path, *, language: str | None) -> str:
        data: dict[str, str] = {}
        if language:
            data["language"] = language
        # Ajil's direct transcription endpoint intentionally selects its model
        # from root-level ``UAG_GROQ_STT_*`` configuration.  Sending the
        # routing-style ``groq/model`` values as multipart fields makes older
        # deployed gateway versions forward that invalid qualified id to Groq.
        # Keep the request wire format compatible with both deployed and vendored
        # gateway versions; the root .env remains the single model source.
        with audio_path.open("rb") as stream:
            content_type = mimetypes.guess_type(audio_path.name)[0] or "application/octet-stream"
            response = await self.client.post(
                self.base_url + self.transcriptions_endpoint,
                data=data,
                files={"file": (audio_path.name, stream, content_type)},
                headers=self._headers(),
            )
        body = self._expect_json(response)
        payload = body.get("payload") if isinstance(body.get("payload"), dict) else body
        text = str(payload.get("text") or "").strip() if isinstance(payload, dict) else ""
        if not text:
            raise UAGError("UAG transcription response did not contain text")
        return text

    async def reply(self, *, messages: Sequence[ChatMessage], system_prompt: str) -> str:
        payload: dict[str, Any] = {
            "model": ",".join(self.models),
            "messages": (
                [{"role": "system", "content": system_prompt}]
                + [{"role": item.role, "content": item.content} for item in messages]
            ),
            "stream": False,
        }
        if self.providers:
            payload["x_router"] = {"providers": list(self.providers), "strategy": "fallback_chain"}
        response = await self.client.post(
            self.base_url + self.chat_endpoint, json=payload, headers=self._headers()
        )
        body = self._expect_json(response)
        text = self._extract_reply(body)
        if not text:
            raise UAGError("UAG chat response did not contain assistant text")
        return text

    @staticmethod
    def _expect_json(response: httpx.Response) -> dict[str, Any]:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise UAGError(f"UAG returned HTTP {response.status_code}") from exc
        try:
            payload = response.json()
        except ValueError as exc:
            raise UAGError("UAG returned non-JSON response") from exc
        if not isinstance(payload, dict):
            raise UAGError("UAG returned invalid JSON payload")
        return payload

    @staticmethod
    def _extract_reply(body: dict[str, Any]) -> str:
        winner = body.get("winner")
        payload = winner.get("payload") if isinstance(winner, dict) else body
        choices = payload.get("choices") if isinstance(payload, dict) else None
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            message = choices[0].get("message")
            if isinstance(message, dict):
                return str(message.get("content") or "").strip()
        return str(payload.get("text") or "").strip() if isinstance(payload, dict) else ""
