"""OpenAI chat completions backend, also used for any OpenAI-compatible server such as a local Ollama."""
from __future__ import annotations

import httpx

from .base import AiError

OPENAI_URL = "https://api.openai.com/v1"


class OpenAIProvider:
    name = "openai"

    def __init__(self, api_key: str, model: str, base_url: str = OPENAI_URL, timeout_s: int = 120,
                 transport: httpx.BaseTransport | None = None, require_key: bool = True, name: str = "openai") -> None:
        if require_key and not api_key:
            raise AiError("no API key, run `hirelane set-key ai-api-key`")
        if not model:
            raise AiError("set ai.model in config/settings.yaml")
        self.name = name
        self.model = model
        self.url = base_url.rstrip("/") + "/chat/completions"
        self._key = api_key
        self._client = httpx.Client(timeout=timeout_s, transport=transport)

    def complete(self, system: str, user: str, *, max_tokens: int = 1000) -> str:
        body = {"model": self.model, "max_tokens": max_tokens,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        headers = {"content-type": "application/json"}
        if self._key:
            headers["authorization"] = f"Bearer {self._key}"
        try:
            r = self._client.post(self.url, json=body, headers=headers)
        except httpx.HTTPError as e:
            raise AiError(f"request failed: {type(e).__name__}") from e
        if r.status_code != 200:
            raise AiError(f"the API returned HTTP {r.status_code}")
        try:
            return str(r.json()["choices"][0]["message"]["content"] or "")
        except (ValueError, KeyError, IndexError, TypeError) as e:
            raise AiError("unexpected reply shape") from e
