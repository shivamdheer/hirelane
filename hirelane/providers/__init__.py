"""AI providers behind one interface. The user picks one in config/settings.yaml."""
from __future__ import annotations

import httpx

from .. import secrets
from ..config import AiSettings
from .anthropic import AnthropicProvider
from .base import AiError, Provider
from .openai import OpenAIProvider

__all__ = ["AiError", "LimitedProvider", "Provider", "get_provider"]


class LimitedProvider:
    """Stops after a fixed number of calls in one run, so a loop can never run up a bill."""

    def __init__(self, inner: Provider, max_calls: int) -> None:
        self.inner = inner
        self.name = inner.name
        self.max_calls = max_calls
        self.calls = 0

    def complete(self, system: str, user: str, *, max_tokens: int = 1000) -> str:
        if self.calls >= self.max_calls:
            raise AiError(f"call limit of {self.max_calls} reached for this run")
        self.calls += 1
        return self.inner.complete(system, user, max_tokens=max_tokens)


def get_provider(ai: AiSettings, transport: httpx.BaseTransport | None = None) -> Provider | None:
    """The configured provider, or None when AI is off or not usable.

    A missing key or model never raises here. Everything that needs a model has a path without one.
    """
    if ai.provider == "none":
        return None
    key = secrets.get_secret(secrets.AI_KEY) or ""
    try:
        inner: Provider
        if ai.provider == "anthropic":
            inner = AnthropicProvider(key, ai.model, ai.timeout_s, transport)
        elif ai.provider == "openai":
            inner = OpenAIProvider(key, ai.model, timeout_s=ai.timeout_s, transport=transport)
        else:
            inner = OpenAIProvider(key, ai.model, ai.base_url, ai.timeout_s, transport, require_key=False,
                                   name="compatible")
    except AiError:
        return None
    return LimitedProvider(inner, ai.max_calls_per_run)
