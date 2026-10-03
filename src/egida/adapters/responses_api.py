"""OpenAI Responses entry point (driving adapter) for Codex and other Responses API clients.

Route: POST /v1/responses (Bearer key). The request is mapped to the same `Interaction` as the
Chat Completions entry point, runs the same pipeline and answers with the same decision headers
and `egida` receipt; errors use the global OpenAI-format handlers from `http_api`.

Mapping notes:
- `instructions` becomes a system message; `developer` items are scanned as system messages.
- Function call items become assistant tool calls; consecutive calls share one assistant
  message. Their outputs become tool messages.
- Custom (freeform) tools such as Codex `apply_patch` take a raw string. The chat upstream only
  knows JSON-schema functions, so a custom tool is offered as a function with one string
  parameter `input`, and the model's call is turned back into a `custom_tool_call` item.
- Namespace tools (Codex groups e.g. `multi_agent_v1` tools) are flattened: each inner function
  is offered under its own name, and a call to it is returned as a `function_call` item with
  `namespace` set. Inner names must not clash with other tool names.
- Hosted tools (`web_search`, `local_shell`, `image_generation`, `file_search`,
  `code_interpreter`, `mcp`) are dropped: the upstream is a chat model behind the proxy and
  cannot run them, and offering them would invite calls nobody executes.
- `reasoning`, `compaction` and `context_compaction` items are dropped: they carry another
  model's reasoning or encrypted context that the chat upstream cannot use. Any other item or
  content part type is a 400.

The whole response is checked before the first byte is sent (Z-3), so streaming replays the
checked result as Responses SSE events with sequence numbers, ending with `response.completed`
or `response.incomplete` (only for the max_output_tokens limit).

A block is a `completed` response whose message is the block notice: Codex treats an
incomplete response as a stream error and retries the blocked request, so clients detect a
block through the `X-Egida-Decision` header and the `egida` receipt instead.
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Final, Literal

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
from egida.core.errors import InputError, UpstreamError
from egida.core.models import Action, Interaction, Message, Role, ToolCall, ToolDef
from egida.core.pipeline import PipelineResult
from egida.core.tools import TOOL_NAME_RE

__all__ = ["router"]

router = APIRouter()

_HOSTED_TOOLS: Final = frozenset(
    {"web_search", "local_shell", "image_generation", "file_search", "code_interpreter", "mcp"}
)
_DROPPED_ITEMS: Final = frozenset({"reasoning", "compaction", "context_compaction"})
_CUSTOM_PARAMETERS: Final = json.dumps(
    {"type": "object", "properties": {"input": {"type": "string"}}, "required": ["input"]},
    sort_keys=True,
    separators=(",", ":"),
)
_TEXT_PARTS: Final = frozenset({"input_text", "output_text", "text"})
_ROLES: Final[dict[str, Role]] = {
    "system": "system",
    "developer": "system",
    "user": "user",
    "assistant": "assistant",
}
_CALL_ID: Final = r"^[\w.:-]{1,128}$"  # reaches the model and the audit unscanned: bounded


# --- request schema (boundary validation) ------------------------------------------


class _In(BaseModel):
    model_config = ConfigDict(extra="ignore")


class _Part(_In):
    type: str
    text: str | None = None


class _MessageItem(_In):
    role: str
    content: str | list[_Part]


class _FunctionCallItem(_In):
    call_id: str = Field(pattern=_CALL_ID)
    name: str = Field(pattern=TOOL_NAME_RE.pattern)
    arguments: str = ""


class _CustomCallItem(_In):
    call_id: str = Field(pattern=_CALL_ID)
    name: str = Field(pattern=TOOL_NAME_RE.pattern)
    input: str = ""


class _CallOutputItem(_In):
    call_id: str = Field(pattern=_CALL_ID)
    output: str | list[_Part]


class _ResponsesRequest(_In):
    model: str = Field(max_length=128, pattern=r"^[\w.:/@+-]+$")  # copied into every audit event
    instructions: str | None = None
    input: str | list[dict[str, Any]]
    tools: list[dict[str, Any]] | None = Field(default=None, max_length=128)  # bounds C09 pins
    stream: bool = False
    max_output_tokens: int | None = Field(default=None, ge=1)  # < 1 would dodge the C17 clamp


class _FunctionTool(_In):
    name: str = Field(pattern=TOOL_NAME_RE.pattern)
    description: str | None = None
    parameters: dict[str, Any] | None = None


class _CustomTool(_In):
    name: str = Field(pattern=TOOL_NAME_RE.pattern)
    description: str | None = None


class _NamespaceTool(_In):
    name: str = Field(pattern=TOOL_NAME_RE.pattern)  # echoed to the client on its calls
    tools: list[dict[str, Any]] = Field(default_factory=list, max_length=128)


def _validate[M: BaseModel](model: type[M], data: object, where: str) -> M:
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        detail = validation_message(exc).removeprefix("invalid request: ")
        raise InputError(f"invalid request: {where}.{detail}") from exc


def _text(parts: str | list[_Part], where: str) -> str:
    if isinstance(parts, str):
        return parts
    texts: list[str] = []
    for k, part in enumerate(parts):
        if part.type not in _TEXT_PARTS or part.text is None:
            raise InputError(f"{where}[{k}]: unsupported content part type {part.type!r}")
        texts.append(part.text)
    return "\n".join(texts)


def _append_call(messages: list[Message], call: ToolCall) -> None:
    """Consecutive calls (also right after the assistant's text) form one assistant message."""
    last = messages[-1] if messages else None
    if last is not None and last.role == "assistant":
        messages[-1] = Message(
            role="assistant", content=last.content, tool_calls=(*last.tool_calls, call)
        )
    else:
        messages.append(Message(role="assistant", content="", tool_calls=(call,)))


def _messages(req: _ResponsesRequest) -> list[Message]:
    messages: list[Message] = []
    if req.instructions:
        messages.append(Message(role="system", content=req.instructions))
    if isinstance(req.input, str):
        messages.append(Message(role="user", content=req.input))
        return messages
    for i, item in enumerate(req.input):
        where = f"input[{i}]"
        kind = item.get("type", "message" if "role" in item else None)
        if kind == "message":
            msg = _validate(_MessageItem, item, where)
            role = _ROLES.get(msg.role)
            if role is None:
                raise InputError(f"{where}.role {msg.role!r} is not supported")
            messages.append(Message(role=role, content=_text(msg.content, f"{where}.content")))
        elif kind == "function_call":
            fc = _validate(_FunctionCallItem, item, where)
            _append_call(messages, ToolCall(fc.call_id, fc.name, fc.arguments))
        elif kind == "custom_tool_call":
            cc = _validate(_CustomCallItem, item, where)
            arguments = json.dumps({"input": cc.input}, ensure_ascii=False)
            _append_call(messages, ToolCall(cc.call_id, cc.name, arguments))
        elif kind in ("function_call_output", "custom_tool_call_output"):
            out = _validate(_CallOutputItem, item, where)
            content = _text(out.output, f"{where}.output")
            messages.append(Message(role="tool", content=content, tool_call_id=out.call_id))
        elif kind in _DROPPED_ITEMS:
            continue  # reasoning or encrypted context the upstream chat model cannot use
        else:
            raise InputError(f"{where}.type {kind!r} is not supported")
    return messages


@dataclass(slots=True)
class _Tools:
    """Upstream tool definitions plus what the answer needs to restore the client's shapes."""

    defs: list[ToolDef] = field(default_factory=list)
    custom: set[str] = field(default_factory=set)  # names of custom (freeform) tools
    namespaces: dict[str, str] = field(default_factory=dict)  # flattened name -> namespace

    def add(self, tool: ToolDef, where: str, namespace: str | None = None) -> None:
        clash = tool.name in self.namespaces or (
            namespace is not None and any(d.name == tool.name for d in self.defs)
        )
        if clash:
            raise InputError(f"{where}.name {tool.name!r} clashes with another tool name")
        self.defs.append(tool)
        if namespace is not None:
            self.namespaces[tool.name] = namespace


def _function(raw: dict[str, Any], where: str) -> ToolDef:
    fn = _validate(_FunctionTool, raw, where)
    parameters = json.dumps(
        fn.parameters or {}, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return ToolDef(fn.name, fn.description or "", parameters)


def _tools(req: _ResponsesRequest) -> _Tools:
    tools = _Tools()
    for k, raw in enumerate(req.tools or ()):
        where = f"tools[{k}]"
        kind = raw.get("type")
        if kind == "function":
            tools.add(_function(raw, where), where)
        elif kind == "custom":
            ct = _validate(_CustomTool, raw, where)
            tools.add(ToolDef(ct.name, ct.description or "", _CUSTOM_PARAMETERS), where)
            tools.custom.add(ct.name)
        elif kind == "namespace":
            ns = _validate(_NamespaceTool, raw, where)
            for j, inner in enumerate(ns.tools):
                inner_where = f"{where}.tools[{j}]"
                if inner.get("type") != "function":
                    raise InputError(f"{inner_where}.type {inner.get('type')!r} is not supported")
                tools.add(_function(inner, inner_where), inner_where, ns.name)
        elif kind in _HOSTED_TOOLS:
            continue  # hosted tools cannot run behind a chat upstream (module docstring)
        else:
            raise InputError(f"{where}.type {kind!r} is not supported")
    return tools


def _to_interaction(req: _ResponsesRequest, agent_id: str, tools: list[ToolDef]) -> Interaction:
    messages = _messages(req)
    if not messages:
        raise InputError("input must not be empty")
    return Interaction(
        request_id=new_request_id(),
        agent_id=agent_id,
        model=req.model,
        messages=tuple(messages),
        tools=tuple(tools),
        max_tokens=req.max_output_tokens,
        stream=req.stream,
    )


# --- route --------------------------------------------------------------------------


@router.post("/v1/responses")
async def responses(request: Request) -> Response:
    runtime = runtime_of(request)
    agent_id = authenticate(request, runtime.policy.current().policy)
    payload = await read_json(request)
    try:
        req = _ResponsesRequest.model_validate(payload)
    except ValidationError as exc:
        raise InputError(validation_message(exc)) from exc
    tools = _tools(req)
    result = await runtime.pipeline.run(_to_interaction(req, agent_id, tools.defs))
    body = _response(result, tools)  # before any byte is sent: UpstreamError stays a 502
    headers = decision_headers(result)
    if req.stream:
        return StreamingResponse(_sse(body), media_type="text/event-stream", headers=headers)
    return JSONResponse(body, headers=headers)


# --- response -----------------------------------------------------------------------


def _custom_input(call: ToolCall) -> str:
    try:
        arguments = json.loads(call.arguments)
    except ValueError:
        arguments = None
    value = arguments.get("input") if isinstance(arguments, dict) else None
    if not isinstance(value, str):
        raise UpstreamError(
            f"model called custom tool {call.name!r} without a string 'input' argument"
        )
    return value


def _output(result: PipelineResult, tools: _Tools) -> list[dict[str, Any]]:
    request_id = result.interaction.request_id
    output = result.interaction.output
    calls: tuple[ToolCall, ...] = ()
    if result.decision.action is Action.BLOCK:
        text = block_message(result)
    else:
        text = output.content if output else ""
        calls = output.tool_calls if output else ()
    items: list[dict[str, Any]] = []
    if text:
        items.append(
            {
                "type": "message",
                "id": f"msg_{request_id}",
                "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": text, "annotations": []}],
            }
        )
    for n, call in enumerate(calls):
        if call.name in tools.custom:
            items.append(
                {
                    "type": "custom_tool_call",
                    "id": f"ctc_{request_id}_{n}",
                    "status": "completed",
                    "call_id": call.id,
                    "name": call.name,
                    "input": _custom_input(call),
                }
            )
        else:
            item: dict[str, Any] = {
                "type": "function_call",
                "id": f"fc_{request_id}_{n}",
                "status": "completed",
                "call_id": call.id,
                "name": call.name,
                "arguments": call.arguments,
            }
            if namespace := tools.namespaces.get(call.name):
                item["namespace"] = namespace
            items.append(item)
    return items


