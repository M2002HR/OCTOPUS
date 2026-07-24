from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, TypeVar
from uuid import uuid4

import httpx
from pydantic import BaseModel, ValidationError

from telegram_codex_agent.core.config import AjilConfig
from telegram_codex_agent.core.errors import (
    AjilFallbackError,
    AjilUnavailableError,
    StructuredOutputError,
)

T = TypeVar("T", bound=BaseModel)


class AjilResponse(BaseModel):
    data: dict[str, Any]
    request_id: str
    model: str = ""
    provider: str = ""
    is_fallback: bool = False


class AjilClient:
    """Typed async client for the pinned Unified AI Gateway contract."""

    def __init__(self, config: AjilConfig, client: httpx.AsyncClient | None = None) -> None:
        self.config = config
        headers = {"accept": "application/json"}
        if config.auth_token:
            headers[config.auth_header_name] = config.auth_token
        self._client = client or httpx.AsyncClient(
            base_url=config.base_url.rstrip("/"),
            timeout=config.timeout_seconds,
            headers=headers,
            trust_env=False,
        )
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _headers(self, request_id: str) -> dict[str, str]:
        return {"x-request-id": request_id}

    @staticmethod
    def _fallback(response: httpx.Response, data: dict[str, Any]) -> bool:
        headers = {key.casefold(): value.casefold() for key, value in response.headers.items()}
        return headers.get("x-uag-fallback") in {"1", "true"} or bool(
            data.get("fallback") or data.get("is_fallback")
        )

    async def _json(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        files: Any = None,
        reject_fallback: bool = False,
    ) -> AjilResponse:
        request_id = uuid4().hex
        try:
            response = await self._client.request(
                method, path, json=json_body, files=files, headers=self._headers(request_id)
            )
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            raise AjilUnavailableError(f"Ajil {method} {path} failed: {exc}") from exc
        if not isinstance(data, dict):
            raise AjilUnavailableError(f"Ajil {method} {path} returned a non-object response")
        is_fallback = self._fallback(response, data)
        if reject_fallback and is_fallback:
            raise AjilFallbackError(
                "Ajil returned a local fallback where structured output was required"
            )
        return AjilResponse(
            data=data,
            request_id=response.headers.get("x-request-id", request_id),
            model=response.headers.get("x-model-winner", ""),
            provider=response.headers.get("x-provider-winner", ""),
            is_fallback=is_fallback,
        )

    async def health(self) -> dict[str, Any]:
        return (await self._json("GET", "/health")).data

    async def list_models(self) -> dict[str, Any]:
        return (await self._json("GET", "/v1/models")).data

    async def list_model_catalog(self) -> dict[str, Any]:
        return (await self._json("GET", "/v1/models/catalog")).data

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str = "",
        temperature: float | None = None,
        stream: bool = False,
        routing: dict[str, Any] | None = None,
    ) -> AjilResponse:
        body: dict[str, Any] = {"messages": messages, "stream": stream}
        if model:
            body["model"] = model
        if temperature is not None:
            body["temperature"] = temperature
        if routing:
            body["x_router"] = routing
        return await self._json("POST", "/v1/chat/completions", json_body=body)

    async def chat_stream(
        self, messages: list[dict[str, Any]], *, model: str = ""
    ) -> AsyncIterator[str]:
        request_id = uuid4().hex
        async with self._client.stream(
            "POST",
            "/v1/chat/completions",
            json={"messages": messages, "stream": True, "model": model},
            headers=self._headers(request_id),
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: ") and line[6:] != "[DONE]":
                    yield line[6:]

    async def responses(self, payload: dict[str, Any]) -> AjilResponse:
        return await self._json("POST", "/v1/responses", json_body=payload)

    async def embeddings(self, inputs: list[str], *, model: str = "") -> AjilResponse:
        body: dict[str, Any] = {"input": inputs}
        if model:
            body["model"] = model
        return await self._json("POST", "/v1/embeddings", json_body=body)

    async def image_generation(self, prompt: str, **options: Any) -> AjilResponse:
        return await self._json(
            "POST", "/v1/images/generations", json_body={"prompt": prompt, **options}
        )

    async def transcribe(
        self, audio_path: Path, *, model: str = "", language: str = ""
    ) -> AjilResponse:
        with audio_path.open("rb") as handle:
            files = {"file": (audio_path.name, handle, "audio/wav")}
            data: dict[str, Any] = {"model": model} if model else {}
            if language:
                data["language"] = language
            request_id = uuid4().hex
            try:
                response = await self._client.post(
                    "/v1/audio/transcriptions",
                    data=data,
                    files=files,
                    headers=self._headers(request_id),
                )
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, json.JSONDecodeError) as exc:
                raise AjilUnavailableError(f"Ajil transcription failed: {exc}") from exc
        return AjilResponse(
            data=payload,
            request_id=response.headers.get("x-request-id", request_id),
            is_fallback=self._fallback(response, payload),
        )

    async def speech(
        self, text: str, *, model: str = "", voice: str = "", response_format: str = "wav"
    ) -> bytes:
        response = await self._client.post(
            "/v1/audio/speech",
            json={
                "input": text,
                "model": model,
                "voice": voice,
                "response_format": response_format,
            },
            headers=self._headers(uuid4().hex),
        )
        try:
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AjilUnavailableError(f"Ajil speech failed: {exc}") from exc
        return response.content

    async def orchestrate(self, payload: dict[str, Any]) -> AjilResponse:
        return await self._json("POST", "/v1/orchestrate", json_body=payload)

    async def structured_chat(
        self,
        schema: type[T],
        messages: list[dict[str, Any]],
        *,
        model: str = "",
        retries: int | None = None,
    ) -> tuple[T, AjilResponse]:
        attempts = retries if retries is not None else self.config.planner.max_retries
        schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False)
        feedback = ""
        for attempt in range(attempts + 1):
            response = await self.chat(
                [
                    *messages,
                    {
                        "role": "system",
                        "content": f"Return JSON only, validating exactly against this JSON Schema: {schema_json}. {feedback}",
                    }
                ],
                model=model or self.config.planner.model,
                temperature=self.config.planner.temperature,
                routing={"allow_local_fallback": False},
            )
            if response.is_fallback and self.config.planner.reject_local_fallback:
                raise AjilFallbackError("planner fallback response rejected")
            content = self._content(response.data)
            try:
                return schema.model_validate_json(self._extract_json(content)), response
            except (ValidationError, ValueError) as exc:
                feedback = f"Previous output failed validation: {exc}. Return corrected JSON only."
                if attempt == attempts:
                    raise StructuredOutputError(
                        f"Ajil planner returned invalid structured output: {exc}"
                    ) from exc
        raise AssertionError("unreachable")

    @staticmethod
    def _content(data: dict[str, Any]) -> str:
        choices = data.get("choices", [])
        if choices and isinstance(choices[0], dict):
            message = choices[0].get("message", {})
            if isinstance(message, dict) and isinstance(message.get("content"), str):
                return message["content"]
        if isinstance(data.get("output_text"), str):
            return data["output_text"]
        raise ValueError("Ajil response has no assistant text")

    @staticmethod
    def _extract_json(content: str) -> str:
        text = content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        json.loads(text)
        return text
