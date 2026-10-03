"""Gemini API entry point (driving adapter) for Gemini CLI and Antigravity CLI.

The clients set `GOOGLE_GEMINI_BASE_URL` to the proxy root and call the `@google/genai` paths:

- `POST /v1beta/models/{model}:generateContent`
- `POST /v1beta/models/{model}:streamGenerateContent` (SSE with `?alt=sse`, else a JSON array)
- `POST /v1beta/models/{model}:countTokens`
- `GET /v1beta/models`, `GET /v1beta/models/{model}`

The same routes exist under `/v1`, except `GET /v1/models`: that path belongs to the OpenAI entry
point (`http_api`), which is registered first. Model ids may contain `:` (`llama3.2:3b`), so the
method is the text after the LAST colon; an optional `models/` prefix is stripped.

Auth: `Authorization: Bearer`, then `x-goog-api-key`, then the `key` query parameter as a last
resort. Errors are Gemini-shaped (`{"error": {"code", "message", "status"}}`) and are produced
here, not by the global OpenAI-format handlers.

Every request maps to the same `Interaction` as the other entry points; the upstream is always the
policy's chat model. Hence tools without `functionDeclarations` (`googleSearch`, `codeExecution`,
`urlContext`, ...) are dropped: a chat upstream cannot run them. Media parts (`inlineData`,
`fileData`) are rejected with 400. Streaming replays the fully checked answer as one chunk, so
output controls always see the whole text. Request and response bodies are never logged.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import AsyncIterator
from typing import Any, Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, ValidationError

from egida.adapters.http_common import (
    agent_for_key,
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
from egida.core.policy import Policy
from egida.core.tools import TOOL_NAME_RE

__all__ = ["router"]

router = APIRouter()

_PREFIXES = ("/v1beta", "/v1")
_MODEL_RE = re.compile(r"[\w.:/@+-]{1,128}")  # same rule as the OpenAI entry point
_METHODS = ("generateContent", "streamGenerateContent", "countTokens")
_MAX_TOOLS = 128  # same bound as the OpenAI entry point (also bounds C09 pins)
# Part fields that carry no content for the model; every other unknown field is rejected.
_PART_METADATA = frozenset(
    {"thought", "thoughtSignature", "thought_signature", "partMetadata", "part_metadata"}
)


def _alias(camel: str, snake: str) -> Any:
    """Gemini's JSON accepts both lowerCamelCase and snake_case field names."""
    return Field(default=None, validation_alias=AliasChoices(camel, snake))


# --- request schema (boundary validation) ------------------------------------------


class _In(BaseModel):
    model_config = ConfigDict(extra="ignore")


class _FunctionCallIn(_In):
    name: str
    args: dict[str, Any] | None = None
    id: str | None = Field(default=None, pattern=r"^[\w.:-]{0,128}$")


class _FunctionResponseIn(_In):
    name: str
    response: dict[str, Any] | None = None
    id: str | None = Field(default=None, pattern=r"^[\w.:-]{0,128}$")


class _Part(BaseModel):
    model_config = ConfigDict(extra="allow")

    text: str | None = None
    thought: bool | None = None
    function_call: _FunctionCallIn | None = _alias("functionCall", "function_call")
    function_response: _FunctionResponseIn | None = _alias("functionResponse", "function_response")


class _Content(_In):
    role: str | None = None
    parts: list[_Part] = Field(default_factory=list)


class _FunctionDeclarationIn(_In):
    name: str
    description: str = ""
    parameters: dict[str, Any] | None = None
    parameters_json_schema: dict[str, Any] | None = _alias(
        "parametersJsonSchema", "parameters_json_schema"
    )


class _ToolIn(_In):
    function_declarations: list[_FunctionDeclarationIn] | None = _alias(
        "functionDeclarations", "function_declarations"
    )


class _GenerationConfigIn(_In):
    max_output_tokens: int | None = Field(
        default=None,
        ge=1,  # < 1 would dodge the C17 clamp and C15
        validation_alias=AliasChoices("maxOutputTokens", "max_output_tokens"),
    )


