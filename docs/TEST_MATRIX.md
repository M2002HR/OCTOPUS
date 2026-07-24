# Test and evidence matrix

Claims in documentation and release notes must be backed by the strongest applicable layer.
Ordinary CI uses fakes and requires no Telegram/provider credentials. Live tests are explicit,
allowlisted, and must preserve content-safe evidence.

| Capability | Automated coverage | Integration/live evidence |
| --- | --- | --- |
| YAML/environment validation and redaction | `tests_agent/test_config_and_jobs.py`, `tests/test_config.py` | `agentctl config validate`, `/config/redacted` |
| Job state machine and cancellation | `tests_agent` job/worker tests | Real Codex cancellation and durable events |
| Redis publish, consumer groups, recovery | queue/worker tests | Redis `XPENDING`/`XINFO`, restart recovery |
| Codex JSON-RPC lifecycle | App Server contract tests | `agentctl codex smoke`, real read-only job |
| Model/reasoning/Fast snapshots | config/UI/worker tests | Bot settings followed by `/status` and real turn |
| Codex weekly usage | usage formatting/cache tests | `/usage` against authenticated App Server |
| Session status/history/log pagination | repository/UI tests | `/resume`, `/history`, `/logs` on real jobs |
| Ajil chat/STT clients | HTTP contract tests | `make ajil-smoke`, `process-file` |
| Bot command/keyboard routing | `tests_agent/test_telegram_ui.py` | second-session Bot E2E |
| Bot voice/image/document normalization | normalization/worker tests | approved attachment matrix |
| Memory ownership and retrieval | memory/repository tests | `/remember`, `/memory`, `/forget` |
| Browser artifact handoff | artifact/directive tests | real workspace screenshot delivered to Telegram |
| Voice VAD/STT/chat/TTS | `tests/` audio/application tests | approved two-account call |
| Telethon private messaging/reply context | messaging tests | two-account text/voice/photo/reply matrix |
| Completion-call categories/redaction | `tests_agent/test_completion_calls.py` | real Codex terminal call |
| Completion-call retry/recovery/privacy | `tests/test_completion_call_consumer.py` | restart recovery, Redis pending returns to zero |
| Media overlay | script/config checks | in-namespace STUN preflight and successful call media |

## Required local quality gates

```bash
RUFF_CACHE_DIR=/tmp/octopus-ruff-cache ruff check src tests tests_agent scripts
PYTHONPYCACHEPREFIX=/tmp/octopus-pycache python -m compileall -q src scripts tests tests_agent
python -m mypy src
python -m pytest -q
docker compose --profile agent config --quiet
git diff --check
```

If a tool itself crashes, record its exact version and internal failure separately; do not report
that gate as passed. If an unrelated pre-existing lint finding remains, identify its file and keep
the changed-file result distinct from the full-repository result.

## Live-test rules

- Use only the configured primary and test Telegram identities.
- Confirm numeric allowlists before calling or sending.
- The production voice process exclusively owns the primary Telethon session.
- Set only the required `RUN_LIVE_*` flag.
- Use a disposable/read-only task unless mutation is the explicit subject of the test.
- Bound every wait and subprocess; always hang up/cleanup in `finally`.
- Store audio, screenshots, and provider responses only under ignored runtime paths.
- Preserve safe facts: job ID, event types, durations, hashes, pass/fail, and redacted transcript
  assertions. Never commit content or credentials.

## Completion-call acceptance

A live completion-call test is successful only when all of these are true:

1. the second account enables the setting through the real Bot;
2. a real Codex job reaches a terminal state;
3. the job event says the message source was Ajil or an explicitly tested fallback;
4. the primary Telethon session calls the second account;
5. the second session answers and receives audio;
6. STT/repetition analysis confirms the terminal message was spoken three times;
7. Telegram hangs up without manual intervention;
8. `completion_call.delivered` is audited without message content;
9. Redis pending and lag return to zero.

## Release evidence template

Record:

- commit/branch and environment date;
- Python, Codex, Docker, PyTgCalls, and Ajil submodule versions;
- commands run and exact pass counts;
- live scenario and approved identities in redacted form;
- service health and queue state;
- known warnings/tool failures;
- whether runtime artifacts were retained or deleted.
