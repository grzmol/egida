"""OpenAI-compatible HTTP entry point (driving adapter).

Path allowlist: POST /v1/chat/completions, GET /v1/models, GET /healthz, GET /metrics, operator
views under /api. Anything else → 404 in the OpenAI error format (closes passthrough of e.g.
/api/pull, CVE-2024-37032).

A blocked request is a valid `chat.completion` with HTTP 200 and finish_reason "content_filter",
plus `X-Egida-*` headers and an `egida` field ("every decision has a receipt").
Request and response bodies are never logged.
"""

from __future__ import annotations

import dataclasses
import functools
import json
import time
from collections.abc import AsyncIterator
from typing import Any, Literal

import anyio
from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from egida.adapters.audit_jsonl import verify_file
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
from egida.adapters.telemetry import (
    PROMETHEUS_CONTENT_TYPE,
    render_prometheus,
    snapshot_to_json,
)
from egida.core.errors import AuditError, AuthError, InputError, UpstreamError
from egida.core.models import Action, Interaction, Message, ToolCall, ToolDef
from egida.core.pipeline import PipelineResult
from egida.core.signatures import signature_cases
from egida.core.tools import TOOL_NAME_RE

__all__ = ["install_error_handlers", "router"]

router = APIRouter()


# --- request schema (boundary validation) ------------------------------------------


class _In(BaseModel):
    model_config = ConfigDict(extra="ignore")


class _FunctionIn(_In):
    name: str
    arguments: str = ""


class _ToolCallIn(_In):
    id: str = Field(default="", pattern=r"^[\w.:-]{0,128}$")
    type: str = "function"
    function: _FunctionIn


class _ContentPart(_In):
    type: str
    text: str | None = None


class _MessageIn(_In):
    role: str
    content: str | list[_ContentPart] | None = None
    # identifiers reach the model but are not scanned: bounded to short, plain tokens
    name: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,64}$")
    tool_call_id: str | None = Field(default=None, pattern=r"^[\w.:-]{1,128}$")
    tool_calls: list[_ToolCallIn] | None = None


class _ToolFunctionIn(_In):
    name: str
    description: str = ""
    parameters: dict[str, Any] | None = None


class _ToolIn(_In):
    type: str = "function"
    function: _ToolFunctionIn


class _ChatRequest(_In):
    model: str = Field(max_length=128, pattern=r"^[\w.:/@+-]+$")  # copied into every audit event
    messages: list[_MessageIn]
    max_tokens: int | None = Field(default=None, ge=1)  # < 1 would dodge the C17 clamp and C15
    max_completion_tokens: int | None = Field(default=None, ge=1)
    stream: bool = False
    n: int | None = None
    tools: list[_ToolIn] | None = Field(default=None, max_length=128)  # also bounds C09 pins
    functions: list[Any] | None = None  # legacy OpenAI fields: rejected, never silently dropped
    function_call: Any = None


_ROLES: dict[str, Literal["system", "user", "assistant", "tool"]] = {
    "system": "system",
    "developer": "system",  # newer OpenAI role: scanned like system
    "user": "user",
    "assistant": "assistant",
    "tool": "tool",
}