class _GenerateRequest(_In):
    contents: list[_Content] = Field(default_factory=list)
    system_instruction: str | _Content | None = _alias("systemInstruction", "system_instruction")
    tools: list[_ToolIn] | None = None
    generation_config: _GenerationConfigIn | None = _alias("generationConfig", "generation_config")


class _CountTokensRequest(_GenerateRequest):
    generate_content_request: _GenerateRequest | None = _alias(
        "generateContentRequest", "generate_content_request"
    )


# --- mapping ------------------------------------------------------------------------


class _Calls:
    """Tool call ids: given ids are kept; missing ids become `call_<k>`. A functionResponse
    without an id answers the latest unanswered call with the same name."""

    def __init__(self) -> None:
        self._next = 0
        self._open: list[tuple[str, str]] = []  # (id, name), oldest first

    def _new_id(self) -> str:
        self._next += 1
        return f"call_{self._next}"

    def call(self, fc: _FunctionCallIn) -> ToolCall:
        call_id = fc.id or self._new_id()
        self._open.append((call_id, fc.name))
        return ToolCall(id=call_id, name=fc.name, arguments=_dumps(fc.args or {}))

    def answer(self, fr: _FunctionResponseIn) -> str:
        if fr.id:
            self._open = [(i, n) for i, n in self._open if i != fr.id]
            return fr.id
        for k in range(len(self._open) - 1, -1, -1):
            if self._open[k][1] == fr.name:
                return self._open.pop(k)[0]
        return self._new_id()


def _dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


def _texts(
    parts: list[_Part], where: str, calls: _Calls | None, role: str
) -> tuple[list[str], list[ToolCall], list[Message]]:
    """Text of the parts, the model's function calls and the user's function responses."""
    texts: list[str] = []
    tool_calls: list[ToolCall] = []
    responses: list[Message] = []
    for j, part in enumerate(parts):
        extra = sorted(set(part.model_extra or ()) - _PART_METADATA)
        if extra:
            raise InputError(f"{where}.parts[{j}]: unsupported part {extra[0]!r}")
        if part.thought:
            continue
        if part.function_call is not None:
            if calls is None or role != "assistant":
                raise InputError(f"{where}.parts[{j}]: functionCall is only allowed in model turns")
            tool_calls.append(calls.call(part.function_call))
        if part.function_response is not None:
            if calls is None or role != "user":
                raise InputError(
                    f"{where}.parts[{j}]: functionResponse is only allowed in user turns"
                )
            fr = part.function_response
            responses.append(
                Message(
                    role="tool",
                    content=_dumps(fr.response or {}),
                    name=fr.name,
                    tool_call_id=calls.answer(fr),
                )
            )
        if part.text is not None:
            texts.append(part.text)
    return texts, tool_calls, responses


_ROLES: dict[str, Literal["user", "assistant"]] = {
    "user": "user",
    "function": "user",  # older Gemini API role for function responses
    "model": "assistant",
}


def _messages(req: _GenerateRequest) -> list[Message]:
    messages: list[Message] = []
    system = req.system_instruction
    if system is not None:
        if isinstance(system, str):
            text = system
        else:
            texts, _, _ = _texts(system.parts, "systemInstruction", None, "system")
            text = "\n".join(texts)
        messages.append(Message(role="system", content=text))
    calls = _Calls()
    for i, content in enumerate(req.contents):
        role = _ROLES.get(content.role or "user")
        if role is None:
            raise InputError(f"contents[{i}].role {content.role!r} is not supported")
        texts, tool_calls, responses = _texts(content.parts, f"contents[{i}]", calls, role)
        messages.extend(responses)  # tool results come before the user's text of the same turn
        if texts or tool_calls or not responses:
            messages.append(
                Message(role=role, content="\n".join(texts), tool_calls=tuple(tool_calls))
            )
    return messages


def _lower_types(schema: object) -> object:
    """Gemini `parameters` (OpenAPI subset) spells types in upper case (`OBJECT`); JSON Schema,
    which the chat upstream expects, uses lower case."""
    if isinstance(schema, dict):
        return {
            k: v.lower() if k == "type" and isinstance(v, str) else _lower_types(v)
            for k, v in schema.items()
        }
    if isinstance(schema, list):
        return [_lower_types(v) for v in schema]
    return schema


