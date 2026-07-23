from __future__ import annotations

import importlib.util
from pathlib import Path


def _module():
    path = Path("scripts/provision_media_relay.py")
    spec = importlib.util.spec_from_file_location("provision_media_relay", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_upsert_env_preserves_other_entries_and_permissions(tmp_path: Path) -> None:
    module = _module()
    env = tmp_path / ".env"
    env.write_text("KEEP=this\nVOICE_AGENT_MEDIA_SSH_HOST=old\n")

    module.upsert_env(env, {"VOICE_AGENT_MEDIA_SSH_HOST": "new", "ADDED": "yes"})

    assert env.read_text() == "KEEP=this\nVOICE_AGENT_MEDIA_SSH_HOST=new\nADDED=yes\n"
    assert env.stat().st_mode & 0o777 == 0o600


def test_media_overlay_defaults_use_private_relay_and_docker_proxy() -> None:
    module = _module()

    assert module.DEFAULTS["VOICE_AGENT_MEDIA_PROXY_HOST"] == "host.docker.internal"
    assert module.DEFAULTS["VOICE_AGENT_MEDIA_PROXY_PORT"] == "32080"
    assert module.DEFAULTS["VOICE_AGENT_MEDIA_RELAY_REMOTE_PORT"] == "8442"


def test_stun_probe_validates_matching_binding_success(monkeypatch, capsys) -> None:
    path = Path("scripts/media_overlay_stun_probe.py")
    spec = importlib.util.spec_from_file_location("media_overlay_stun_probe", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    transaction_id = b"a" * 12

    class FakeSocket:
        def settimeout(self, value: float) -> None:
            assert value == 10

        def sendto(self, data: bytes, target: tuple[str, int]) -> None:
            assert data.endswith(transaction_id)
            assert target == ("203.0.113.10", 19302)

        def recvfrom(self, size: int) -> tuple[bytes, tuple[str, int]]:
            return b"\x01\x01\x00\x00\x21\x12\xa4\x42" + transaction_id, ("203.0.113.10", 19302)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback) -> None:
            return None

    monkeypatch.setattr(module.secrets, "token_bytes", lambda size: transaction_id)
    monkeypatch.setattr(
        module.socket,
        "getaddrinfo",
        lambda *args: [(None, None, None, None, ("203.0.113.10", 19302))],
    )
    monkeypatch.setattr(module.socket, "socket", lambda *args: FakeSocket())

    module.main()

    assert capsys.readouterr().out == "media overlay STUN preflight passed\n"
