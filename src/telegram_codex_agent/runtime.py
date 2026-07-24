from __future__ import annotations

import asyncio
import sys

from telegram_codex_agent.core.config import load_settings
from telegram_codex_agent.telegram.bot import TelegramBotService


async def _reply(_: object) -> str:
    return "پیام دریافت شد. مسیر پردازش شغل در حال راه‌اندازی است."


async def run_bot() -> None:
    service = TelegramBotService(load_settings(), _reply)
    await service.run_polling()


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "bot":
        asyncio.run(run_bot())
    elif command in {"worker", "scheduler"}:
        raise SystemExit(f"{command} runtime is available after the persistent worker bootstrap")
    else:
        raise SystemExit("usage: python -m telegram_codex_agent.runtime {bot|worker|scheduler}")


if __name__ == "__main__":
    main()
