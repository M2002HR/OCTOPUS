# Troubleshooting

## Platform does not become ready

```bash
docker compose --profile agent ps
docker compose --profile agent logs --tail=300 \
  postgres redis ajil_gateway agent-migrate agent-api agent-bot agent-worker
curl --noproxy '*' http://127.0.0.1:18090/ready
```

| Symptom | Check | Resolution |
| --- | --- | --- |
| PostgreSQL unhealthy | password, port, volume, `pg_isready` | Keep `POSTGRES_*` and `DATABASE_URL` consistent; protect existing volume |
| Migration failed | `agent-migrate` logs | Fix forward migration/config; do not delete data or rewrite applied migration |
| Redis unhealthy | AOF/volume/port logs | Restore Redis, then reconcile Streams against PostgreSQL |
| Ajil unhealthy | provider/proxy/Redis/submodule logs | Initialize recursive submodules and validate root `UAG_*` |
| API live but not ready | `/ready` check map | Restore only failed dependency |
| Wrong Compose names/ports | rendered config | Use `docker compose --profile agent config`, not stale `uag-gateway` examples |

## Bot is silent

- Confirm `agent-bot` is running and only one poller uses the Bot token.
- Validate `TELEGRAM_BOT_TOKEN`, user/chat allowlists, polling/webhook choice, and Bot proxy.
- Polling is default. Webhook requires a public URL and secret.
- Inspect Bot logs for Telegram 401/409/proxy errors.
- Restart Bot after token/proxy/transport/global-policy change.

Settings persist only after the Bot has registered the user through a normal message/job. If a
button says “Send one task first,” create the context first.

## Workspace/session/task problems

| Symptom | Cause/check |
| --- | --- |
| “Select a workspace” | Use `/projects`; arbitrary Telegram paths are rejected |
| Project missing | Check `WORKSPACE_ROOT_HOST` mount, `workspace.max_depth`, Git directory, registry |
| Resume thread unavailable | Verify owner/project scope and persisted `codex_threads` |
| Session says RUNNING forever | Inspect latest job heartbeat, Redis pending, worker logs |
| History/log missing | Confirm correct user/chat/session and pagination |
| Attachment unavailable | Check deterministic inbox path, download error, size, MIME, containment |

## Codex App Server

```bash
agentctl codex status
agentctl codex smoke
docker compose --profile agent logs --tail=300 agent-worker
```

| Symptom | Resolution |
| --- | --- |
| Binary missing | Check `CODEX_HOST_RUNTIME`, `CODEX_BINARY`, container `PATH` |
| Not authenticated | Verify protected `CODEX_HOME_HOST` mount and host Codex login |
| Outbound request timeout | Configure `CODEX_HTTP_PROXY_URL`; it is separate from Bot/Telethon/Ajil |
| Model/effort did not change | Confirm preference via `/status`; it applies to newly created jobs/turns |
| Fast cannot enable | Model catalog unavailable or selected model does not advertise Fast |
| Approval request hangs | Inspect deterministic approval bridge/policy; never leave App Server request unanswered |
| Cancellation does not finish | Confirm persisted `cancel_requested`, thread/turn IDs, and `turn/interrupt` |
| Weekly usage unavailable | `/usage` depends on `account/rateLimits/read`, not thread token events |
| Rate limit/auth error | Treat as terminal category; do not retry indefinitely |

## Job queue and restart recovery

Inspect Redis groups and PostgreSQL job state. A pending entry with an active heartbeat is normal.
If worker died, restart it and let pending reclaim/lease recovery run. Terminal database state
wins; do not manually duplicate Stream entries.

If Redis publish failed after job creation, the database row is still authoritative. Use the
recovery/republish path rather than creating a second user job.

## Browser/artifact

- Confirm project actually has browser/Chrome Lab/Playwright tooling.
- Check `CHROME_CDP_ENDPOINT` and dedicated browser profile.
- Confirm application URL/process is reachable from worker host network.
- A screenshot directive must be absolute, exist, stay inside approved roots, and fit upload cap.
- Do not claim success from an empty/error-page screenshot; inspect it.
- On cancellation, check no server/browser subprocess remains.

