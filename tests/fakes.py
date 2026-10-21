"""Test doubles."""
from __future__ import annotations

from collections.abc import Callable

from hirelane.providers.base import AiError


class FakeProvider:
    """Returns canned replies. The reply may be a string, a list consumed in order, or a function of the request."""

    name = "fake"

    def __init__(self, reply: str | list[str] | Callable[[str, str], str] = "") -> None:
        self.reply = reply
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str, *, max_tokens: int = 1000) -> str:
        self.calls.append((system, user))
        if callable(self.reply):
            return self.reply(system, user)
        if isinstance(self.reply, list):
            if not self.reply:
                raise AiError("no more replies")
            return self.reply.pop(0)
        return self.reply
