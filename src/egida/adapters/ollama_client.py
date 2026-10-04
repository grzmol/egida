"""ModelClient for any OpenAI-compatible upstream (Ollama serves one under /v1)."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from egida.core.errors import UpstreamError
from egida.core.models import Interaction, Message, ToolCall, Usage
from egida.core.policy import UpstreamConfig
from egida.core.ports import ModelResult

__all__ = ["OllamaClient", "to_openai_messages"]

log = logging.getLogger(__name__)


def to_openai_messages(interaction: Interaction) -> list[dict[str, Any]]:
    """Domain messages → OpenAI chat format (what the upstream receives, already redacted)."""
    out: list[dict[str, Any]] = []
    for m in interaction.messages:
        item: dict[str, Any] = {"role": m.role, "content": m.content}
        if m.name is not None:
            item["name"] = m.name
        if m.tool_call_id is not None:
            item["tool_call_id"] = m.tool_call_id
        if m.tool_calls:
            item["tool_calls"] = [
                {
                    "id": c.id,
                    "type": "function",
                    "function": {"name": c.name, "arguments": c.arguments},
                }
                for c in m.tool_calls
            ]
        out.append(item)
    return out


class OllamaClient:
    """The httpx client is owned by the caller (created and closed in the app lifespan)."""

    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    async def complete(self, interaction: Interaction, upstream: UpstreamConfig) -> ModelResult:
        body: dict[str, Any] = {
            "model": interaction.model,
            "messages": to_openai_messages(interaction),
            "stream": False,
        }
        if interaction.max_tokens is not None:
            body["max_tokens"] = interaction.max_tokens
        if interaction.tools:
            body["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": json.loads(t.parameters_json or "{}"),
                    },
                }
                for t in interaction.tools
            ]
        url = upstream.base_url.rstrip("/") + "/chat/completions"
        try:
            response = await self._http.post(url, json=body, timeout=upstream.timeout_s)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as exc:
            raise UpstreamError(
                f"upstream HTTP {exc.response.status_code}: {exc.response.text[:200]}"
            ) from exc
        except httpx.TransportError as exc:  # includes timeouts and connection errors
            raise UpstreamError(f"upstream unreachable: {type(exc).__name__}: {exc}") from exc
        except ValueError as exc:
            raise UpstreamError(f"upstream returned invalid JSON: {exc}") from exc
        return _parse(data)


def _parse(data: Any) -> ModelResult:
    try:
        choice = data["choices"][0]
        message = choice["message"]
        calls = tuple(
            ToolCall(
                id=str(c.get("id", "")),
                name=str(c["function"]["name"]),
                arguments=_arguments(c["function"].get("arguments", "")),
            )
            for c in message.get("tool_calls") or ()
        )
        usage_raw = data.get("usage") or {}
        usage = Usage(
            int(usage_raw.get("prompt_tokens", 0)), int(usage_raw.get("completion_tokens", 0))
        )
        if not usage_raw:
            log.warning("upstream response without usage; budget settles on the reservation")
        return ModelResult(
            message=Message(
                role="assistant", content=message.get("content") or "", tool_calls=calls
            ),
            usage=usage,
            finish_reason=str(choice.get("finish_reason") or "stop"),
        )
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise UpstreamError(f"unexpected upstream response shape: {exc!r}") from exc


def _arguments(value: Any) -> str:
    """The contract keeps raw JSON text; some servers send arguments as an object."""
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
