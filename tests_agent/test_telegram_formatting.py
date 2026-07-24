from telegram_codex_agent.telegram.formatting import split_telegram_text


def test_telegram_text_is_split_below_limit() -> None:
    text = "word " * 100
    chunks = split_telegram_text(text, limit=60)
    assert len(chunks) > 1
    assert all(len(chunk) <= 60 for chunk in chunks)
    assert "".join(f"{chunk} " for chunk in chunks).replace("  ", " ").strip() == text.strip()
