"""Pieces shared by the HTTP entry points: OpenAI Chat Completions (`http_api`), Anthropic
Messages (`anthropic_api`), OpenAI Responses (`responses_api`) and Gemini (`gemini_api`).

Every entry point maps its wire format to the same `Interaction`, runs the same pipeline and
answers with the same decision headers and `egida` receipt; only the envelope differs.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import Request
from pydantic import ValidationError

from egida.adapters.telemetry import TelemetrySink
from egida.core.errors import AuthError, InputError
from egida.core.pipeline import Pipeline, PipelineResult
from egida.core.policy import Policy
from egida.core.ports import PolicySource, SignatureFeed

__all__ = [
    "Runtime",
    "agent_for_key",
    "authenticate",
    "block_message",
    "decision_headers",
    "new_request_id",
    "read_json",
    "receipt",
    "runtime_of",
    "validation_message",
]


@dataclass(frozen=True, slots=True)
class Runtime:
    """Objects built by the composition root (app.py) and stored on app.state.runtime."""

    pipeline: Pipeline
    policy: PolicySource
    feed: SignatureFeed
    registered_kinds: tuple[str, ...]
    telemetry: TelemetrySink
    audit_path: Path


def runtime_of(request: Request) -> Runtime:
    runtime: Runtime = request.app.state.runtime
    return runtime


def agent_for_key(key: str, policy: Policy) -> str:
    """Agent id whose `key_sha256` matches `key`. AuthError when none does."""
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    for agent_id, agent in policy.agents.items():
        if hmac.compare_digest(digest, agent.key_sha256):
            return agent_id
    raise AuthError("unknown API key")


def authenticate(request: Request, policy: Policy, *, key_headers: tuple[str, ...] = ()) -> str:
    """Agent id for the request's API key: `Authorization: Bearer <key>` first, then the first
    non-empty header in `key_headers` (e.g. `x-api-key` for Anthropic clients)."""
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    key = token.strip() if scheme.lower() == "bearer" else ""
    for name in key_headers:
        if key:
            break
        key = request.headers.get(name, "").strip()
    if not key:
        raise AuthError("missing API key")
    return agent_for_key(key, policy)


async def read_json(request: Request) -> object:
    """Request body as JSON. InputError for invalid JSON or text that is not valid UTF-8."""
    try:
        payload: object = await request.json()
    except ValueError as exc:
        raise InputError(f"request body is not valid JSON: {exc}") from exc
    try:  # JSON may escape lone surrogates, which cannot be hashed, scanned or audited
        json.dumps(payload, ensure_ascii=False).encode("utf-8")
    except UnicodeEncodeError as exc:
        raise InputError(f"request body is not valid UTF-8 text: {exc.reason}") from exc
    return payload


def validation_message(exc: ValidationError) -> str:
    """First Pydantic error as `invalid request: <location>: <message>`."""
    first = exc.errors()[0]
    loc = ".".join(str(p) for p in first["loc"])
    return f"invalid request: {loc}: {first['msg']}"


def new_request_id() -> str:
    return "req_" + uuid.uuid4().hex[:16]


def decision_headers(result: PipelineResult) -> dict[str, str]:
    headers = {
        "X-Egida-Decision": result.decision.action.value,
        "X-Egida-Request-Id": result.interaction.request_id,
        "X-Policy-Version": str(result.policy.policy.version),
        "X-Policy-Sha256": result.policy.sha256[:12],
    }
    if result.feed_version is not None:
        headers["X-Feed-Version"] = result.feed_version
    return headers


def receipt(result: PipelineResult) -> dict[str, object]:
    return {
        "decision": result.decision.action.value,
        "request_id": result.interaction.request_id,
        "policy_version": result.policy.policy.version,
        "feed_version": result.feed_version,
        "blocked_by": result.decision.blocked_by,
        "controls": [
            {
                "id": f.control_id,
                "category": f.category.value,
                "score": f.score,
                "tags": list(f.tags),
            }
            for f in result.decision.findings
        ],
        "errors": [{"id": e.control_id, "kind": e.kind} for e in result.decision.errors],
    }


def block_message(result: PipelineResult) -> str:
    """Text the client sees instead of the model's answer when the decision is block."""
    return (
        f"Request blocked by Egida (control: {result.decision.blocked_by}, "
        f"request: {result.interaction.request_id})."
    )
