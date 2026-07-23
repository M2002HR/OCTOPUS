from voice_agent.language import language_hint


def test_language_hint_prefers_persian_and_kurdish_scripts() -> None:
    assert language_hint("سلام، حالت چطوره؟") == "fa"
    assert language_hint("سڵاو، چۆنی؟") == "ckb"


def test_language_hint_uses_male_voice_map_languages() -> None:
    assert language_hint("Hello there") == "en"
    assert language_hint("Merhaba") == "en"
    assert language_hint("Merhaba, nas\u0131ls\u0131n?") == "tr"
    assert language_hint("مرحبا") == "ar"
