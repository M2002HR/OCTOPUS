# Telegram Bot commands and UI

The Bot API account is the normal control surface for OCTOPUS. It manages workspaces, persistent
Codex sessions, jobs, settings, history, logs, memory, browser tasks, and artifacts. The primary
Telethon account is a separate compatibility transport for private calls/messages; it is not a
replacement for the Bot.

The interface and defaults are English. Inline keyboards are used for contextual choices and the
persistent reply keyboard exposes Home, Status, Projects, Sessions, Jobs, History, Browser,
Review, Logs, Settings, and Stop.

## First use

1. Open the Bot and send `/start`.
2. Open `/projects` and select one discovered Git workspace.
3. Send `/new` to create a fresh logical session, or `/resume` to continue one.
4. Send a normal task in natural language.
5. Watch public Codex commentary at `info`/`debug`.
6. Inspect `/status`, `/history`, `/jobs`, or `/logs JOB_ID`.

The Bot refuses a code task without an explicitly selected workspace. Workspace paths are chosen
from the configured registry/discovery root, never accepted as arbitrary Telegram filesystem input.

## Session and workspace commands

| Command | Behavior |
| --- | --- |
| `/start`, `/home` | Open the control center |
| `/help` | Show the compact command guide |
| `/projects` | List configured/discovered Git projects under `workspace.root` |
| `/project SLUG` | Select a registered workspace for this user/chat |
| `/new` | Start a fresh conversation context in the selected workspace |
| `/resume` | List saved Codex threads with selected/running/idle state |
| `/resume SESSION_ID` | Resume the selected session and its Codex App Server thread |
| `/status` | Show workspace, thread state, model, reasoning, permissions, Fast mode, selected job, thread token usage, and Codex account quota |
| `/usage` | Query authenticated Codex weekly limits and reset time |
| `/history [SESSION_ID]` | Show paginated prompts, results, and durable job events for one owned session |

`RUNNING` means a job is currently in flight. `IDLE · last completed`, `IDLE · last failed`, and
`IDLE · no tasks` describe a resumable thread with no active work. Selection and execution state
are intentionally independent.

## Job and log commands

| Command | Behavior |
| --- | --- |
| `/jobs` | List recent/running jobs with action buttons |
| `/job JOB_ID` | Show one owned job and its current state |
| `/stop JOB_ID` | Request cancellation and interrupt an active Codex turn |
| `/logs` | Open live-log level controls |
| `/logs level off\|error\|info\|debug` | Persist the Telegram progress level |
| `/logs JOB_ID [PAGE]` | Show paginated durable events |

`info` includes job lifecycle, tool summaries, and public Codex `agentMessage` commentary.
`debug` includes the most detailed safe public event set. Raw chain-of-thought/private reasoning,
credentials, environment values, and unrestricted subprocess output are never mirrored.

## Codex settings

| Command | Behavior |
| --- | --- |
| `/config` | Open all settings |
| `/model` or `/codex` | Display/select Codex model |
| `/model MODEL` | Persist a `gpt-*` model for future/resumed turns |
| `/reasoning` | Select `low`, `medium`, `high`, `xhigh`, `max`, or `ultra` |
| `/reasoning LEVEL` | Persist reasoning effort |
| `/fast` | Toggle Fast mode |
| `/fast on`, `/fast off`, `/fast status` | Explicit Fast controls |
| `/permissions` | Select Read Only, Workspace, or Full Access |
| `/permissions MODE` | Persist a sandbox mode |
| `/permission`, `/permision` | Compatibility aliases for `/permissions` |
| `/language` | Select input/STT and response language; default is English |
| `/language en\|fa` | Persist language selection while the control UI remains English |
| `/completion_call` | Show terminal-call setting and global availability |
| `/completion_call on\|off` | Persist per-user completion-call opt-in |

Preferences are stored on the Telegram user and snapshotted into each new job. A later preference
change does not mutate a running job. Resumed Codex threads still receive explicit current
model/reasoning/sandbox overrides.

Fast mode is validated against the live Codex model catalog. If the selected model does not
advertise Fast or the catalog is unavailable, the setting is not changed. Fast consumes account
limits faster and currently maps to the catalog-advertised `priority` service tier.

## Review and browser commands

| Command | Behavior |
| --- | --- |
| `/diff` | Ask Codex to inspect uncommitted changes without modifying files |
| `/review` | Ask Codex for a read-only working-tree review |
| `/browser` | Open browser actions |
| `/browser screenshot` | Use workspace browser tooling, inspect UI, save a screenshot, and attach it |
| `/browser test` | Run relevant browser/E2E checks and return reports/artifacts |
| `/browser artifact` | Find, inspect, and attach the newest relevant browser artifact |

These are structured Codex task prompts, not a second independent automation daemon. Codex runs in
the selected workspace and uses that project's existing Chrome Lab, Playwright, or browser tooling.
An attachment is returned only when Codex emits a validated
`[[telegram_file:/absolute/path]]` directive for a file contained by the workspace.

## Memory commands

| Command | Behavior |
| --- | --- |
| `/remember TEXT` | Save explicit scoped memory |
| `/memory` | List memory records owned by the active user/context |
| `/forget MEMORY_ID` | Delete an owned record |

See [Memory](MEMORY.md) for scope, retrieval, persistence, and privacy.

## Natural input and attachments

Any non-command message creates a durable job. Supported Bot inputs:

- text and captions;
- voice notes/audio, downloaded to a deterministic inbox and transcribed;
- images/photos, passed as Codex image input when a workspace task is selected;
- documents and videos, stored with safe metadata and made available to the job;
- reply context represented by the normalized message metadata.

Files have deterministic paths and SHA-256 metadata. Telegram download failure is reported rather
than silently treating the attachment as text. Generated artifacts are checked for existence,
workspace containment, file type, and Telegram upload size before delivery.

## Access boundaries

- `telegram.allowed_user_ids` and `telegram.allowed_chat_ids` in `config/agent.yaml` are the
  enforced Bot API numeric allowlists.
- Empty allowlists are suitable only for a controlled personal development deployment.
- Bot user/chat ownership scopes session, job, history, memory, and settings reads.
- `VOICE_AGENT_ALLOWED_PEER_IDS` is a separate numeric Telethon call allowlist.
- The second Telethon session is a test peer only; it must not own the primary session or run in
  the production voice process.

## Settings persistence and startup

Settings become available after the Bot has registered the user through at least one normal
message/job. Telegram slash commands are registered on Bot startup. Restart `agent-bot` after
changing Bot credentials, proxy, transport, or global policy; per-user changes require no restart.
