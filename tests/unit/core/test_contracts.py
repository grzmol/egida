"""Contract tests for the frozen core types (A0)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict

from egida.core.audit import AuditEvent, FindingSummary
from egida.core.errors import PolicyError
from egida.core.models import (
    Action,
    Category,
    Interaction,
    Message,
    Side,
    Span,
    ToolCall,
    ToolDef,
    Usage,
)
from egida.core.policy import build_policy
from egida.core.texts import apply_redactions, iter_texts

ROOT = Path(__file__).resolve().parents[3]


class DummyParams(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    min_len: int = 3


def _control(**overrides: Any) -> dict[str, Any]:
    control: dict[str, Any] = {
        "id": "dummy",
        "kind": "dummy",
        "sides": ["input"],
        "action": "block",
        "threshold": 0.5,
        "params": {},
    }
    control.update(overrides)
    return control


def _interaction() -> Interaction:
    return Interaction(
        request_id="req_1",
        agent_id="demo-agent",
        model="llama3.2:3b",
        messages=(
            Message(role="system", content="You are helpful."),
            Message(role="user", content="PESEL 44051401359 please"),
            Message(
                role="assistant",
                content="",
                tool_calls=(ToolCall(id="c1", name="read_file", arguments='{"path": "a.txt"}'),),
            ),
            Message(role="tool", content="file body", tool_call_id="c1"),
        ),
        tools=(ToolDef(name="read_file", description="Reads a file.", parameters_json="{}"),),
        output=Message(
            role="assistant",
            content="done",
            tool_calls=(ToolCall(id="c2", name="read_file", arguments='{"path": "b"}'),),
        ),
    )


# --- policy ---------------------------------------------------------------


def test_valid_policy_is_accepted(policy_dict: dict[str, Any]) -> None:
    policy = build_policy(policy_dict, {})
    assert policy.version == 1
    assert policy.agents["demo-agent"].budget == "default"


def test_params_become_validated_instances(policy_dict: dict[str, Any]) -> None:
    policy_dict["controls"] = [_control(params={"min_len": 7})]
    policy = build_policy(policy_dict, {"dummy": DummyParams})
    params = policy.controls[0].params
    assert isinstance(params, DummyParams)
    assert params.min_len == 7


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda p: p["controls"].extend([_control(), _control()]), id="duplicate-id"),
        pytest.param(lambda p: p["controls"].append(_control(kind="nope")), id="unknown-kind"),
        pytest.param(lambda p: p.update(unexpected=1), id="unknown-root-field"),
        pytest.param(lambda p: p["limits"].update(max_tokenz=5), id="unknown-nested-field"),
        pytest.param(lambda p: p["controls"].append(_control(threshold=1.5)), id="threshold>1"),
        pytest.param(
            lambda p: p["agents"]["demo-agent"].update(budget="missing"), id="missing-budget"
        ),
        pytest.param(
            lambda p: p["agents"]["demo-agent"].update(key_sha256="sk-demo-agent"),
            id="plaintext-key",
        ),
        pytest.param(
            lambda p: p["agents"]["demo-agent"].update(allowed_models=["gpt-4o"]),
            id="unknown-model",
        ),
        pytest.param(
            lambda p: p["models"]["llama3.2:3b"].update(upstream="missing"),
            id="unknown-upstream",
        ),
        pytest.param(
            lambda p: p["controls"].append(_control(params={"min_len": "x"})), id="bad-params"
        ),
        pytest.param(
            lambda p: p["controls"].append(_control(params={"other": 1})), id="extra-params"
        ),
    ],
)
def test_invalid_policy_is_rejected(policy_dict: dict[str, Any], mutate: Any) -> None:
    mutate(policy_dict)
    with pytest.raises(PolicyError) as exc:
        build_policy(policy_dict, {"dummy": DummyParams})
    assert exc.value.errors, "PolicyError must carry human-readable errors"


def test_non_mapping_policy_is_rejected() -> None:
    with pytest.raises(PolicyError):
        build_policy(["not", "a", "mapping"], {})  # type: ignore[arg-type]


# --- texts ----------------------------------------------------------------


def test_iter_texts_input_targets() -> None:
    targets = [t for t, _ in iter_texts(_interaction(), Side.INPUT)]
    assert targets == [
        "messages[0].content",
        "messages[1].content",
        "messages[2].content",
        "messages[2].tool_calls[0].arguments",
        "messages[3].content",
        "tools[0].description",
        "tools[0].parameters_json",  # property descriptions reach the model: scanned too
    ]


def test_iter_texts_output_targets() -> None:
    texts = dict(iter_texts(_interaction(), Side.OUTPUT))
    assert texts == {
        "output.content": "done",
        "output.tool_calls[0].arguments": '{"path": "b"}',
    }


def test_apply_redactions_merges_overlaps_and_keeps_original() -> None:
    original = _interaction()
    text = original.messages[1].content
    start = text.index("44051401359")
    spans = [
        Span("messages[1].content", start, start + 6, "pesel"),
        Span("messages[1].content", start + 3, start + 11, "pesel"),
    ]
    redacted = apply_redactions(original, spans)
    assert redacted.messages[1].content == "PESEL [REDACTED:pesel] please"
    assert original.messages[1].content == text


def test_apply_redactions_on_output_and_tool_args() -> None:
    redacted = apply_redactions(
        _interaction(),
        [
            Span("output.content", 0, 4, "x"),
            Span("messages[2].tool_calls[0].arguments", 10, 15, "path"),
        ],
    )
    assert redacted.output is not None
    assert redacted.output.content == "[REDACTED:x]"
    assert redacted.messages[2].tool_calls[0].arguments == '{"path": "[REDACTED:path]"}'


@pytest.mark.parametrize(
    "span",
    [
        Span("messages[9].content", 0, 1, "x"),
        Span("nonsense", 0, 1, "x"),
        Span("messages[1].content", 5, 999, "x"),
        Span("messages[1].content", 4, 2, "x"),
    ],
)
def test_apply_redactions_rejects_bad_spans(span: Span) -> None:
    with pytest.raises(ValueError):
        apply_redactions(_interaction(), [span])


# --- audit ----------------------------------------------------------------


def test_audit_event_is_json_serializable() -> None:
    event = AuditEvent(
        type="decision",
        ts=1.0,
        request_id="req_1",
        agent_id="demo-agent",
        decision=Action.BLOCK,
        blocked_by="pii",
        findings=(
            FindingSummary(
                control_id="pii",
                category=Category.PII,
                score=1.0,
                action=Action.BLOCK,
                tags=("owasp.llm02-2025",),
                evidence="PESEL 4405******9",
            ),
        ),
        usage=Usage(10, 5),
        latency_ms={"total": 3.2},
    )
    data = event.to_dict()
    assert data["schema"] == "audit.v1"
    decoded = json.loads(json.dumps(data))
    assert decoded == data  # identical to a line parsed back from the JSONL log
    assert decoded["decision"] == "block"
    assert decoded["findings"][0]["category"] == "pii"
    assert decoded["usage"] == {"prompt_tokens": 10, "completion_tokens": 5}
