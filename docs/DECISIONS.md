# Architecture decisions

These decisions document the implemented design and the reason a simpler-looking alternative was
not selected.

## ADR-001: One product, two Telegram transports

The product is `telegram-codex-agent`. Aiogram Bot API is the normal control plane. The existing
`voice_agent` Telethon/PyTgCalls package remains a supported subsystem because Bot API cannot place
private user-account calls and the subsystem has real two-account validation.

Consequence: Bot and Telethon credentials, allowlists, processes, persistence, and failure domains
remain explicit. Neither transport impersonates the other.

## ADR-002: Ajil is a pinned recursive submodule

Ajil Unified AI Gateway lives at `modules/ajil_uag` with nested provider submodules. Root code uses
its HTTP contract. Changes are developed reproducibly upstream and the root pins the resulting
commit; the root agent does not edit the submodule opportunistically.

Consequence: `git submodule update --init --recursive` is mandatory. Root `.env` remains the only
environment file.

## ADR-003: Python 3.12 and Compose are the reproducible runtime

The host can run lightweight checks, but Docker/Python 3.12 is authoritative. Compose runs
infrastructure and can run all persistent agent services. Bot/worker use host networking and
mounted Codex/workspaces because the personal full-access agent must control the owner machine.
Systemd/native scripts remain a supported development option.

Consequence: production-like validation runs in the container version, and mounted paths are
explicit configuration.

## ADR-004: English default and voice enforcement

The control-plane default is English. The Telegram settings schema currently permits English and
Persian input/response preferences, while the control UI remains English. The Telethon call and
compatibility-message STT/TTS path enforces English and rejects other configured language values.
Its introduction is “Hello, yes?” and its prompt does not introduce a persona.

Consequence: documentation must distinguish configurable Bot language from the stricter voice
compatibility contract. Any language expansion requires validation, prompts, STT/TTS, and live
tests together.

## ADR-005: PostgreSQL is authoritative; Redis delivers

Users, conversations, jobs, events, Codex threads, artifacts, memory, and leases are durable in
PostgreSQL. Redis Streams deliver job IDs/live events and cache quota/catalog data.

Consequence: workers reconcile Redis messages against database state, commit terminal state before
acknowledgement, and recover pending entries. Redis loss may require republishing durable work but
does not redefine the job result.

## ADR-006: Codex App Server is the primary execution brain

Workspace implementation/testing/system management uses the local Codex App Server with persistent
threads and structured events. Ajil remains the orchestrator/direct-chat/provider gateway instead
of reimplementing Codex's shell, Git, Docker, filesystem, and browser intelligence.

Consequence: App Server lifecycle, permissions, cancellation, progress, usage, and artifacts are
first-class integrations, not parsed terminal text from one-shot CLI calls.

## ADR-007: One primary Telethon session owner

Only `voice-agent` opens `TELEGRAM_STRING_SESSION`. Worker/Bot communicate with it through durable
data, never by constructing another Telethon client.

Consequence: private-call updates are not split between clients, avoiding the observed
“Exchanging encryption keys” failure. A second session may drive tests but never owns production
calls.

## ADR-008: Completion calls use a separate durable Stream

Terminal Codex state is committed first. The worker asks Ajil for safe wording and atomically
deduplicates/publishes a request. The primary voice service validates the numeric target, speaks
three repetitions, hangs up, marks delivery, and acknowledges.

Consequence: call failure cannot poison or rewrite task completion. Recovery is at-least-once;
normal duplicates are suppressed, but a crash after audible delivery and before the delivered
marker can cause one repeat call.

## ADR-009: User settings are snapshotted per job

Model, reasoning, Fast tier, permissions, language, progress, project/thread, and completion-call
preference are copied into job metadata at creation.

Consequence: later settings changes apply to future work and cannot mutate a queued/running job.
Protected metadata is written by the service after caller metadata to prevent override.

## ADR-010: Trusted workspace registry, not arbitrary paths

The owner selects configured/discovered Git workspaces beneath `workspace.root`. Telegram strings
do not become a cwd. Artifact files must be contained by that workspace/configured root.

Consequence: the full-access engine remains powerful without turning every Telegram path into an
implicit authorization grant.

## ADR-011: Public commentary, not private reasoning

At `info`/`debug`, the Bot forwards Codex public `agentMessage` commentary, lifecycle changes, and
safe tool summaries. Raw private reasoning/chain-of-thought is not exposed.

Consequence: the owner sees meaningful intermediate progress while credentials, hidden reasoning,
and unbounded raw streams remain protected.

## ADR-012: Development full access is deliberate, not production security

Default Codex policy is `danger-full-access`, network enabled, approval `never`, because the
single owner wants an agent that can operate the destination machine. Numeric Telegram allowlists,
path containment, redaction, and process cleanup remain defense-in-depth.

Consequence: multi-user/untrusted exposure is prohibited until the hardening backlog is completed.

## Discovery record (2026-07-24)

- Linux host with Docker/Compose and FFmpeg; supported execution is Python 3.12.
- Codex CLI/App Server was authenticated through ChatGPT and protocol schemas were generated from
  the installed runtime.
- Ajil and nested modules were initialized recursively.
- Existing voice calls, STT/TTS, private messaging, image analysis, reply context, and audit
  behavior were integrated rather than replaced.
- The voice media network required a separate UDP path even when Telegram signaling worked.
- Real two-session tests established call, conversational, message/media, and completion-call
  behavior; release claims still require current evidence after material changes.
