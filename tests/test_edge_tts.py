from voice_agent.adapters.edge_tts import EdgeSpeechSynthesizer


def test_edge_tts_selects_configured_male_voice_for_detected_language() -> None:
    synthesizer = EdgeSpeechSynthesizer(
        voice="fa-IR-FaridNeural",
        voices_by_language={
            "fa": "fa-IR-FaridNeural",
            "ckb": "fa-IR-FaridNeural",
            "en": "en-US-AndrewMultilingualNeural",
        },
        rate="+0%",
        ffmpeg_bin="ffmpeg",
    )

    assert synthesizer._voice_for("سلام", None) == "fa-IR-FaridNeural"
    assert synthesizer._voice_for("Hello", None) == "en-US-AndrewMultilingualNeural"
    assert synthesizer._voice_for("سڵاو", None) == "fa-IR-FaridNeural"
