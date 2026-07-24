# Agent instructions

`telegram-codex-agent` is a personal Telegram AI agent with a native full-access control plane,
Ajil as a pinned recursive submodule, Codex App Server integration, a persistent job system, and
a legacy-compatible Telethon voice-call subsystem.

- Use only `config/agent.yaml` for non-secret policy and the root `.env` for all secrets.
- `modules/ajil_uag` is a submodule. Do not edit it directly; make reproducible upstream patches.
- Development full access is intentional. Do not widen its scope to unrelated user projects.
- Keep async code non-blocking, add timeouts, and always clean up subprocesses/browser resources.
- Run relevant tests, Ruff, and mypy after changes. Update migrations for persistent model changes.
- Update `.env.example`, config schema, docs, and implementation status with every configuration change.
- Preserve `src/voice_agent`; it is the validated private-call compatibility component.
- Never commit secrets or claim an integration passed without recorded evidence.
