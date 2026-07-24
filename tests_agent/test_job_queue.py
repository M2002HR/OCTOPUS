from telegram_codex_agent.jobs.queue import RedisStreamJobQueue


def test_stream_message_decoder_supports_text_and_byte_responses() -> None:
    assert RedisStreamJobQueue._decode(
        [
            ("1-0", {"job_id": "job-1"}),
            (b"2-0", {b"job_id": b"job-2"}),
        ]
    ) == [("1-0", "job-1"), ("2-0", "job-2")]
