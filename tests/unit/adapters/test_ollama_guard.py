"""OllamaGuardClient (B6): native /api/generate request shape and errors as UpstreamError."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from control_layer.adapters.ollama_guard import OllamaGuardClient
from control_layer.core.errors import UpstreamError

pytestmark = pytest.mark.anyio


def _client(
    handler: Callable[[httpx.Request], httpx.Response],
) -> tuple[OllamaGuardClient, list[Any]]:
    bodies: list[Any] = []

    def record(request: httpx.Request) -> httpx.Response:
        bodies.append((str(request.url), json.loads(request.content)))
        return handler(request)

    http = httpx.AsyncClient(transport=httpx.MockTransport(record))
    return OllamaGuardClient(http, "http://ollama:11434/"), bodies


async def test_generate_sends_raw_prompt_with_keep_alive_and_greedy_decoding() -> None:
    guard, bodies = _client(lambda r: httpx.Response(200, json={"response": "unsafe\nS9"}))
    assert await guard.generate("llama-guard3:1b", "<prompt>", 16) == "unsafe\nS9"
    url, body = bodies[0]
    assert url == "http://ollama:11434/api/generate"
    assert body == {
        "model": "llama-guard3:1b",
        "prompt": "<prompt>",
        "raw": True,
        "stream": False,
        "keep_alive": -1,
        "options": {"temperature": 0, "num_predict": 16},
    }


async def test_load_sends_no_prompt_so_ollama_only_loads_the_model() -> None:
    guard, bodies = _client(lambda r: httpx.Response(200, json={"done": True}))
    await guard.load("llama-guard3:1b")
    assert bodies[0][1] == {"model": "llama-guard3:1b", "keep_alive": -1}


async def test_missing_model_error_text_reaches_the_audit_detail() -> None:
    guard, _ = _client(
        lambda r: httpx.Response(404, json={"error": "model 'llama-guard3:1b' not found"})
    )
    with pytest.raises(UpstreamError, match="404.*not found"):
        await guard.generate("llama-guard3:1b", "p", 16)


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, json={"done": True}),  # no response field
        httpx.Response(200, json={"response": None}),
        httpx.Response(200, json=["safe"]),
        httpx.Response(200, content=b"not json"),
        httpx.Response(500, content=b"boom"),
    ],
    ids=["no-field", "null", "list", "invalid-json", "http-500"],
)
async def test_unusable_answers_raise_instead_of_reading_as_safe(response: httpx.Response) -> None:
    guard, _ = _client(lambda r: response)
    with pytest.raises(UpstreamError, match="^guard: "):
        await guard.generate("m", "p", 16)


async def test_unreachable_ollama_is_an_upstream_error() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    guard, _ = _client(refuse)
    with pytest.raises(UpstreamError, match="unreachable: ConnectError"):
        await guard.load("m")
