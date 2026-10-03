"""Pipeline (A1): stage order, aggregation, redaction, timeouts, on_error, policy snapshot."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any, ClassVar

import pytest
from pydantic import BaseModel, ConfigDict

from control_layer.adapters.budget_passthrough import PassthroughBudgetStore
from control_layer.adapters.fake_model import FakeModelClient
from control_layer.core.audit import AuditEvent
from control_layer.core.errors import UpstreamError
from control_layer.core.models import Action, Category, Finding, Interaction, Message, Span
from control_layer.core.pipeline import Pipeline
from control_layer.core.policy import build_policy
from control_layer.core.ports import PolicySnapshot, ScanContext

pytestmark = pytest.mark.anyio


class NoParams(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ScriptedDetector:
    """Detector whose behaviour is a function of the scan context."""

    kind: ClassVar[str] = "scripted"
    Params: ClassVar[type[BaseModel]] = NoParams

    def __init__(self, behaviour: Callable[[ScanContext], Any]) -> None:
        self._behaviour = behaviour
        self.calls = 0

    async def scan(self, ctx: ScanContext) -> list[Finding]:
        self.calls += 1
        result = self._behaviour(ctx)
        if asyncio.iscoroutine(result):
            result = await result
        return list(result)


class MemorySink:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    async def emit(self, event: AuditEvent) -> None:
        self.events.append(event)

    def of_type(self, kind: str) -> list[AuditEvent]:
        return [e for e in self.events if e.type == kind]


class SequencePolicySource:
    def __init__(self, *snapshots: PolicySnapshot) -> None:
        self._snapshots = list(snapshots)
        self.calls = 0

    def current(self) -> PolicySnapshot:
        snap = self._snapshots[min(self.calls, len(self._snapshots) - 1)]
        self.calls += 1
        return snap

    def last_error(self) -> str | None:
        return None


def _snapshot(policy_dict: dict[str, Any], controls: list[dict[str, Any]]) -> PolicySnapshot:
    policy_dict = {**policy_dict, "controls": controls}
    kinds = {c["kind"] for c in controls}
    policy = build_policy(policy_dict, dict.fromkeys(kinds, NoParams))
    return PolicySnapshot(policy=policy, sha256="a" * 64, loaded_at=0.0, source="test")


def _control(cid: str, **kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": cid,
        "kind": cid,
        "sides": ["input"],
        "action": "block",
        "threshold": 0.5,
    }
    base.update(kw)
    return base


def _interaction(text: str = "hello", model: str = "llama3.2:3b", **kw: Any) -> Interaction:
    return Interaction(
        request_id="req_test",
        agent_id="demo-agent",
        model=model,
        messages=(Message(role="user", content=text),),
        **kw,
    )


def _finding(ctx: ScanContext, score: float = 1.0, spans: tuple[Span, ...] = ()) -> Finding:
    return Finding(control_id=ctx.control_id, category=Category.PII, score=score, spans=spans)


def _span_on(ctx: ScanContext, needle: str) -> tuple[Span, ...]:
    from control_layer.core.texts import iter_texts

    for target, text in iter_texts(ctx.interaction, ctx.side):
        i = text.find(needle)
        if i >= 0:
            return (Span(target, i, i + len(needle), "pii"),)
    return ()


class _TickClock:
    """Monotonic clock advancing 1 ms per read, so stage latencies are non-zero and ordered."""

    def __init__(self) -> None:
        self._t = 0.0

    def now(self) -> float:
        return 1_759_489_200.0 + self._t

    def monotonic(self) -> float:
        self._t += 0.001
        return self._t


def _pipeline(
    snapshot_source: Any,
    detectors: dict[str, Any],
    model: FakeModelClient | None = None,
    sink: MemorySink | None = None,
) -> tuple[Pipeline, FakeModelClient, MemorySink]:
    model = model or FakeModelClient(reply="model says hi")
    sink = sink or MemorySink()
    pipeline = Pipeline(
        policy=snapshot_source,
        detectors=detectors,
        model=model,
        budgets=PassthroughBudgetStore(),
        audit=sink,
        clock=_TickClock(),
    )
    return pipeline, model, sink


async def test_no_controls_allows_and_audits_once(policy_dict: dict[str, Any]) -> None:
    pipeline, model, sink = _pipeline(SequencePolicySource(_snapshot(policy_dict, [])), {})
    result = await pipeline.run(_interaction())
    assert result.decision.action is Action.ALLOW
    assert model.calls == 1
    assert result.interaction.output is not None
    assert result.interaction.output.content == "model says hi"
    decisions = sink.of_type("decision")
    assert len(decisions) == 1
    assert decisions[0].decision is Action.ALLOW
    assert "total" in decisions[0].latency_ms


async def test_input_block_short_circuits(policy_dict: dict[str, Any]) -> None:
    first = ScriptedDetector(lambda ctx: [_finding(ctx)])
    second = ScriptedDetector(lambda ctx: [])
    snap = _snapshot(policy_dict, [_control("first"), _control("second")])
    pipeline, model, _ = _pipeline(SequencePolicySource(snap), {"first": first, "second": second})
    result = await pipeline.run(_interaction())
    assert result.decision.action is Action.BLOCK
    assert result.decision.blocked_by == "first"
    assert model.calls == 0
    assert second.calls == 0
    assert result.interaction.output is None


async def test_input_redaction_reaches_model_redacted(policy_dict: dict[str, Any]) -> None:
    det = ScriptedDetector(lambda ctx: [_finding(ctx, spans=_span_on(ctx, "44051401359"))])
    snap = _snapshot(policy_dict, [_control("pii", action="redact")])
    pipeline, model, sink = _pipeline(SequencePolicySource(snap), {"pii": det})
    result = await pipeline.run(_interaction("PESEL 44051401359"))
    assert result.decision.action is Action.REDACT
    assert model.last_interaction is not None
    assert model.last_interaction.messages[0].content == "PESEL [REDACTED:pii]"
    assert "44051401359" not in repr(sink.events)


async def test_output_redaction(policy_dict: dict[str, Any]) -> None:
    det = ScriptedDetector(lambda ctx: [_finding(ctx, spans=_span_on(ctx, "secret"))])
    snap = _snapshot(policy_dict, [_control("pii", action="redact", sides=["output"])])
    pipeline, _, _ = _pipeline(
        SequencePolicySource(snap), {"pii": det}, model=FakeModelClient(reply="the secret is x")
    )
    result = await pipeline.run(_interaction())
    assert result.decision.action is Action.REDACT
    assert result.interaction.output is not None
    assert result.interaction.output.content == "the [REDACTED:pii] is x"


async def test_redact_without_spans_blocks(policy_dict: dict[str, Any]) -> None:
    det = ScriptedDetector(lambda ctx: [_finding(ctx)])
    snap = _snapshot(policy_dict, [_control("pii", action="redact")])
    pipeline, model, _ = _pipeline(SequencePolicySource(snap), {"pii": det})
    result = await pipeline.run(_interaction())
    assert result.decision.action is Action.BLOCK
    assert result.decision.blocked_by == "pii"
    assert model.calls == 0


async def test_below_threshold_allows_but_is_audited(policy_dict: dict[str, Any]) -> None:
    det = ScriptedDetector(lambda ctx: [_finding(ctx, score=0.2)])
    snap = _snapshot(policy_dict, [_control("pii", threshold=0.5)])
    pipeline, _, sink = _pipeline(SequencePolicySource(snap), {"pii": det})
    result = await pipeline.run(_interaction())
    assert result.decision.action is Action.ALLOW
    summary = sink.of_type("decision")[0].findings
    assert [(f.control_id, f.action) for f in summary] == [("pii", Action.ALLOW)]


def _raise(ctx: ScanContext) -> list[Finding]:
    raise RuntimeError("detector exploded")


async def _hang(ctx: ScanContext) -> list[Finding]:
    await asyncio.sleep(5)
    return []


@pytest.mark.parametrize(
    ("behaviour", "kind"), [(_raise, "exception"), (_hang, "timeout")], ids=["raise", "hang"]
)
@pytest.mark.parametrize(
    ("on_error", "expected"), [("block", Action.BLOCK), ("allow", Action.ALLOW)]
)
async def test_control_errors_follow_on_error(
    policy_dict: dict[str, Any],
    behaviour: Callable[[ScanContext], Any],
    kind: str,
    on_error: str,
    expected: Action,
) -> None:
    det = ScriptedDetector(behaviour)
    snap = _snapshot(policy_dict, [_control("guard", on_error=on_error, timeout_ms=20)])
    pipeline, _, sink = _pipeline(SequencePolicySource(snap), {"guard": det})
    result = await pipeline.run(_interaction())
    assert result.decision.action is expected
    assert [e.kind for e in result.decision.errors] == [kind]
    errors = sink.of_type("control_error")
    assert len(errors) == 1
    assert errors[0].detail is not None
    assert "guard" in errors[0].detail
    assert errors[0].control_id == "guard"
    assert errors[0].blocked_by == ("guard" if on_error == "block" else None)


async def test_finding_with_foreign_control_id_is_an_error(policy_dict: dict[str, Any]) -> None:
    det = ScriptedDetector(lambda ctx: [Finding("someone-else", Category.PII, 1.0)])
    snap = _snapshot(policy_dict, [_control("pii", action="allow")])
    pipeline, _, _ = _pipeline(SequencePolicySource(snap), {"pii": det})
    result = await pipeline.run(_interaction())
    assert result.decision.action is Action.BLOCK
    assert result.decision.errors[0].kind == "exception"


async def test_disallowed_model_blocks(policy_dict: dict[str, Any]) -> None:
    pipeline, model, _ = _pipeline(SequencePolicySource(_snapshot(policy_dict, [])), {})
    result = await pipeline.run(_interaction(model="gpt-4o"))
    assert result.decision.action is Action.BLOCK
    assert result.decision.blocked_by == "access.model"
    assert model.calls == 0


async def test_oversized_input_blocks_and_max_tokens_is_clamped(
    policy_dict: dict[str, Any],
) -> None:
    policy_dict["limits"]["max_input_chars"] = 10
    pipeline, model, _ = _pipeline(SequencePolicySource(_snapshot(policy_dict, [])), {})
    blocked = await pipeline.run(_interaction("x" * 11))
    assert blocked.decision.blocked_by == "limit"
    assert model.calls == 0
    allowed = await pipeline.run(_interaction("short", max_tokens=1_000_000))
    assert allowed.decision.action is Action.ALLOW
    assert model.last_interaction is not None
    assert model.last_interaction.max_tokens == 1024


async def test_disabled_or_other_side_controls_do_not_run(policy_dict: dict[str, Any]) -> None:
    off = ScriptedDetector(lambda ctx: [_finding(ctx)])
    out_only = ScriptedDetector(lambda ctx: [])
    snap = _snapshot(
        policy_dict, [_control("off", enabled=False), _control("outonly", sides=["output"])]
    )
    pipeline, _, _ = _pipeline(SequencePolicySource(snap), {"off": off, "outonly": out_only})
    result = await pipeline.run(_interaction())
    assert result.decision.action is Action.ALLOW
    assert off.calls == 0
    assert out_only.calls == 1  # only on the output side


async def test_request_uses_one_policy_snapshot(policy_dict: dict[str, Any]) -> None:
    blocking = _snapshot(policy_dict, [_control("pii")])
    lenient = _snapshot(policy_dict, [_control("pii", action="allow")])
    det = ScriptedDetector(lambda ctx: [_finding(ctx)])
    source = SequencePolicySource(blocking, lenient)
    pipeline, _, _ = _pipeline(source, {"pii": det})
    result = await pipeline.run(_interaction())
    assert source.calls == 1
    assert result.decision.action is Action.BLOCK


async def test_upstream_error_is_audited_and_raised(policy_dict: dict[str, Any]) -> None:
    pipeline, _, sink = _pipeline(
        SequencePolicySource(_snapshot(policy_dict, [])),
        {},
        model=FakeModelClient(raise_error=True),
    )
    with pytest.raises(UpstreamError):
        await pipeline.run(_interaction())
    assert len(sink.of_type("upstream_error")) == 1
