"""Durable, scoped memory with deterministic lexical retrieval fallback."""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from telegram_codex_agent.db.models import MemoryRecord

_TOKEN = re.compile(r"[\w\u0600-\u06ff]{2,}", re.UNICODE)


class MemoryService:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def remember(
        self,
        user_id: str,
        content: str,
        *,
        title: str = "user memory",
        conversation_id: str | None = None,
        project_id: str | None = None,
        memory_type: str = "user_preference",
        importance: int = 50,
    ) -> str:
        async with self.sessions() as session:
            row = MemoryRecord(
                user_id=user_id,
                conversation_id=conversation_id,
                project_id=project_id,
                memory_type=memory_type,
                title=title[:255],
                content=content[:20_000],
                importance=max(0, min(100, importance)),
            )
            session.add(row)
            await session.commit()
            return row.id

    async def retrieve(
        self, user_id: str, query: str, *, conversation_id: str | None = None, project_id: str | None = None, limit: int = 8
    ) -> list[MemoryRecord]:
        tokens = set(_TOKEN.findall(query.casefold()))
        async with self.sessions() as session:
            rows = list(
                await session.scalars(
                    select(MemoryRecord)
                    .where(MemoryRecord.user_id == user_id)
                    .order_by(MemoryRecord.importance.desc(), MemoryRecord.updated_at.desc())
                    .limit(100)
                )
            )
            def score(row: MemoryRecord) -> tuple[int, int]:
                text_tokens = set(_TOKEN.findall(f"{row.title} {row.content}".casefold()))
                scope = int(row.conversation_id == conversation_id) * 4 + int(row.project_id == project_id) * 3
                return (len(tokens & text_tokens) * 10 + scope + row.importance // 20, row.importance)

            return sorted(rows, key=score, reverse=True)[:limit]

    async def list(self, user_id: str, limit: int = 20) -> list[MemoryRecord]:
        async with self.sessions() as session:
            return list(
                await session.scalars(
                    select(MemoryRecord)
                    .where(MemoryRecord.user_id == user_id)
                    .order_by(MemoryRecord.updated_at.desc())
                    .limit(limit)
                )
            )

    async def forget(self, user_id: str, memory_id: str) -> bool:
        async with self.sessions() as session:
            row = await session.get(MemoryRecord, memory_id, with_for_update=True)
            if row is None or row.user_id != user_id:
                return False
            await session.delete(row)
            await session.commit()
            return True
