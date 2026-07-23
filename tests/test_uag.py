import json
from pathlib import Path

import httpx
import pytest

from voice_agent.adapters.uag import UAGClient, UAGError
from voice_agent.domain import ChatMessage


def make_client() -> UAGClient:
    return UAGClient(
        base_url="http://uag.test",
        chat_endpoint="/v1/chat/completions",
        transcriptions_endpoint="/v1/audio/transcriptions",
        timeout_seconds=10,
        auth_token="test-token",
        auth_header_name="x-api-token",
        models=("model-a",),
        providers=("groq",),
        transcription_provider="groq",
        transcription_models=("groq/whisper-large-v3-turbo",),
        vision_models=("gemini/gemini-2.5-flash",),
        vision_providers=("gemini",),
    )


@pytest.mark.asyncio
async def test_transcription_uses_gateway_config_and_wav_mime_type(tmp_path: Path) -> None:
    audio = tmp_path / "turn.wav"
    audio.write_bytes(b"RIFFfake-wav")

    async def handler(request: httpx.Request) -> httpx.Response:
        body = request.content.decode("latin-1")
        assert request.headers["x-api-token"] == "test-token"
        assert 'name="language"' in body
        assert "groq/whisper" not in body
        assert "Content-Type: audio/x-wav" in body
        return httpx.Response(200, json={"payload": {"text": "سلام"}}, request=request)

    client = make_client()
    await client.client.aclose()
    client.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        assert await client.transcribe(audio, language="fa") == "سلام"
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_chat_extracts_gateway_winner_and_rejects_errors() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("chat/completions"):
            return httpx.Response(
                200,
                json={"winner": {"payload": {"choices": [{"message": {"content": "پاسخ"}}]}}},
                request=request,
            )
        return httpx.Response(502, json={}, request=request)

    client = make_client()
    await client.client.aclose()
    client.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        response_text = await client.reply(
            messages=[ChatMessage("user", "سلام")], system_prompt="x"
        )
        assert response_text == "پاسخ"
        response = httpx.Response(502, request=httpx.Request("GET", "http://uag.test"))
        with pytest.raises(UAGError, match="HTTP 502"):
            client._expect_json(response)
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_vision_chat_uses_openai_data_url_content(tmp_path: Path) -> None:
    image = tmp_path / "input.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["model"] == "gemini/gemini-2.5-flash"
        assert payload["x_router"]["providers"] == ["gemini"]
        content = payload["messages"][-1]["content"]
        assert content[0] == {"type": "text", "text": "What is shown?"}
        assert content[1]["type"] == "image_url"
        assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")
        return httpx.Response(
            200,
            json={"winner": {"payload": {"choices": [{"message": {"content": "تصویر"}}]}}},
            request=request,
        )

    client = make_client()
    await client.client.aclose()
    client.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        assert (
            await client.reply_with_image(
                messages=[ChatMessage("user", "history")],
                system_prompt="system",
                image_path=image,
                prompt="What is shown?",
            )
            == "تصویر"
        )
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_vision_chat_includes_each_referenced_image(tmp_path: Path) -> None:
    first = tmp_path / "first.png"
    second = tmp_path / "second.jpg"
    first.write_bytes(b"first")
    second.write_bytes(b"second")

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        content = payload["messages"][-1]["content"]
        assert content[0]["type"] == "text"
        assert [item["type"] for item in content[1:]] == ["image_url", "image_url"]
        return httpx.Response(
            200,
            json={"winner": {"payload": {"choices": [{"message": {"content": "تصاویر"}}]}}},
            request=request,
        )

    client = make_client()
    await client.client.aclose()
    client.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        assert (
            await client.reply_with_images(
                messages=[],
                system_prompt="system",
                image_paths=(first, second),
                prompt="مقایسه کن",
            )
            == "تصاویر"
        )
    finally:
        await client.aclose()
