from voice_agent.observability import Event


def test_event_redacts_secret_details() -> None:
    payload = Event("test", "trace", details={"token": "secret", "safe": "yes"}).payload()
    assert payload["details"] == {"token": "[REDACTED]", "safe": "yes"}
