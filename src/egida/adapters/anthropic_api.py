"""Anthropic Messages entry point (driving adapter) for Claude Code and other Anthropic clients.

Routes: POST /v1/messages, POST /v1/messages/count_tokens, HEAD/GET /api/hello (Claude Code's
connectivity probe). Query strings such as `?beta=true` are ignored.

The request is mapped to the same `Interaction` as the OpenAI entry point and runs through the
same pipeline; the upstream is still the policy's OpenAI-compatible model. Only text, tool_use
and tool_result blocks are supported: thinking blocks are dropped, any other block (image,
document, ...) and server tools are rejected with 400, never silently ignored. A blocked request
is a valid message with stop_reason "end_turn" and one text block naming the control and request
id; clients detect the block by the X-Egida-* headers and the `egida` receipt. Not "refusal":
Claude Code hides the text of a refusal and points the user at Anthropic's usage policy instead.
Errors use the Anthropic error shape.
"""

from __future__ import annotations

import json
import math
from collections.abc import AsyncIterator
from typing import Any, Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from egida.adapters.http_common import (
    authenticate,
    block_message,
    decision_headers,
    new_request_id,
    read_json,
    receipt,
    runtime_of,
    validation_message,
)
from egida.core.budget import input_chars
from egida.core.errors import AuditError, AuthError, InputError, UpstreamError
from egida.core.models import Action, Interaction, Message, ToolCall, ToolDef
from egida.core.pipeline import PipelineResult
from egida.core.tools import TOOL_NAME_RE

__all__ = ["router"]

router = APIRouter()

_KEY_HEADERS = ("x-api-key",)
_ID_PATTERN = r"^[\w.:-]{1,128}$"


# --- request schema (boundary validation) ------------------------------------------


class _In(BaseModel):
    model_config = ConfigDict(extra="ignore")


class _Block(_In):
    type: str
    text: str | None = None
    id: str | None = Field(default=None, pattern=_ID_PATTERN)
    name: str | None = None
    input: Any = None
    tool_use_id: str | None = Field(default=None, pattern=_ID_PATTERN)
    content: str | list[_Block] | None = None


class _MessageIn(_In):
    role: str
    content: str | list[_Block]


class _ToolIn(_In):
    type: str | None = None
    name: str
    description: str = ""
    input_schema: dict[str, Any] | None = None


class _MessagesRequest(_In):
    model: str = Field(max_length=128, pattern=r"^[\w.:/@+-]+$")  # copied into every audit event
    messages: list[_MessageIn]
    system: str | list[_Block] | None = None
    max_tokens: int | None = Field(default=None, ge=1)
    stream: bool = False
    tools: list[_ToolIn] | None = Field(default=None, max_length=128)


_ROLES: dict[str, Literal["system", "user", "assistant"]] = {
    "system": "system",
    "user": "user",
    "assistant": "assistant",
}
_DROPPED = frozenset({"thinking", "redacted_thinking"})


def _text_of(blocks: str | list[_Block], where: str) -> str:
    """Text of a str or a list of text blocks (thinking blocks dropped, others rejected)."""
    if isinstance(blocks, str):
        return blocks
    texts: list[str] = []
    for k, b in enumerate(blocks):
        if b.type in _DROPPED:
            continue
        if b.type != "text" or b.text is None:
            raise InputError(f"{where}[{k}]: unsupported content block type {b.type!r}")
        texts.append(b.text)
    return "\n".join(texts)


def _map_message(m: _MessageIn, i: int) -> list[Message]:
    role = _ROLES.get(m.role)
    if role is None:
        raise InputError(f"messages[{i}].role {m.role!r} is not supported")
    if isinstance(m.content, str):
        return [Message(role=role, content=m.content)]
    where = f"messages[{i}].content"
    tool_results: list[Message] = []
    calls: list[ToolCall] = []
    texts: list[str] = []
    for k, b in enumerate(m.content):
        if b.type in _DROPPED:
            continue
        if b.type == "text" and b.text is not None:
            texts.append(b.text)
        elif b.type == "tool_use" and role == "assistant" and b.id and b.name:
            arguments = json.dumps(b.input if b.input is not None else {}, ensure_ascii=False)
            calls.append(ToolCall(id=b.id, name=b.name, arguments=arguments))
        elif b.type == "tool_result" and role == "user" and b.tool_use_id:
            content = _text_of(b.content or "", f"{where}[{k}].content")
            tool_results.append(Message(role="tool", content=content, tool_call_id=b.tool_use_id))
        else:
            raise InputError(f"{where}[{k}]: unsupported content block type {b.type!r}")
    out = tool_results
    if texts or calls:
        out.append(Message(role=role, content="\n".join(texts), tool_calls=tuple(calls)))
    return out


