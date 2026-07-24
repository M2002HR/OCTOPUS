"""Typed, cancellable JSONL client for the locally installed Codex App Server.

The app server is deliberately used over stdio rather than shelling out to
``codex exec``.  That gives jobs stable thread/turn identifiers, event-level
auditability, explicit approval handling, and a real interrupt operation.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from telegram_codex_agent.core.config import CodexConfig
from telegram_codex_agent.core.errors import ConfigurationError

logger = logging.getLogger(__name__)

Json = dict[str, Any]
EventCallback = Callable[[str, Json], Awaitable[None] | None]
ApprovalCallback = Callable[[str, Json], Awaitable[Json] | Json]


class CodexProtocolError(RuntimeError):
    """Raised when the App Server returns a JSON-RPC error or malformed event."""


@dataclass(slots=True)
class CodexThreadHandle:
    id: str
    cwd: str
    model: str


@dataclass(slots=True)
class CodexTurnResult:
    thread_id: str
    turn_id: str
    status: str
    text: str = ""
    error: str = ""
    events: list[Json] = field(default_factory=list)


class CodexAppServer:
    """One App Server process with concurrent JSON-RPC request/event handling."""

    def __init__(
        self,
        config: CodexConfig,
        *,
        on_event: EventCallback | None = None,
        approval_decider: ApprovalCallback | None = None,
    ) -> None:
        self.config = config
        self.on_event = on_event
        self.approval_decider = approval_decider or self._default_approval
        self.process: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._next_id = 0
        self._pending: dict[int, asyncio.Future[Json]] = {}
        self._turn_events: dict[str, list[Json]] = {}
        self._turn_done: dict[str, asyncio.Future[CodexTurnResult]] = {}
        self.active_turns: dict[str, tuple[str, str]] = {}
        self._write_lock = asyncio.Lock()

    async def __aenter__(self) -> CodexAppServer:
        await self.start()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def start(self) -> None:
        if self.process and self.process.returncode is None:
            return
        try:
            self.process = await asyncio.create_subprocess_exec(
                self.config.binary,
                "app-server",
                "--stdio",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise ConfigurationError(f"Codex binary is unavailable: {self.config.binary}") from exc
        self._reader_task = asyncio.create_task(self._read_stdout(), name="codex-app-server-reader")
        self._stderr_task = asyncio.create_task(self._read_stderr(), name="codex-app-server-stderr")
        await self.request(
            "initialize",
            {
                "clientInfo": {"name": "telegram-codex-agent", "version": "0.2.0"},
                "capabilities": {"experimentalApi": True},
            },
            timeout=self.config.startup_timeout_seconds,
        )
        await self._write({"jsonrpc": "2.0", "method": "initialized", "params": {}})

    async def close(self) -> None:
        process = self.process
        self.process = None
        if not process:
            return
        if process.stdin:
            process.stdin.close()
            try:
                await process.stdin.wait_closed()
            except (BrokenPipeError, ConnectionResetError):
                pass
        try:
            await asyncio.wait_for(process.wait(), timeout=5)
        except TimeoutError:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=5)
            except TimeoutError:
                process.kill()
                await process.wait()
        for task in (self._reader_task, self._stderr_task):
            if task and not task.done():
                task.cancel()
        for future in self._pending.values():
            if not future.done():
                future.set_exception(CodexProtocolError("Codex App Server closed"))
        self._pending.clear()

    async def request(
        self,
        method: str,
        params: Json | None,
        *,
        timeout: float = 60,
    ) -> Json:
        if not self.process or not self.process.stdin:
            raise CodexProtocolError("Codex App Server is not running")
        self._next_id += 1
        request_id = self._next_id
        future: asyncio.Future[Json] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        await self._write({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        finally:
            self._pending.pop(request_id, None)

    async def start_thread(self, cwd: Path | str, *, ephemeral: bool = False) -> CodexThreadHandle:
        absolute_cwd = str(Path(cwd).resolve())
        params: Json = {
            "cwd": absolute_cwd,
            "model": self.config.model,
            "approvalPolicy": self.config.approval_policy,
            "sandbox": self.config.sandbox_mode,
            "ephemeral": ephemeral,
        }
        if self.config.service_tier:
            params["serviceTier"] = self.config.service_tier
        result = await self.request(
            "thread/start",
            params,
            timeout=self.config.startup_timeout_seconds,
        )
        thread = result.get("thread", {})
        thread_id = thread.get("id")
        if not isinstance(thread_id, str) or not thread_id:
            raise CodexProtocolError(f"thread/start did not return a thread id: {result!r}")
        return CodexThreadHandle(thread_id, absolute_cwd, self.config.model)

    async def resume_thread(self, thread_id: str, cwd: Path | str) -> CodexThreadHandle:
        """Resume a persisted App Server thread in its registered workspace."""
        absolute_cwd = str(Path(cwd).resolve())
        params: Json = {
            "threadId": thread_id,
            "cwd": absolute_cwd,
            "model": self.config.model,
            "approvalPolicy": self.config.approval_policy,
            "sandbox": self.config.sandbox_mode,
        }
        if self.config.service_tier:
            params["serviceTier"] = self.config.service_tier
        result = await self.request(
            "thread/resume",
            params,
            timeout=self.config.startup_timeout_seconds,
        )
        thread = result.get("thread", {})
        resumed_id = thread.get("id") or thread_id
        if not isinstance(resumed_id, str) or not resumed_id:
            raise CodexProtocolError(f"thread/resume did not return a thread id: {result!r}")
        return CodexThreadHandle(
            resumed_id,
            absolute_cwd,
            self.config.model,
        )

    async def run_turn(
        self,
        thread: CodexThreadHandle,
        prompt: str,
        *,
        timeout: float,
        output_schema: Json | None = None,
    ) -> CodexTurnResult:
        params: Json = {
            "threadId": thread.id,
            "input": [{"type": "text", "text": prompt}],
            "approvalPolicy": self.config.approval_policy,
            "effort": self.config.reasoning_effort,
            # A resumed thread may have been created with another model. The
            # explicit per-turn override is authoritative, matching `/model`.
            "model": self.config.model,
            "cwd": thread.cwd,
        }
        if self.config.service_tier:
            params["serviceTier"] = self.config.service_tier
        if output_schema is not None:
            params["outputSchema"] = output_schema
        result = await self.request("turn/start", params, timeout=self.config.startup_timeout_seconds)
        turn = result.get("turn", {})
        turn_id = turn.get("id")
        if not isinstance(turn_id, str) or not turn_id:
            raise CodexProtocolError(f"turn/start did not return a turn id: {result!r}")
        completed: asyncio.Future[CodexTurnResult] = asyncio.get_running_loop().create_future()
        self._turn_events[turn_id] = []
        self._turn_done[turn_id] = completed
        self.active_turns[turn_id] = (thread.id, turn_id)
        try:
            return await asyncio.wait_for(completed, timeout=timeout)
        except TimeoutError as exc:
            await self.interrupt(thread.id, turn_id)
            raise CodexProtocolError(f"Codex turn timed out after {timeout:.0f}s") from exc
        finally:
            self._turn_done.pop(turn_id, None)
            self.active_turns.pop(turn_id, None)

    async def interrupt(self, thread_id: str, turn_id: str) -> None:
        try:
            await self.request("turn/interrupt", {"threadId": thread_id, "turnId": turn_id}, timeout=15)
        except (CodexProtocolError, TimeoutError):
            logger.warning("codex turn interrupt failed", extra={"thread_id": thread_id, "turn_id": turn_id})

    async def _write(self, payload: Json) -> None:
        assert self.process and self.process.stdin
        async with self._write_lock:
            self.process.stdin.write((json.dumps(payload, ensure_ascii=False) + "\n").encode())
            await self.process.stdin.drain()

    async def _read_stdout(self) -> None:
        assert self.process and self.process.stdout
        stdout = self.process.stdout
        try:
            while line := await stdout.readline():
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning("ignoring malformed Codex JSONL", extra={"line": line.decode(errors="replace")[:500]})
                    continue
                await self._dispatch(message)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Codex App Server stdout reader failed")

    async def _read_stderr(self) -> None:
        assert self.process and self.process.stderr
        stderr = self.process.stderr
        try:
            while line := await stderr.readline():
                logger.debug("codex app server", extra={"line": line.decode(errors="replace").rstrip()})
        except asyncio.CancelledError:
            raise

    async def _dispatch(self, message: Json) -> None:
        message_id = message.get("id")
        if isinstance(message_id, int) and ("result" in message or "error" in message):
            future = self._pending.get(message_id)
            if future and not future.done():
                if "error" in message:
                    future.set_exception(CodexProtocolError(str(message["error"])))
                else:
                    future.set_result(message["result"])
            return
        method = message.get("method")
        if isinstance(message_id, int) and isinstance(method, str):
            decision = await self.approval_decider(method, message.get("params") or {})
            await self._write({"jsonrpc": "2.0", "id": message_id, "result": decision})
            return
        if not isinstance(method, str):
            return
        params = message.get("params") or {}
        turn = params.get("turn") or {}
        turn_id = params.get("turnId") or turn.get("id")
        if isinstance(turn_id, str) and turn_id in self._turn_events:
            self._turn_events[turn_id].append(message)
        if self.on_event:
            maybe_awaitable = self.on_event(method, params)
            if maybe_awaitable is not None:
                await maybe_awaitable
        if method == "turn/completed" and isinstance(turn_id, str):
            future = self._turn_done.get(turn_id)
            if future and not future.done():
                future.set_result(
                    CodexTurnResult(
                        thread_id=str(params.get("threadId", "")),
                        turn_id=turn_id,
                        status=str(turn.get("status", "failed")),
                        text=self._assistant_text(self._turn_events.get(turn_id, [])),
                        error=str((turn.get("error") or {}).get("message", "")),
                        events=list(self._turn_events.get(turn_id, [])),
                    )
                )

    @staticmethod
    def _assistant_text(events: list[Json]) -> str:
        final_messages: list[str] = []
        legacy_messages: list[str] = []
        for event in events:
            if event.get("method") != "item/completed":
                continue
            item = (event.get("params") or {}).get("item") or {}
            if item.get("type") == "agentMessage" and isinstance(item.get("text"), str):
                phase = str(item.get("phase") or "").casefold()
                if phase == "final_answer":
                    final_messages.append(item["text"])
                elif phase != "commentary":
                    # Older providers may omit phase. Preserve their historical
                    # behavior rather than dropping the only assistant output.
                    legacy_messages.append(item["text"])
        return "\n".join(final_messages or legacy_messages).strip()

    @staticmethod
    async def _default_approval(method: str, params: Json) -> Json:
        """Never grant unrecognised privilege escalations without a policy handler."""
        logger.warning("Codex requested approval without a job policy", extra={"method": method, "params": params})
        if method in {"item/commandExecution/requestApproval", "item/fileChange/requestApproval"}:
            return {"decision": "decline"}
        if method == "item/permissions/requestApproval":
            return {"permissions": {"fileSystem": None, "network": None}, "scope": "turn"}
        return {"decision": "cancel"}
