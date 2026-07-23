import pytest

from voice_agent.domain import Call, CallState


def test_call_only_allows_valid_lifecycle_transitions() -> None:
    call = Call(peer_id=7, peer_username="test")
    call.transition(CallState.RINGING)
    call.transition(CallState.CONNECTING)
    call.transition(CallState.ACTIVE)
    call.transition(CallState.ENDED)
    assert call.state is CallState.ENDED


def test_call_rejects_invalid_transition() -> None:
    with pytest.raises(ValueError):
        Call(peer_id=7, peer_username=None).transition(CallState.ACTIVE)
