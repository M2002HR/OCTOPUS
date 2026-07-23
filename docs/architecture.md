# Architecture

## Components

```text
Telegram peer
  <-> Telegram private-call signaling (Telethon)
  <-> encrypted media (PyTgCalls / NTgCalls)
  <-> PCM frames -> turn detector -> WAV
  <-> Ajil /v1/audio/transcriptions -> transcript
  <-> Ajil /v1/chat/completions -> reply text
  <-> Edge TTS + ffmpeg -> Ogg/Opus
  <-> PyTgCalls outbound media
```

`LiveVoiceAssistant` composes the concrete adapters. `ConversationOrchestrator` is independent
of Telegram and has ports for transcription, chat, speech synthesis, and persistence. This keeps
the conversation pipeline unit-testable with fakes.

## Modules

- `config.py`: root `.env` parsing and early validation.
- `domain.py`: call and turn value objects plus valid call-state transitions.
- `audio.py` and `audio_turns.py`: RMS VAD and PCM-to-WAV turn assembly.
- `application.py`: STT -> contextual chat -> TTS orchestration and stage events.
- `adapters/telegram.py`: authorized Telethon session and allowlist resolution.
- `adapters/uag.py`: Ajil OpenAI-compatible STT and chat client.
- `adapters/edge_tts.py`: Edge TTS plus ffmpeg Ogg/Opus conversion.
- `voip.py`: PyTgCalls private-call adapter, speaker capture, and media playback.
- `storage.py`: append-only SQLite events, conversation turns, and JSONL event mirror.

## Persistence and observability

SQLite uses WAL mode. `audit_events` records lifecycle states, durations, safe metadata, and
errors. With `VOICE_AGENT_RECORDING_MODE=transcript_only`, `conversation_turns` stores
transcript/reply pairs and historical media paths for analytics.
`runtime/events.jsonl` is a tail-friendly mirror of events. Event redaction protects known secret
field names; do not put secrets in custom event values.

No call keys, signaling bytes, API tokens, or session strings are persisted. Raw audio lives under
`runtime/incoming/` only during an active call; output audio behaves likewise under
`runtime/tts/` and `runtime/intro/`. Per-call media is deleted when the live assistant closes.

## Concurrency

Telegram has one outbound media stream per private call. `LiveVoiceAssistant` serializes completed
speech turns with an async lock, preventing a later answer from replacing an earlier response.
The VAD runs synchronously on small PCM frames; HTTP and TTS operations are asynchronous.
