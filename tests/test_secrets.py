from __future__ import annotations

import pytest

from hirelane import secrets
from tests.conftest import MemoryKeyring


def test_roundtrip_uses_the_hirelane_service(fake_keyring: MemoryKeyring) -> None:
    secrets.set_secret(secrets.AI_KEY, "sk-example")
    assert secrets.get_secret(secrets.AI_KEY) == "sk-example"
    assert list(fake_keyring.store) == [("hirelane", "ai-api-key")]


def test_missing_secret_is_none_and_delete_reports_it(fake_keyring: MemoryKeyring) -> None:
    assert secrets.get_secret("nothing") is None
    assert not secrets.delete_secret("nothing")
    secrets.set_secret("x", "1")
    assert secrets.delete_secret("x")


def test_empty_values_are_refused() -> None:
    with pytest.raises(secrets.SecretsError):
        secrets.set_secret(secrets.AI_KEY, "")


def test_describe_never_returns_values(fake_keyring: MemoryKeyring) -> None:
    secrets.set_secret(secrets.WEB_TOKEN, "hunter2")
    state = secrets.describe()
    assert state[secrets.WEB_TOKEN] is True and state[secrets.AI_KEY] is False
    assert "hunter2" not in str(state)


def test_an_environment_variable_overrides_the_keyring_for_containers(monkeypatch: pytest.MonkeyPatch) -> None:
    secrets.set_secret(secrets.WEB_TOKEN, "from-keyring")
    monkeypatch.setenv("HIRELANE_SECRET_WEB_TOKEN", "from-env")
    assert secrets.get_secret(secrets.WEB_TOKEN) == "from-env"
    assert secrets.env_name("ai-api-key") == "HIRELANE_SECRET_AI_API_KEY"
