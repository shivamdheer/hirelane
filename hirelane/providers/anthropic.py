"""Anthropic Messages API backend."""
from __future__ import annotations

import httpx

from .base import AiError

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: str, model: str, timeout_s: int = 120, transport: httpx.BaseTransport | None = None,
                 base_url: str = API_URL) -> None:
        if not api_key:
            raise AiError("no API key, run `hirelane set-key ai-api-key`")
        if not model:
            raise AiError("set ai.model in config/settings.yaml")
        self.model = model
        self.base_url = base_url
        self._key = api_key
        self._client = httpx.Client(timeout=timeout_s, transport=transport)

    def complete(self, system: str, user: str, *, max_tokens: int = 1000) -> str:
        body = {"model": self.model, "max_tokens": max_tokens, "system": system,
                "messages": [{"role": "user", "content": user}]}
        headers = {"x-api-key": self._key, "anthropic-version": API_VERSION, "content-type": "application/json"}
        try:
            r = self._client.post(self.base_url, json=body, headers=headers)
        except httpx.HTTPError as e:
            raise AiError(f"request failed: {type(e).__name__}") from e
        if r.status_code != 200:
            raise AiError(f"the API returned HTTP {r.status_code}")
        try:
            parts = r.json()["content"]
            return "".join(p.get("text", "") for p in parts if p.get("type") == "text")
        except (ValueError, KeyError, TypeError, AttributeError) as e:
            raise AiError("unexpected reply shape") from e
