from voice_agent.adapters.edge_tts import EdgeSpeechSynthesizer


def test_edge_tts_always_uses_the_configured_english_voice() -> None:
    synthesizer = EdgeSpeechSynthesizer(
        voice="en-US-AndrewMultilingualNeural",
        rate="+0%",
        ffmpeg_bin="ffmpeg",
    )

    assert synthesizer._voice_for("Hello", None) == "en-US-AndrewMultilingualNeural"
