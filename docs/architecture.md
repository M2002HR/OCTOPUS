# Voice and Telethon subsystem architecture

This document describes `src/voice_agent`, the legacy-compatible private call/message subsystem.
For the Bot/Codex platform see [System architecture](ARCHITECTURE.md).

## Components

```text
Telegram peer
  <-> private-call signaling (Telethon)
  <-> encrypted media (PyTgCalls / NTgCalls)
  <-> PCM frames -> turn detector -> WAV
  <-> Ajil /v1/audio/transcriptions -> English transcript
  <-> Ajil /v1/chat/completions -> English reply
  <-> Edge TTS + ffmpeg -> Ogg/Opus
  <-> PyTgCalls outbound media
```

`LiveVoiceAssistant` composes concrete adapters. `ConversationOrchestrator` depends on ports for
transcription, chat, synthesis, and persistence, making the conversation pipeline unit-testable
with fakes.

## Module map

| Module | Responsibility |
| --- | --- |
| `config.py` | Root `.env` parsing, defaults, validation, runtime path resolution |
| `domain.py` | Call/turn value objects and valid call-state transitions |
| `audio.py`, `audio_turns.py` | RMS VAD and PCM-to-WAV turn assembly |
| `application.py` | STT → contextual chat → TTS orchestration and stage events |
| `adapters/telegram.py` | Sole Telethon session, numeric allowlist, peer resolution |
| `adapters/uag.py` | Async Ajil STT/chat/image request contract |
| `adapters/edge_tts.py` | Edge TTS and ffmpeg Ogg/Opus conversion |
| `voip.py` | PyTgCalls signaling/media, speaker capture, playback, hangup |
| `messaging.py` | Allowlisted text/voice/photo/reply processing and approved media |
| `completion_calls.py` | Redis consumer group, retry/dedup/recovery |
| `storage.py` | SQLite WAL events, optional transcripts, message turns |
| `observability.py` | Content-safe event values and JSONL |
| `live.py` | Persistent incoming service, locks, lifecycle, completion-call placement |
| `cli.py` | `serve`, explicit outbound test call, and process-file commands |

## Startup and authorization

`serve` validates credentials/policy before network work, opens one Telethon client, resolves every
configured inbound username and message username to numeric IDs, verifies them against
`VOICE_AGENT_ALLOWED_PEER_IDS`, synthesizes the English introduction, and starts:

- incoming-call handler when enabled;
- private-message handler when enabled;
- completion-call Redis consumer when globally enabled.

Unknown callers are declined. Usernames are not compared during an active call; the startup
numeric mapping is authoritative until restart.

## Inbound voice lifecycle

```text
incoming update
  -> numeric caller authorization
  -> single-call busy gate
  -> accept/connect
  -> play "Hello, yes?"
  -> capture PCM
  -> VAD builds bounded utterance
  -> STT / chat / TTS
  -> serialized playback
  -> repeat until peer/user hangup
  -> flush persistence and remove media
```

VAD uses start/continuation hysteresis, sustained-speech threshold, pre-roll, end silence, minimum
utterance, and maximum duration. Frame timing derives from byte length/sample rate/channels.

The language contract is English-only in validation for call STT and compatibility-message STT.
The system prompt prohibits self-introduction. Disclosure can be configured separately for
deployments that require it.

## Private messaging

The same primary account handles one configured peer's text, voice/audio, image/photo, document,
video-caption, and reply-context messages. Text is the default output; `/voice` creates a voice
note and `/text` forces text. Temporary downloads are removed after delivery.

Local image/video sending is manifest-only and path-contained. See [Private messaging](messaging.md).

## Completion calls

The voice service consumes pre-generated terminal requests; it does not generate job status or
open Codex. It resolves the protected numeric target through the existing allowlist, synthesizes
the exact message three times in one audio file, places a call through the primary session, waits
for playback plus a guard, hangs up, and cleans the directory.

The consumer retries failures, acknowledges invalid payloads safely, marks successful job IDs for
deduplication, and repeatedly claims stale pending messages after restart. See
[Completion calls](completion-calls.md).

## Persistence and observability

SQLite runs in WAL mode. `audit_events` records lifecycle state, duration, error class, and safe
metadata. With `VOICE_AGENT_RECORDING_MODE=transcript_only`, `conversation_turns` and
`message_turns` contain sensitive transcript/reply content. `runtime/events.jsonl` is a
tail-friendly content-free event mirror.

No call keys, signaling bytes, provider/Bot tokens, proxy passwords, or Telethon session strings
are persisted. Completion-call audit intentionally omits the spoken status. Per-call incoming/TTS
media and completion audio are temporary and removed from normal/error/cancellation paths.

## Concurrency and cleanup

- only one process/client owns the primary string session;
- the incoming server permits one active call;
- `_turn_lock` serializes STT/chat/TTS/playback;
- `_notification_lock` serializes completion calls;
- a busy active call causes a bounded completion-call retry;
- async HTTP/TTS/Redis work is awaited and time-bounded;
- shutdown stops the completion consumer, message handler, VoIP engine, Telethon client, and
  storage;
- `finally` cleanup removes audio and hangs up even after playback/provider exceptions.

The VAD performs small synchronous PCM calculations; all network and subprocess work remains
asynchronous.

## Network boundary

Telethon proxy settings carry MTProto signaling. PyTgCalls media uses Telegram VoIP reflectors and
may require UDP independently. On the target host, the GOST/SSH media overlay captures UDP inside
the shared namespace and sends it through the required HTTP CONNECT proxy. See
[UDP media overlay](media-overlay.md).