def _to_interaction(req: _ChatRequest, agent_id: str) -> Interaction:
    if req.n is not None and req.n != 1:
        raise InputError("only n=1 is supported")
    if not req.messages:
        raise InputError("messages must not be empty")
    if req.functions is not None or req.function_call is not None:
        raise InputError("functions/function_call are not supported, use tools/tool_calls")
    messages: list[Message] = []
    for i, m in enumerate(req.messages):
        role = _ROLES.get(m.role)
        if role is None:
            raise InputError(f"messages[{i}].role {m.role!r} is not supported")
        calls = tuple(
            ToolCall(id=c.id, name=c.function.name, arguments=c.function.arguments)
            for c in m.tool_calls or ()
        )
        messages.append(
            Message(
                role=role,
                content=_content(m, i, has_calls=bool(calls)),
                name=m.name,
                tool_call_id=m.tool_call_id,
                tool_calls=calls,
            )
        )
    tools: list[ToolDef] = []
    for k, t in enumerate(req.tools or ()):
        if t.type != "function":
            raise InputError(f"tools[{k}].type {t.type!r} is not supported, use 'function'")
        if not TOOL_NAME_RE.fullmatch(t.function.name):
            raise InputError(f"tools[{k}].function.name must match {TOOL_NAME_RE.pattern}")
        parameters = json.dumps(
            t.function.parameters or {}, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        tools.append(ToolDef(t.function.name, t.function.description, parameters))
    return Interaction(
        request_id=new_request_id(),
        agent_id=agent_id,
        model=req.model,
        messages=tuple(messages),
        tools=tuple(tools),
        max_tokens=req.max_completion_tokens or req.max_tokens,
        stream=req.stream,
    )


def _content(m: _MessageIn, index: int, *, has_calls: bool) -> str:
    if m.content is None:
        if m.role == "assistant" and has_calls:
            return ""
        raise InputError(f"messages[{index}].content must not be null")
    if isinstance(m.content, str):
        return m.content
    texts: list[str] = []
    for part in m.content:
        if part.type != "text" or part.text is None:
            raise InputError(f"messages[{index}]: unsupported content part type {part.type!r}")
        texts.append(part.text)
    return "\n".join(texts)


# --- routes -------------------------------------------------------------------------


@router.get("/healthz")
async def healthz(request: Request) -> dict[str, object]:
    snapshot = runtime_of(request).policy.current()
    return {
        "status": "ok",
        "policy_version": snapshot.policy.version,
        "policy_sha256": snapshot.sha256,
    }


@router.get("/api/policy")
async def policy_status(request: Request) -> dict[str, object]:
    """Operator view of the active policy (no agent key; the proxy listens on localhost)."""
    runtime = runtime_of(request)
    snapshot = runtime.policy.current()
    policy = snapshot.policy
    return {
        "version": policy.version,
        "sha256": snapshot.sha256,
        "loaded_at": snapshot.loaded_at,
        "source": snapshot.source,
        "last_error": runtime.policy.last_error(),
        "controls": [
            {
                "id": c.id,
                "kind": c.kind,
                "enabled": c.enabled,
                "sides": [s.value for s in c.sides],
                "action": c.action.value,
                "threshold": c.threshold,
                "on_error": c.on_error or policy.defaults.on_error,
            }
            for c in policy.controls
        ],
        "registered_kinds": list(runtime.registered_kinds),
        "agents": [
            {
                "id": agent_id,
                "allowed_models": list(a.allowed_models),
                "allowed_tools": list(a.allowed_tools),
                "budget": a.budget,
            }
            for agent_id, a in policy.agents.items()
        ],
    }


@router.get("/api/signatures")
async def signatures_status(request: Request) -> dict[str, object]:
    """Operator view of the active signature feed (no agent key; the proxy listens on localhost)."""
    feed = runtime_of(request).feed
    snapshot = feed.current()
    return {
        "feed_version": snapshot.version,
        "sha256": snapshot.sha256,
        "loaded_at": snapshot.loaded_at,
        "source": snapshot.source,
        "last_error": feed.last_error(),
        "rules": [
            {
                "id": r.rule.id,
                "title": r.rule.title,
                "status": r.rule.status,
                "severity": r.rule.severity,
                "action": r.rule.action,
                "scope": list(r.rule.scope),
                "tags": list(r.rule.tags),
                "references": list(r.rule.references),
                "tests": {
                    "positive": len(r.rule.tests.positive),
                    "negative": len(r.rule.tests.negative),
                },
            }
            for r in snapshot.feed.rules
        ],
    }


@router.get("/api/signatures/cases")
async def signatures_cases(request: Request, agent: str = "sig-probe-agent") -> dict[str, object]:
    """The feed rules' own tests as selftest cases for `agent` (R4 + R6, demo W2)."""
    runtime = runtime_of(request)
    policy = runtime.policy.current().policy
    if agent not in policy.agents:
        raise StarletteHTTPException(404)
    return signature_cases(runtime.feed.current(), policy, agent)


@router.get("/metrics")
async def prometheus_metrics(request: Request) -> Response:
    """Prometheus text format (operator endpoint, no agent key)."""
    text = render_prometheus(runtime_of(request).telemetry.snapshot())
    return Response(text, media_type=PROMETHEUS_CONTENT_TYPE)


@router.get("/api/telemetry")
async def telemetry_status(request: Request) -> dict[str, object]:
    """Per-stage latency percentiles and counters, `telemetry.v1` (operator endpoint)."""
    return snapshot_to_json(runtime_of(request).telemetry.snapshot())


@router.get("/api/audit/verify")
async def audit_verify(request: Request) -> JSONResponse:
    """Hash-chain check of the audit log: 200 intact, 409 broken (operator endpoint).

    Runs in a worker thread (the cost grows with the file); the line being appended right now
    is skipped, not reported as truncated."""
    path = runtime_of(request).audit_path
    result = await anyio.to_thread.run_sync(
        functools.partial(verify_file, path, allow_partial_tail=True)
    )
    return JSONResponse(dataclasses.asdict(result), status_code=200 if result.ok else 409)


@router.get("/v1/models")
async def list_models(request: Request) -> dict[str, object]:
    policy = runtime_of(request).policy.current().policy
    agent_id = authenticate(request, policy)
    return {
        "object": "list",
        "data": [
            {"id": name, "object": "model", "created": 0, "owned_by": "egida"}
            for name in policy.agents[agent_id].allowed_models
        ],
    }


@router.post("/v1/chat/completions")
async def chat_completions(request: Request) -> Response:
    runtime = runtime_of(request)
    agent_id = authenticate(request, runtime.policy.current().policy)
    payload = await read_json(request)
    try:
        chat = _ChatRequest.model_validate(payload)
    except ValidationError as exc:
        raise InputError(validation_message(exc)) from exc
    interaction = _to_interaction(chat, agent_id)
    result = await runtime.pipeline.run(interaction)
    headers = decision_headers(result)
    if chat.stream:
        return StreamingResponse(_sse(result), media_type="text/event-stream", headers=headers)
    return JSONResponse(_completion(result), headers=headers)


# --- responses ----------------------------------------------------------------------


def _assistant(result: PipelineResult) -> tuple[dict[str, object], str]:
    """Message shown to the client and its finish_reason."""
    if result.decision.action is Action.BLOCK:
        return {"role": "assistant", "content": block_message(result)}, "content_filter"
    output = result.interaction.output
    content = output.content if output else ""
    message: dict[str, object] = {"role": "assistant", "content": content}
    if output and output.tool_calls:
        message["content"] = content or None  # OpenAI sends null next to tool calls
        message["tool_calls"] = [
            {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": c.arguments}}
            for c in output.tool_calls
        ]
    return message, result.finish_reason or "stop"


def _completion(result: PipelineResult) -> dict[str, object]:
    message, finish_reason = _assistant(result)
    usage = result.usage
    prompt = usage.prompt_tokens if usage else 0
    completion = usage.completion_tokens if usage else 0
    return {
        "id": "chatcmpl-" + result.interaction.request_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": result.interaction.model,
        "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
        "usage": {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": prompt + completion,
        },
        "egida": receipt(result),
    }


async def _sse(result: PipelineResult) -> AsyncIterator[str]:
    """Replay a fully checked response as SSE (Z-3: output controls always see the whole text)."""
    message, finish_reason = _assistant(result)
    base = {
        "id": "chatcmpl-" + result.interaction.request_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": result.interaction.model,
    }
    delta_content = {k: v for k, v in message.items() if k != "role"}
    if isinstance(calls := delta_content.get("tool_calls"), list):  # stream deltas carry an index
        delta_content["tool_calls"] = [{"index": i, **c} for i, c in enumerate(calls)]
    chunks: list[dict[str, object]] = [
        {**base, "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]},
        {**base, "choices": [{"index": 0, "delta": delta_content, "finish_reason": None}]},
        {
            **base,
            "choices": [{"index": 0, "delta": {}, "finish_reason": finish_reason}],
            "egida": receipt(result),
        },
    ]
    for chunk in chunks:
        yield "data: " + json.dumps(chunk, ensure_ascii=False) + "\n\n"
    yield "data: [DONE]\n\n"


# --- errors -------------------------------------------------------------------------


def _error(status: int, message: str, kind: str, code: str) -> JSONResponse:
    return JSONResponse(
        {"error": {"message": message, "type": kind, "code": code}}, status_code=status
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AuthError)
    async def _auth(_: Request, exc: AuthError) -> JSONResponse:
        return _error(401, str(exc), "authentication_error", "invalid_api_key")

    @app.exception_handler(InputError)
    async def _input(_: Request, exc: InputError) -> JSONResponse:
        return _error(400, str(exc), "invalid_request_error", "invalid_request")

    @app.exception_handler(UpstreamError)
    async def _upstream(_: Request, exc: UpstreamError) -> JSONResponse:
        return _error(502, str(exc), "upstream_error", "bad_gateway")

    @app.exception_handler(AuditError)
    async def _audit(_: Request, exc: AuditError) -> JSONResponse:
        # no decision without a receipt (ADR-0004): withhold the answer; the cause is logged
        return _error(503, "audit log unavailable", "server_error", "audit_unavailable")

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        if exc.status_code == 404:
            return _error(404, "unknown endpoint", "invalid_request_error", "not_found")
        return _error(exc.status_code, str(exc.detail), "invalid_request_error", "http_error")
