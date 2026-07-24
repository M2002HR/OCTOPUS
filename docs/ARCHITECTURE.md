# Architecture

```text
Telegram Bot API (aiogram) -> normalizer -> PostgreSQL job source of truth
                                               |
                                               v
                                        Redis Stream queue
                                               |
                                               v
                                      native worker/orchestrator
                              /----------------|-----------------\\
                           Ajil UAG      Codex App Server      host tools

Telethon + PyTgCalls private calls -> existing voice_agent -> Ajil
```

The Bot API and Telethon service have different Telegram capabilities and credentials. They share
the root environment contract and Ajil gateway but do not share a process. PostgreSQL is the
durable source of truth; Redis only delivers jobs and live events.
