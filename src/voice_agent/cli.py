from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from voice_agent.adapters.edge_tts import EdgeSpeechSynthesizer
from voice_agent.adapters.uag import UAGClient
from voice_agent.application import ConversationOrchestrator
from voice_agent.config import Settings
from voice_agent.domain import AudioTurn
from voice_agent.live import LiveVoiceAssistant, wait_for_termination
from voice_agent.storage import AuditStore


def build_orchestrator(
    settings: Settings,
) -> tuple[ConversationOrchestrator, UAGClient, AuditStore]:
    audit = AuditStore(settings.audit_database_path, settings.audit_jsonl_path)
    client = UAGClient(
        base_url=settings.uag_base_url,
        chat_endpoint=settings.uag_chat_endpoint,
        transcriptions_endpoint=settings.uag_transcriptions_endpoint,
        timeout_seconds=settings.uag_timeout_seconds,
        auth_token=settings.uag_auth_token,
        auth_header_name=settings.uag_auth_header_name,
        models=settings.chat_models,
        providers=settings.chat_providers,
        transcription_provider=settings.transcription_provider,
        transcription_models=settings.transcription_models,
    )
    orchestrator = ConversationOrchestrator(
        transcriber=client,
        brain=client,
        synthesizer=EdgeSpeechSynthesizer(
            voice=settings.edge_voice, rate=settings.edge_rate, ffmpeg_bin=settings.ffmpeg_bin
        ),
        audit=audit,
        system_prompt=settings.system_prompt,
        output_dir=settings.runtime_dir / "tts",
        max_history_messages=settings.max_history_messages,
        persist_transcripts=settings.recording_mode == "transcript_only",
    )
    return orchestrator, client, audit


async def _process_file(args: argparse.Namespace) -> None:
    settings = Settings.load(Path(args.env) if args.env else None)
    app, client, audit = build_orchestrator(settings)
    try:
        result = await app.process(
            AudioTurn(
                call_id=args.call_id,
                audio_path=Path(args.audio),
                mime_type=args.mime,
                language=args.language,
            )
        )
        print(result.reply)
        print(result.audio_path)
    finally:
        await client.aclose()
        audit.close()


async def _call(args: argparse.Namespace) -> None:
    settings = Settings.load(Path(args.env) if args.env else None)
    assistant = LiveVoiceAssistant(settings)
    try:
        await assistant.place_test_call(args.username)
        await wait_for_termination()
    finally:
        await assistant.close()


def main() -> None:
    parser = argparse.ArgumentParser(prog="telegram-voice-agent")
    sub = parser.add_subparsers(dest="command", required=True)
    process = sub.add_parser(
        "process-file", help="Process a captured test utterance through STT, AI, and TTS"
    )
    process.add_argument("audio")
    process.add_argument("--call-id", default="manual-test")
    process.add_argument("--language", default="fa")
    process.add_argument("--mime", default="audio/ogg")
    process.add_argument("--env")
    call = sub.add_parser("call", help="Place one explicitly requested allowlisted test call")
    call.add_argument("--username", required=True)
    call.add_argument("--env")
    args = parser.parse_args()
    if args.command == "process-file":
        asyncio.run(_process_file(args))
    if args.command == "call":
        asyncio.run(_call(args))


if __name__ == "__main__":
    main()
