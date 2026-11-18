"""Configuration defaults must fail closed on network exposure."""

from app.core.config import Settings


def test_default_bind_is_loopback(monkeypatch):
    monkeypatch.delenv("HOST", raising=False)
    assert Settings(_env_file=None).HOST == "127.0.0.1"
