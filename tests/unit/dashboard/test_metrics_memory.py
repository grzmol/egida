import json

import pytest

from control_layer.adapters.metrics_memory import MetricsMemory, nearest_rank
from control_layer.core.audit import AuditEvent, FindingSummary
from control_layer.core.models import Action, BudgetUsage, Category


def decision(
    action: Action,
    *findings: FindingSummary,
    blocked_by: str | None = None,
    agent: str = "demo-agent",
    total_ms: float = 10.0,
    cost: float = 0.001,
) -> AuditEvent:
    return AuditEvent(
        type="decision",
        ts=1.0,
        request_id="req_x",
        agent_id=agent,
        model="llama3.2:3b",
        decision=action,
        blocked_by=blocked_by,
        findings=findings,
        cost=cost,
        budget=BudgetUsage(agent, 3600, 100, cost, 1, 50000, 1.0, 300),
        latency_ms={"total": total_ms, "input:pii": 1.0},
    )


def finding(control_id: str, action: Action, category: Category = Category.PII) -> FindingSummary:
    return FindingSummary(control_id, category, 1.0, action, (), "pesel 44*******59@messages[0]")


@pytest.mark.anyio
async def test_counts_decisions_controls_errors_and_policy_events() -> None:
    metrics = MetricsMemory()
    await metrics.emit(decision(Action.ALLOW))
    await metrics.emit(
        decision(Action.BLOCK, finding("pii", Action.BLOCK), blocked_by="pii", agent="ci-agent")
    )
    await metrics.emit(
        decision(Action.REDACT, finding("secrets", Action.REDACT, Category.SECRET))
    )
    await metrics.emit(decision(Action.ALLOW, finding("prompt_guard", Action.ALLOW)))
    await metrics.emit(AuditEvent(type="control_error", ts=2.0, blocked_by="prompt_guard"))
    await metrics.emit(AuditEvent(type="upstream_error", ts=2.5, detail="timeout"))
    await metrics.emit(AuditEvent(type="policy_rejected", ts=3.0, detail="controls.0.threshold"))
    await metrics.emit(
        AuditEvent(type="policy_reloaded", ts=4.0, policy_version=2, policy_sha256="ab" * 32)
    )

    stats = metrics.stats()
    assert stats["requests"] == {"total": 4, "allow": 2, "redact": 1, "block": 1}
    assert stats["controls"] == {
        "pii": {"block": 1, "redact": 0, "below_threshold": 0, "errors": 0},
        "secrets": {"block": 0, "redact": 1, "below_threshold": 0, "errors": 0},
        "prompt_guard": {"block": 0, "redact": 0, "below_threshold": 1, "errors": 1},
    }
    assert stats["upstream_errors"] == 1
    assert stats["policy"]["last_rejected"]["detail"] == "controls.0.threshold"
    assert stats["policy"]["last_reloaded"]["policy_version"] == 2
    assert set(stats["budgets"]) == {"demo-agent", "ci-agent"}
    assert stats["cost"]["demo-agent"] == pytest.approx(0.003)
    json.dumps(stats)  # the API returns it as JSON


def test_nearest_rank_percentiles() -> None:
    samples = [float(v) for v in range(1, 101)]
    assert nearest_rank(samples, 50) == 50.0
    assert nearest_rank(samples, 95) == 95.0
    assert nearest_rank([7.0], 95) == 7.0
    assert nearest_rank([], 95) is None


@pytest.mark.anyio
async def test_latency_window_and_event_buffer_are_bounded() -> None:
    metrics = MetricsMemory()
    for i in range(1200):
        await metrics.emit(decision(Action.ALLOW, total_ms=float(i)))
    latency = metrics.stats()["latency_ms"]["total"]
    assert latency["count"] == 1000  # only the newest 1000 samples
    assert latency["p50"] == 699.0
    assert len(metrics.events(limit=10_000)) == 500


@pytest.mark.anyio
async def test_events_newest_first_with_filters() -> None:
    metrics = MetricsMemory()
    await metrics.emit(decision(Action.ALLOW))
    await metrics.emit(decision(Action.BLOCK, finding("pii", Action.BLOCK), blocked_by="pii"))
    await metrics.emit(decision(Action.REDACT, finding("secrets", Action.REDACT)))

    assert [e["decision"] for e in metrics.events()] == ["redact", "block", "allow"]
    assert [e["decision"] for e in metrics.events(decision="block")] == ["block"]
    assert [e["decision"] for e in metrics.events(control="secrets")] == ["redact"]
    assert len(metrics.events(limit=1)) == 1
