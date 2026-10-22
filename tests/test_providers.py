from __future__ import annotations

import json

import httpx
import pytest

from hirelane.providers.anthropic import AnthropicProvider
from hirelane.providers.base import AiError
from hirelane.providers.openai import OpenAIProvider


def transport(status: int, payload: object, seen: list[httpx.Request] | None = None) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return httpx.Response(status, json=payload)

    return httpx.MockTransport(handler)


def test_anthropic_request_and_reply() -> None:
    seen: list[httpx.Request] = []
    t = transport(200, {"content": [{"type": "text", "text": "Hello "}, {"type": "text", "text": "there"}]}, seen)
    p = AnthropicProvider("key-123", "<model-id>", transport=t)
    assert p.complete("be brief", "hi", max_tokens=50) == "Hello there"
    (req,) = seen
    body = json.loads(req.content)
    assert req.headers["x-api-key"] == "key-123" and req.headers["anthropic-version"] == "2023-06-01"
    assert body == {"model": "<model-id>", "max_tokens": 50, "system": "be brief",
                    "messages": [{"role": "user", "content": "hi"}]}


def test_openai_request_and_reply() -> None:
    seen: list[httpx.Request] = []
    t = transport(200, {"choices": [{"message": {"content": "Hi!"}}]}, seen)
    p = OpenAIProvider("key-abc", "<model-id>", transport=t)
    assert p.complete("sys", "hello") == "Hi!"
    (req,) = seen
    assert str(req.url) == "https://api.openai.com/v1/chat/completions"
    assert req.headers["authorization"] == "Bearer key-abc"
    assert json.loads(req.content)["messages"][0] == {"role": "system", "content": "sys"}


def test_compatible_endpoint_needs_no_key() -> None:
    seen: list[httpx.Request] = []
    t = transport(200, {"choices": [{"message": {"content": "ok"}}]}, seen)
    p = OpenAIProvider("", "<local-model>", "http://localhost:11434/v1/", transport=t, require_key=False)
    assert p.complete("s", "u") == "ok"
    assert str(seen[0].url) == "http://localhost:11434/v1/chat/completions"
    assert "authorization" not in seen[0].headers


@pytest.mark.parametrize("factory", [
    lambda t: AnthropicProvider("k", "<model-id>", transport=t),
    lambda t: OpenAIProvider("k", "<model-id>", transport=t),
])
@pytest.mark.parametrize("status,payload", [(401, {}), (500, {}), (200, {"unexpected": True}), (200, [])])
def test_failures_become_ai_errors_without_leaking_the_key(factory, status: int, payload: object) -> None:
    p = factory(transport(status, payload))
    with pytest.raises(AiError) as info:
        p.complete("s", "u")
    assert str(info.value) != "k"
    assert "Bearer" not in str(info.value)


def test_network_errors_become_ai_errors() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(AiError, match="ConnectError"):
        OpenAIProvider("k", "<model-id>", transport=httpx.MockTransport(boom)).complete("s", "u")


def test_missing_key_or_model_is_refused() -> None:
    with pytest.raises(AiError, match="set-key"):
        AnthropicProvider("", "<model-id>")
    with pytest.raises(AiError, match=r"ai\.model"):
        OpenAIProvider("k", "")