def _tools(req: _GenerateRequest) -> list[ToolDef]:
    tools: list[ToolDef] = []
    for k, tool in enumerate(req.tools or ()):
        for d, decl in enumerate(tool.function_declarations or ()):  # other tools are dropped
            if not TOOL_NAME_RE.fullmatch(decl.name):
                raise InputError(
                    f"tools[{k}].functionDeclarations[{d}].name must match {TOOL_NAME_RE.pattern}"
                )
            if decl.parameters_json_schema is not None:
                parameters: object = decl.parameters_json_schema
            else:
                parameters = _lower_types(decl.parameters or {})
            canonical = json.dumps(
                parameters, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            )
            tools.append(ToolDef(decl.name, decl.description, canonical))
    if len(tools) > _MAX_TOOLS:
        raise InputError(f"at most {_MAX_TOOLS} function declarations are supported")
    return tools


def _to_interaction(
    req: _GenerateRequest, agent_id: str, model: str, *, stream: bool
) -> Interaction:
    config = req.generation_config
    return Interaction(
        request_id=new_request_id(),
        agent_id=agent_id,
        model=model,
        messages=tuple(_messages(req)),
        tools=tuple(_tools(req)),
        max_tokens=config.max_output_tokens if config else None,
        stream=stream,
    )


def _parse[T: BaseModel](cls: type[T], payload: object) -> T:
    try:
        return cls.model_validate(payload)
    except ValidationError as exc:
        raise InputError(validation_message(exc)) from exc


# --- auth and paths -----------------------------------------------------------------


def _agent(request: Request, policy: Policy) -> str:
    """Agent id from Bearer or `x-goog-api-key`; the `key` query parameter only when neither
    header carries a key."""
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    has_header_key = (scheme.lower() == "bearer" and token.strip()) or request.headers.get(
        "x-goog-api-key", ""
    ).strip()
    query_key = request.query_params.get("key", "").strip()
    if not has_header_key and query_key:
        return agent_for_key(query_key, policy)
    return authenticate(request, policy, key_headers=("x-goog-api-key",))


class _NotFoundError(Exception):
    """Unknown model or method under /models (404 NOT_FOUND)."""


def _model_id(raw: str) -> str:
    model = raw.removeprefix("models/")
    if not _MODEL_RE.fullmatch(model):
        raise InputError(f"invalid model id {model!r}")
    return model


def _split(target: str) -> tuple[str, str]:
    """`<model>:<method>` with the method after the LAST colon (model ids contain colons)."""
    model, sep, method = target.rpartition(":")
    if not sep or method not in _METHODS:
        raise _NotFoundError(f"unknown method in {target!r}")
    return _model_id(model), method


# --- errors -------------------------------------------------------------------------


def _error(code: int, message: str, status: str) -> JSONResponse:
    return JSONResponse(
        {"error": {"code": code, "message": message, "status": status}}, status_code=code
    )


def _error_response(exc: Exception) -> JSONResponse:
    if isinstance(exc, AuthError):
        return _error(401, str(exc), "UNAUTHENTICATED")
    if isinstance(exc, InputError):
        return _error(400, str(exc), "INVALID_ARGUMENT")
    if isinstance(exc, _NotFoundError):
        return _error(404, str(exc), "NOT_FOUND")
    if isinstance(exc, UpstreamError):
        return _error(502, str(exc), "UNAVAILABLE")
    if isinstance(exc, AuditError):
        # no decision without a receipt (ADR-0004): withhold the answer
        return _error(503, "audit log unavailable", "UNAVAILABLE")
    raise exc


_HANDLED = (AuthError, InputError, _NotFoundError, UpstreamError, AuditError)


# --- responses ----------------------------------------------------------------------


def _args(call: ToolCall) -> dict[str, Any]:
    try:
        args = json.loads(call.arguments) if call.arguments.strip() else {}
    except ValueError as exc:
        raise UpstreamError(f"tool call {call.name!r}: arguments are not valid JSON") from exc
    if not isinstance(args, dict):
        raise UpstreamError(f"tool call {call.name!r}: arguments are not a JSON object")
    return args