## Ajil, STT, and TTS

| Symptom | Check |
| --- | --- |
| Ajil provider/model error | gateway `/health`, provider keys, models/providers, router retries |
| STT error | `AI_TRANSCRIPTION_*`, Groq STT model/language, audio format |
| Vision error | `VOICE_AGENT_VISION_*` selects an image-capable Gemini model/provider |
| Edge TTS error | selected voice, network, FFmpeg executable |
| Temporary 5xx/504 | bounded retry where implemented; do not turn an integration failure into success |

## Codex completion call

### No call after job stops

Check:

1. job used Codex;
2. user enabled `/completion_call on` before job creation;
3. global `CODEX_COMPLETION_CALLS_ENABLED=true`;
4. target numeric Bot user ID is in `VOICE_AGENT_ALLOWED_PEER_IDS`;
5. worker recorded `completion_call.queued` rather than skipped/failed;
6. voice consumer is ready and stream/group names match;
7. primary Telethon session is connected and exclusively owned.

```bash
docker compose --profile agent logs --tail=300 agent-worker voice-agent
docker compose exec -T redis redis-cli -n 1 \
  XINFO GROUPS telegram_codex_agent.completion_calls
docker compose exec -T redis redis-cli -n 1 \
  XPENDING telegram_codex_agent.completion_calls voice_agent.completion_calls
```

### Pending does not clear after restart

Pending younger than the 30-second stale-claim window is expected briefly. The consumer checks
`XAUTOCLAIM` on every poll, so it should recover once stale. Confirm service remains running and
stream/group match. Do not manually acknowledge before checking whether the call occurred.

### Duplicate call after crash

Normal duplicates are suppressed. A process crash after audible playback but before setting the
delivered marker can cause one recovered repeat; this is the documented at-least-once boundary.

### Call retries as busy

An inbound/normal/completion call already owns the media engine. Wait for it to end; bounded retry
will continue. Increasing attempts without addressing a permanently busy owner is not a fix.

### Message wrong/not three times

The request schema fixes repeat count to three and TTS uses one Ajil/fallback message repeated in
one payload. Inspect job source/category and run the live recording/STT harness. Voice audit
intentionally does not contain the spoken text.

## Voice startup/configuration

| Symptom | Resolution |
| --- | --- |
| Missing API/session | Fill primary `TELEGRAM_API_ID/HASH/STRING_SESSION` in root `.env` |
| Proxy loopback from container | Use Docker host endpoint values, not `127.0.0.1` |
| Caller rejected | Username must resolve at startup and numeric ID must be allowlisted |
| Non-English config rejected | Telethon call/message language is intentionally enforced to `en` |
| VAD invalid | continuation RMS ≤ start RMS; respect validation minimums |
| Service restart loop | inspect credentials, allowlist resolution, Ajil/TTS intro generation |

## Telegram VoIP handshake and media

### Stuck at “Exchanging encryption keys”

The primary authorization is probably active in another Telethon client/process. Stop the
conflicting owner. Never run two call clients on one string session.

### Signaling works but `call.active` does not

PyTgCalls media is independent from Telethon proxy signaling. Run the overlay STUN preflight inside
the voice namespace and inspect media sidecars. Permit required outbound UDP/TCP fallback without
opening broad inbound rules.

### Call active but speech is missed

Inspect frame/turn/STT events. Tune VAD one value at a time:

- clipped beginning: increase pre-roll;
- ignored quiet voice: lower start/continue RMS;
- noise turns: raise RMS/minimum utterance;
- replies too late: lower end silence;
- mid-sentence interruption: raise end silence.

See [Voice turn detection](voice-turn-detection.md).

## Audit investigation

Use trace/job/call IDs and timestamps. Do not add raw prompts, transcript, signaling, keys, session
values, or provider bodies to JSONL to simplify debugging. Query protected content stores only when
authorized. Rotate credentials immediately if they appear in any artifact/log/chat.
