from __future__ import annotations

import pytest

from hirelane import secrets
from hirelane.config import AiSettings
from hirelane.providers import LimitedProvider, get_provider
from hirelane.providers.base import AiError
from tests.fakes import FakeProvider


def test_limited_provider_stops_at_the_limit() -> None:
    p = LimitedProvider(FakeProvider("x"), 2)
    assert p.complete("s", "u") == "x" and p.complete("s", "u") == "x"
    with pytest.raises(AiError, match="limit of 2"):
        p.complete("s", "u")


def test_factory_chooses_backends_and_degrades_to_none() -> None:
    assert get_provider(AiSettings()) is None
    assert get_provider(AiSettings(provider="anthropic", model="<model-id>")) is None        # no key stored yet
    secrets.set_secret(secrets.AI_KEY, "k")
    anth = get_provider(AiSettings(provider="anthropic", model="<model-id>"))
    assert anth is not None and anth.name == "anthropic"
    assert get_provider(AiSettings(provider="openai", model="")) is None                      # no model
    oai = get_provider(AiSettings(provider="openai", model="<model-id>"))
    assert oai is not None and oai.name == "openai"
    local = get_provider(AiSettings(provider="compatible", model="<m>", base_url="http://localhost:11434/v1"))
    assert local is not None and local.name == "compatible"