def _response(result: PipelineResult) -> dict[str, object]:
    parts: list[dict[str, object]] = []
    if result.decision.action is Action.BLOCK:
        parts.append({"text": block_message(result)})
        finish = "SAFETY"
    else:
        output = result.interaction.output
        if output and output.content:
            parts.append({"text": output.content})
        for call in output.tool_calls if output else ():
            function_call: dict[str, object] = {"name": call.name, "args": _args(call)}
            if call.id:
                function_call["id"] = call.id
            parts.append({"functionCall": function_call})
        if not parts:
            parts.append({"text": ""})
        finish = "MAX_TOKENS" if result.finish_reason == "length" else "STOP"
    usage = result.usage
    prompt = usage.prompt_tokens if usage else 0
    completion = usage.completion_tokens if usage else 0
    return {
        "candidates": [
            {"content": {"role": "model", "parts": parts}, "finishReason": finish, "index": 0}
        ],
        "usageMetadata": {
            "promptTokenCount": prompt,
            "candidatesTokenCount": completion,
            "totalTokenCount": prompt + completion,
        },
        "modelVersion": result.interaction.model,
        "responseId": result.interaction.request_id,
        "egida": receipt(result),
    }


async def _sse(chunk: dict[str, object]) -> AsyncIterator[str]:
    yield "data: " + json.dumps(chunk, ensure_ascii=False) + "\n\n"


def _model_entry(name: str) -> dict[str, object]:
    return {
        "name": f"models/{name}",
        "displayName": name,
        "supportedGenerationMethods": list(_METHODS),
    }


# --- routes -------------------------------------------------------------------------


async def _generate(request: Request, model: str, method: str) -> Response:
    runtime = runtime_of(request)
    agent_id = _agent(request, runtime.policy.current().policy)
    payload = await read_json(request)
    if method == "countTokens":
        counted = _parse(_CountTokensRequest, payload)
        inner = counted.generate_content_request or counted
        interaction = _to_interaction(inner, agent_id, model, stream=False)
        return JSONResponse({"totalTokens": math.ceil(input_chars(interaction) / 4)})
    stream = method == "streamGenerateContent"
    req = _parse(_GenerateRequest, payload)
    if not req.contents:
        raise InputError("contents must not be empty")
    result = await runtime.pipeline.run(_to_interaction(req, agent_id, model, stream=stream))
    body = _response(result)
    headers = decision_headers(result)
    if not stream:
        return JSONResponse(body, headers=headers)
    if request.query_params.get("alt") == "sse":
        return StreamingResponse(_sse(body), media_type="text/event-stream", headers=headers)
    return JSONResponse([body], headers=headers)


async def post_model(request: Request, target: str) -> Response:
    try:
        model, method = _split(target)
        return await _generate(request, model, method)
    except _HANDLED as exc:
        return _error_response(exc)


async def list_models(request: Request) -> Response:
    try:
        policy = runtime_of(request).policy.current().policy
        agent_id = _agent(request, policy)
    except _HANDLED as exc:
        return _error_response(exc)
    models = policy.agents[agent_id].allowed_models
    return JSONResponse({"models": [_model_entry(name) for name in models]})


async def get_model(request: Request, target: str) -> Response:
    try:
        policy = runtime_of(request).policy.current().policy
        agent_id = _agent(request, policy)
        model = target.removeprefix("models/")
        if model not in policy.agents[agent_id].allowed_models:
            raise _NotFoundError(f"model {model!r} is not available to this agent")
    except _HANDLED as exc:
        return _error_response(exc)
    return JSONResponse(_model_entry(model))


for _prefix in _PREFIXES:
    router.add_api_route(f"{_prefix}/models/{{target:path}}", post_model, methods=["POST"])
    router.add_api_route(f"{_prefix}/models/{{target:path}}", get_model, methods=["GET"])
# GET /v1/models is the OpenAI model list (http_api, registered first); Gemini's is under /v1beta.
router.add_api_route("/v1beta/models", list_models, methods=["GET"])
