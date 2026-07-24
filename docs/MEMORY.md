# Persistent memory and continuity

OCTOPUS separates conversation history, explicit memory, user preferences, project context,
execution outcomes, and Codex thread continuity. These data have different scopes and must not be
collapsed into one global prompt.

## Stored layers

| Layer | Storage | Scope and purpose |
| --- | --- | --- |
| Telegram messages | PostgreSQL `messages` | Normalized user/assistant input and attachment metadata within a conversation |
| Conversation summary | PostgreSQL `conversations.summary` | Bounded context for one user/chat/project conversation |
| User preferences | PostgreSQL `users.preferences_json` | Model, reasoning, Fast mode, permissions, language, log level, completion-call opt-in |
| Explicit memory | PostgreSQL `memory_records` | User-created facts via `/remember`, optionally conversation/project scoped |
| Project registry | PostgreSQL `projects` plus YAML | Trusted roots, commands, browser metadata, and environment policy |
| Job outcomes | PostgreSQL jobs/events | Results and evidence available to history and later orchestration |
| Codex continuity | PostgreSQL `codex_threads` | App Server thread ID, cwd, model/policy, latest turn, usage, status |
| Voice conversation | SQLite `conversation_turns` | Optional transcript/reply retention for private calls |
| Telethon messages | SQLite `message_turns` | Optional content retention for compatibility messaging |

PostgreSQL is authoritative for the Bot/Codex control plane. Voice SQLite is an independent
compatibility store and is never treated as Codex session memory.

## Scope and ownership

Every control-plane record is tied to the requesting Telegram user, chat, conversation, and
project as applicable. `/history`, `/resume`, `/logs`, `/memory`, and job actions filter by owner;
an identifier from another user is not sufficient authorization.

Project context never crosses cwd automatically. Selecting another workspace creates/chooses a
conversation appropriate to that project. A Codex thread is not resumed in a different project.

## Explicit memory commands

- `/remember TEXT` stores a user-owned memory in the active conversation/project context.
- `/memory` lists records visible to the current user/context.
- `/forget MEMORY_ID` removes an owned record.

Memory content is treated as untrusted context, not executable shell, cwd, configuration, or an
approval grant.

## Retrieval and summarization

`memory.enabled` controls use of the memory service. `memory.retrieval_limit` bounds retrieved
records. Current retrieval is deterministic lexical/scoped retrieval; the schema includes optional
embedding fields for future semantic retrieval, but documentation must not claim a production
vector retriever until one is enabled and tested.

`memory.summarize_after_messages` is the policy threshold for conversation compaction. Raw durable
messages remain the audit/history source; summaries are derived context, not an authoritative job
result.

## Preferences and job snapshots

Preferences are mutable user state, while jobs are immutable execution snapshots. At job creation
the service copies relevant values into job metadata:

- model and reasoning effort;
- Fast mode/service tier;
- sandbox/approval mode;
- input/response language;
- live log policy;
- completion-call opt-in and protected target Telegram ID;
- selected project/session identifiers.

This prevents a settings click during execution from changing the meaning of an already queued
job. New or resumed turns use the latest snapshot.

## Codex session history

`/history` combines:

- the prompts sent in the selected session;
- terminal results/errors;
- ordered job events and safe public Codex commentary;
- persisted thread token/context usage;
- running/idle terminal state.

The authenticated account's weekly quota is not session history; it is fetched separately by
`/usage`.

## Privacy and retention

Message text, summaries, memory, job objectives/results, and optional voice transcripts are
sensitive. PostgreSQL and voice SQLite require protected filesystem/database access and external
backup/retention policy. JSONL voice audit and operational logs intentionally omit conversation
content.

The application does not claim encryption at rest or automatic GDPR-style retention enforcement.
Use encrypted storage and a documented deletion schedule before broader deployment.

Do not store passwords, API keys, session strings, authentication cookies, or private keys through
`/remember`. Root `.env` is the only secret source.
