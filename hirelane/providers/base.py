"""The interface every AI backend implements.

Everything that can call a model goes through ``Provider``. With no provider configured the pipeline still runs,
using deterministic code in place of each model step.
"""
from __future__ import annotations

import json
import re
from typing import Any, Protocol


class AiError(RuntimeError):
    """The provider failed, timed out, or is not configured. Callers fall back to the non-AI path."""


class Provider(Protocol):
    name: str

    def complete(self, system: str, user: str, *, max_tokens: int = 1000) -> str:
        """Send one request and return the text of the reply."""
        ...


FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.I)


def parse_json_reply(text: str) -> Any:
    """Parse a JSON reply, tolerating a code fence or text around the object. Raises AiError when there is none."""
    cleaned = FENCE.sub("", (text or "").strip())
    for candidate in (cleaned, _outer(cleaned, "{", "}"), _outer(cleaned, "[", "]")):
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except ValueError:
            continue
    raise AiError("the reply was not valid JSON")


def _outer(text: str, open_ch: str, close_ch: str) -> str:
    start, end = text.find(open_ch), text.rfind(close_ch)
    return text[start: end + 1] if 0 <= start < end else ""


def complete_json(provider: Provider, system: str, user: str, *, max_tokens: int = 1000) -> Any:
    return parse_json_reply(provider.complete(system, user, max_tokens=max_tokens))


def untrusted(label: str, text: str) -> str:
    """Wrap text that came from a web page or an email so the model treats it as data, not as instructions."""
    safe = (text or "").replace("</data>", "")
    return f'<data label="{label}">\n{safe}\n</data>'