def _to_interaction(req: _MessagesRequest, agent_id: str) -> Interaction:
    if not req.messages:
        raise InputError("messages must not be empty")
    messages: list[Message] = []
    if req.system is not None:
        system = _text_of(req.system, "system")
        if system:
            messages.append(Message(role="system", content=system))
    for i, m in enumerate(req.messages):
        messages.extend(_map_message(m, i))
    tools: list[ToolDef] = []
    for k, t in enumerate(req.tools or ()):
        if t.type not in (None, "custom"):
            raise InputError(f"tools[{k}].type {t.type!r} is not supported, use custom tools")
        if not TOOL_NAME_RE.fullmatch(t.name):
            raise InputError(f"tools[{k}].name must match {TOOL_NAME_RE.pattern}")
        schema = json.dumps(
            t.input_schema or {}, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        tools.append(ToolDef(t.name, t.description, schema))
    return Interaction(
        request_id=new_request_id(),
        agent_id=agent_id,
        model=req.model,
        messages=tuple(messages),
        tools=tuple(tools),
        max_tokens=req.max_tokens,
        stream=req.stream,
    )


async def _parse(request: Request) -> tuple[_MessagesRequest, Interaction]:
    agent_id = authenticate(
        request, runtime_of(request).policy.current().policy, key_headers=_KEY_HEADERS
    )
    payload = await read_json(request)
    try:
        req = _MessagesRequest.model_validate(payload)
    except ValidationError as exc:
        raise InputError(validation_message(exc)) from exc
    return req, _to_interaction(req, agent_id)


# --- routes -------------------------------------------------------------------------


@router.api_route("/api/hello", methods=["GET", "HEAD"])
async def hello() -> Response:
    return Response(status_code=200)


@router.post("/v1/messages")
async def messages(request: Request) -> Response:
    try:
        req, interaction = await _parse(request)
        result = await runtime_of(request).pipeline.run(interaction)
        message = _message(result)
    except (AuthError, InputError, UpstreamError, AuditError) as exc:
        return _error(exc)
    headers = decision_headers(result)
    if req.stream:
        return StreamingResponse(
            _sse(message, result), media_type="text/event-stream", headers=headers
        )
    return JSONResponse(message, headers=headers)


@router.post("/v1/messages/count_tokens")
async def count_tokens(request: Request) -> Response:
    try:
        _, interaction = await _parse(request)
    except (AuthError, InputError) as exc:
        return _error(exc)
    return JSONResponse({"input_tokens": math.ceil(input_chars(interaction) / 4)})


# --- responses ----------------------------------------------------------------------

_STOP_REASONS = {"stop": "end_turn", "length": "max_tokens", "tool_calls": "tool_use"}


def _content_blocks(result: PipelineResult) -> tuple[list[dict[str, Any]], str]:
    if result.decision.action is Action.BLOCK:
        return [{"type": "text", "text": block_message(result)}], "end_turn"
    output = result.interaction.output
    blocks: list[dict[str, Any]] = []
    if output and output.content:
        blocks.append({"type": "text", "text": output.content})
    for call in output.tool_calls if output else ():
        try:
            arguments = json.loads(call.arguments or "{}")
        except ValueError as exc:
            raise UpstreamError(f"tool call {call.name!r} arguments are not valid JSON") from exc
        if not isinstance(arguments, dict):
            raise UpstreamError(f"tool call {call.name!r} arguments are not a JSON object")
        blocks.append({"type": "tool_use", "id": call.id, "name": call.name, "input": arguments})
    return blocks, _STOP_REASONS.get(result.finish_reason or "stop", "end_turn")


def _message(result: PipelineResult) -> dict[str, Any]:
    blocks, stop_reason = _content_blocks(result)
    usage = result.usage
    return {
        "id": "msg_" + result.interaction.request_id,
        "type": "message",
        "role": "assistant",
        "model": result.interaction.model,
        "content": blocks,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {
            "input_tokens": usage.prompt_tokens if usage else 0,
            "output_tokens": usage.completion_tokens if usage else 0,
        },
        "egida": receipt(result),
    }


def _event(name: str, data: dict[str, Any]) -> str:
    return (
        f"event: {name}\ndata: " + json.dumps({"type": name, **data}, ensure_ascii=False) + "\n\n"
    )


async def _sse(message: dict[str, Any], result: PipelineResult) -> AsyncIterator[str]:
    """Replay a fully checked message as Anthropic SSE (output controls saw the whole text)."""
    usage = message["usage"]
    start = {k: v for k, v in message.items() if k != "egida"}
    start |= {
        "content": [],
        "stop_reason": None,
        "usage": {"input_tokens": usage["input_tokens"], "output_tokens": 0},
    }
    yield _event("message_start", {"message": start})
    yield _event("ping", {})
    for index, block in enumerate(message["content"]):
        if block["type"] == "text":
            empty: dict[str, Any] = {"type": "text", "text": ""}
            delta: dict[str, Any] = {"type": "text_delta", "text": block["text"]}
        else:
            empty = {**block, "input": {}}
            partial = json.dumps(block["input"], ensure_ascii=False)
            delta = {"type": "input_json_delta", "partial_json": partial}
        yield _event("content_block_start", {"index": index, "content_block": empty})
        yield _event("content_block_delta", {"index": index, "delta": delta})
        yield _event("content_block_stop", {"index": index})
    yield _event(
        "message_delta",
        {
            "delta": {"stop_reason": message["stop_reason"], "stop_sequence": None},
            "usage": {"output_tokens": usage["output_tokens"]},
            "egida": message["egida"],
        },
    )
    yield _event("message_stop", {})


# --- errors -------------------------------------------------------------------------


def _error(exc: Exception) -> JSONResponse:
    if isinstance(exc, AuthError):
        status, kind, text = 401, "authentication_error", str(exc)
    elif isinstance(exc, InputError):
        status, kind, text = 400, "invalid_request_error", str(exc)
    elif isinstance(exc, UpstreamError):
        status, kind, text = 502, "api_error", str(exc)
    else:  # AuditError: no decision without a receipt (ADR-0004); the cause is logged
        status, kind, text = 503, "overloaded_error", "audit log unavailable"
    return JSONResponse(
        {"type": "error", "error": {"type": kind, "message": text}}, status_code=status
    )