def _response(result: PipelineResult, tools: _Tools) -> dict[str, Any]:
    incomplete = "max_output_tokens" if result.finish_reason == "length" else None
    if result.decision.action is Action.BLOCK:
        incomplete = None  # see module docstring: an incomplete block makes Codex retry
    usage = result.usage
    prompt = usage.prompt_tokens if usage else 0
    completion = usage.completion_tokens if usage else 0
    return {
        "id": f"resp_{result.interaction.request_id}",
        "object": "response",
        "created_at": int(time.time()),
        "status": "incomplete" if incomplete else "completed",
        "incomplete_details": {"reason": incomplete} if incomplete else None,
        "error": None,
        "model": result.interaction.model,
        "output": _output(result, tools),
        "usage": {
            "input_tokens": prompt,
            "input_tokens_details": {"cached_tokens": 0},
            "output_tokens": completion,
            "output_tokens_details": {"reasoning_tokens": 0},
            "total_tokens": prompt + completion,
        },
        "egida": receipt(result),
    }


# --- streaming ----------------------------------------------------------------------


def _item_events(index: int, item: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Events for one finished output item, from output_item.added to output_item.done."""
    where = {"item_id": item["id"], "output_index": index}
    events: list[tuple[str, dict[str, Any]]] = []
    kind = item["type"]
    if kind == "message":
        text = item["content"][0]["text"]
        part = {"type": "output_text", "text": "", "annotations": []}
        at = {**where, "content_index": 0}
        events += [
            (
                "response.output_item.added",
                {**where, "item": {**item, "status": "in_progress", "content": []}},
            ),
            ("response.content_part.added", {**at, "part": part}),
            ("response.output_text.delta", {**at, "delta": text, "logprobs": []}),
            ("response.output_text.done", {**at, "text": text, "logprobs": []}),
            ("response.content_part.done", {**at, "part": {**part, "text": text}}),
        ]
    elif kind == "function_call":
        arguments = item["arguments"]
        events += [
            (
                "response.output_item.added",
                {**where, "item": {**item, "status": "in_progress", "arguments": ""}},
            ),
            ("response.function_call_arguments.delta", {**where, "delta": arguments}),
            (
                "response.function_call_arguments.done",
                {**where, "name": item["name"], "arguments": arguments},
            ),
        ]
    else:  # custom_tool_call
        value = item["input"]
        events += [
            (
                "response.output_item.added",
                {**where, "item": {**item, "status": "in_progress", "input": ""}},
            ),
            ("response.custom_tool_call_input.delta", {**where, "delta": value}),
            ("response.custom_tool_call_input.done", {**where, "input": value}),
        ]
    events.append(("response.output_item.done", {**where, "item": item}))
    return events


async def _sse(body: dict[str, Any]) -> AsyncIterator[str]:
    """Replay a fully checked response as Responses SSE events (Z-3)."""
    start = {
        k: v for k, v in body.items() if k not in ("egida", "output", "usage", "incomplete_details")
    }
    start |= {"status": "in_progress", "output": [], "usage": None, "incomplete_details": None}
    terminal: Literal["response.completed", "response.incomplete"] = (
        "response.incomplete" if body["status"] == "incomplete" else "response.completed"
    )
    events: list[tuple[str, dict[str, Any]]] = [
        ("response.created", {"response": start}),
        ("response.in_progress", {"response": start}),
    ]
    for index, item in enumerate(body["output"]):
        events += _item_events(index, item)
    events.append((terminal, {"response": body}))
    for seq, (kind, data) in enumerate(events):
        payload = json.dumps({"type": kind, "sequence_number": seq, **data}, ensure_ascii=False)
        yield f"event: {kind}\ndata: {payload}\n\n"
