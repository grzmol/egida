"""OllamaClient (F1): every upstream failure is an UpstreamError (502 + audit), never a 500."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from egida.adapters.ollama_client import OllamaClient
from egida.core.errors import UpstreamError
from egida.core.models import Interaction, Message
from egida.core.policy import UpstreamConfig
from egida.core.ports import ModelResult

pytestmark = pytest.mark.anyio

UPSTREAM = UpstreamConfig(base_url="http://ollama:11434/v1", timeout_s=5)
REQUEST = Interaction("r", "a", "llama3.2:3b", (Message("user", "hi"),))


async def _complete(handler: Callable[[httpx.Request], httpx.Response]) -> ModelResult:
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        return await OllamaClient(http).complete(REQUEST, UPSTREAM)


def _raise(exc: type[httpx.TransportError]) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        raise exc("boom", request=request)

    return handler


@pytest.mark.parametrize(
    ("handler", "fragment"),
    [
        (_raise(httpx.ConnectError), "unreachable: ConnectError"),
        (_raise(httpx.ReadTimeout), "unreachable: ReadTimeout"),
        (lambda r: httpx.Response(503, text="overloaded"), "HTTP 503"),
        (lambda r: httpx.Response(200, content=b"<html>"), "invalid JSON"),
        (lambda r: httpx.Response(200, json={"object": "chat.completion"}), "response shape"),
        (lambda r: httpx.Response(200, json={"choices": []}), "response shape"),
    ],
    ids=["refused", "timeout", "5xx", "not-json", "no-choices", "empty-choices"],
)
async def test_upstream_failures_are_upstream_errors(
    handler: Callable[[httpx.Request], httpx.Response], fragment: str
) -> None:
    with pytest.raises(UpstreamError, match=fragment):
        await _complete(handler)


async def test_object_tool_arguments_become_json_text() -> None:
    reply = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "c1",
                            "function": {"name": "search_docs", "arguments": {"q": "zażółć"}},
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"prompt_tokens": 3, "completion_tokens": 2},
    }
    result = await _complete(lambda r: httpx.Response(200, json=reply))
    (call,) = result.message.tool_calls
    assert call.arguments == '{"q": "zażółć"}'
