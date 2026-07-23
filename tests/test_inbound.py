import asyncio
from pathlib import Path
from typing import Any

import pytest
from pytgcalls.types import ChatUpdate

from voice_agent.storage import AuditStore
from voice_agent.voip import IncomingCallServer


class FakeMtProto:
    def __init__(self) -> None:
        self.discarded: list[tuple[int, bool]] = []

    async def discard_call(self, peer_id: int, missed: bool) -> None:
        self.discarded.append((peer_id, missed))


class FakeCalls:
    def __init__(self) -> None:
        self._app = FakeMtProto()
        self._p2p_configs: dict[int, object] = {}
        self.handlers: list[Any] = []
        self.started = False

    def add_handler(self, handler: Any) -> None:
        self.handlers.append(handler)

    def remove_handler(self, handler: Any) -> None:
        self.handlers.remove(handler)

    async def start(self) -> None:
        self.started = True

    async def emit(self, update: ChatUpdate) -> None:
        for handler in tuple(self.handlers):
            await handler(self, update)


@pytest.mark.asyncio
async def test_inbound_server_accepts_only_configured_peer(tmp_path: Path) -> None:
    calls = FakeCalls()
    accepted: list[int] = []
    ended: list[int] = []
    store = AuditStore(tmp_path / "events.db", tmp_path / "events.jsonl")

    async def on_authorized(peer_id: int, _: object) -> None:
        accepted.append(peer_id)

    async def on_ended(peer_id: int) -> None:
        ended.append(peer_id)

    server = IncomingCallServer(
        telethon_client=object(),
        calls=calls,
        audit=store,
        allowed_peer_id=42,
        on_authorized_call=on_authorized,
        on_call_ended=on_ended,
    )
    await server.start()
    await calls.emit(ChatUpdate(42, ChatUpdate.Status.INCOMING_CALL))
    await asyncio.sleep(0)
    assert calls.started
    assert accepted == [42]
    assert calls._app.discarded == []

    await calls.emit(ChatUpdate(42, ChatUpdate.Status.DISCARDED_CALL))
    await asyncio.sleep(0)
    assert ended == [42]
    assert not server.busy
    await server.stop()
    store.close()


@pytest.mark.asyncio
async def test_inbound_server_rejects_non_allowlisted_peer(tmp_path: Path) -> None:
    calls = FakeCalls()
    store = AuditStore(tmp_path / "events.db", tmp_path / "events.jsonl")

    async def unexpected_authorized(_: int, __: object) -> None:
        raise AssertionError("an unauthorized caller must never be accepted")

    async def on_ended(_: int) -> None:
        return None

    server = IncomingCallServer(
        telethon_client=object(),
        calls=calls,
        audit=store,
        allowed_peer_id=42,
        on_authorized_call=unexpected_authorized,
        on_call_ended=on_ended,
    )
    await server.start()
    calls._p2p_configs[99] = object()
    await calls.emit(ChatUpdate(99, ChatUpdate.Status.INCOMING_CALL))
    await asyncio.sleep(0)
    assert calls._app.discarded == [(99, True)]
    assert 99 not in calls._p2p_configs
    assert ("call.incoming.rejected", "ok") in store.events_for_trace("inbound-listener")
    await server.stop()
    store.close()
