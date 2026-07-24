from voice_agent.english import (
    fallback_reply,
    is_english_output,
    limit_voice_reply,
    normalize_english_output,
)


def test_english_output_guard_accepts_ascii_and_rejects_other_scripts() -> None:
    assert is_english_output("Hello, dear.")
    assert not is_english_output("")
    assert not is_english_output("non-English script: \u0633\u0644\u0627\u0645")
    assert fallback_reply() == "Could you please repeat that?"


def test_english_typography_is_normalized_to_ascii() -> None:
    assert is_english_output("Please confirm the email\u2011based reset flow.")
    assert normalize_english_output("Please confirm the email\u2011based reset flow.") == (
        "Please confirm the email-based reset flow."
    )


def test_voice_reply_limit_ends_at_a_sentence_boundary() -> None:
    response = "First sentence is useful. Second sentence is much too long for this reply."
    assert limit_voice_reply(response, 40) == "First sentence is useful."
