# Troubleshooting

## Configuration or startup failures

| Symptom | Check | Resolution |
| --- | --- | --- |
| Missing Telegram configuration | `ConfigurationError` before connection | Set API ID, API hash, and string session in the root `.env`. |
| Proxy configuration failure | error mentions proxy host/port | If the proxy is enabled, provide both a host and a positive port. |
| VAD configuration failure | error mentions `CONTINUE_RMS` | Keep continuation RMS less than or equal to start RMS. |
| Ajil does not become healthy | `docker compose logs uag-gateway` | Check root `UAG_*` values, Docker proxy reachability, provider credentials, and nested submodule checkout. |
| STT returns provider/model errors | inspect Ajil logs and `AI_TRANSCRIPTION_*` | Configure the actual Ajil STT provider/model in root `.env`; the agent sends the language hint to the direct STT route. |
| TTS fails | run `ffmpeg -version` and inspect error event | Install/configure `FFMPEG_BIN`, then verify selected Edge TTS voice and network access. |

## Speech timing problems

If replies start too late, lower `VOICE_AGENT_VAD_END_SILENCE_MS` gradually. If callers are cut off
at natural pauses, raise it. For noise-triggered turns, increase start RMS and minimum utterance
duration. For clipped initial words, increase pre-roll. See the [VAD guide](voice-turn-detection.md)
for ranges and use one setting change per test.

## Telegram VoIP handshake and media

### Another process uses the same session

Telegram delivers private-call updates to the active owner of a user authorization. If a dashboard
or another Telethon client uses the exact same `TELEGRAM_STRING_SESSION`, the agent can ring the
peer but fail to receive the acceptance/signaling updates. Symptoms often include remaining on
“Exchanging encryption keys.”

Stop only the conflicting process/container for the manual test, run the agent, then restore it.
For a durable deployment, create and authorize a dedicated Telegram session for the voice agent.
Do not run two concurrent private-call clients on one session.

### Signaling arrives but `call.active` never appears

If audit logs show `telegram.raw.call_update` and one or more
`telegram.raw.call_update`/`UpdatePhoneCallSignalingData` events but the process raises
`ntgcalls.TelegramServerError` before `call.active`, session ownership has been fixed but the
media transport did not connect. PyTgCalls/NTgCalls uses Telegram VoIP servers independently of
the Telethon signaling transport. A SOCKS proxy that handles TCP signaling does not automatically
tunnel the media path.

Ask the network operator to permit outbound Telegram VoIP reflector traffic, including the UDP
path and its required TCP fallback, and test from the same host/container network namespace. Do
not open broad inbound firewall rules: the agent only needs outbound connectivity. After a network
change, rerun the manual live-call test with the competing session owner stopped. A successful
test must produce `call.active`, inbound `StreamFrames`/turn events, and a heard TTS reply.

## Audit investigation

Use the call ID and trace ID from JSONL to query `audit_events`. Error events expose only an error
class, intentionally. Do not add raw request bodies, signaling data, keys, session values, or
transcript text to the JSONL stream to make diagnosis easier; use the protected SQLite transcript
table only if transcript retention is enabled and authorized.
