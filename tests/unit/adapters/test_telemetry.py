"""Telemetry from audit events (A6 §4): percentiles, overhead, window, RPS, exporters."""

from __future__ import annotations

from typing import Any

import pytest

from control_layer.adapters.telemetry import (
    StageStats,
    TelemetrySink,
    TelemetrySnapshot,
    percentile,
    render_prometheus,
    snapshot_to_json,
)
from control_layer.core.audit import AuditEvent, FindingSummary
from control_layer.core.models import Action, Category
from control_layer.core.ports import Clock

pytestmark = pytest.mark.anyio


def _decision(
    clock: Clock,
    latency_ms: dict[str, float],
    decision: Action = Action.ALLOW,
    findings: tuple[FindingSummary, ...] = (),
) -> AuditEvent:
    return AuditEvent(
        type="decision",
        ts=clock.now(),
        decision=decision,
        findings=findings,
        latency_ms=latency_ms,
    )


def _stage(sink: TelemetrySink, name: str) -> StageStats:
    return next(s for s in sink.snapshot().stages if s.stage == name)


def test_percentile_nearest_rank_bounds() -> None:
    values = [float(v) for v in range(100, 0, -1)]
    assert percentile(values, 50) == 50.0
    assert percentile(values, 95) == 95.0
    assert percentile(values, 100) == 100.0
    assert percentile([7.0], 50) == 7.0
    assert percentile([7.0], 95) == 7.0
    assert percentile([], 50) is None
    with pytest.raises(ValueError, match="0..100"):
        percentile(values, 950)


async def test_overhead_is_total_minus_upstream(clock: Clock) -> None:
    sink = TelemetrySink(clock)
    for _ in range(3):
        await sink.emit(_decision(clock, {"total": 100.0, "upstream": 80.0}))
    overhead = _stage(sink, "overhead")
    assert (overhead.count, overhead.p50_ms, overhead.p95_ms) == (3, 20.0, 20.0)


async def test_block_before_model_overhead_equals_total(clock: Clock) -> None:
    sink = TelemetrySink(clock)
    await sink.emit(_decision(clock, {"total": 12.0, "access": 1.0}, Action.BLOCK))
    assert _stage(sink, "overhead").p50_ms == 12.0
    assert "upstream" not in {s.stage for s in sink.snapshot().stages}


async def test_percentiles_come_from_window_counts_are_cumulative(clock: Clock) -> None:
    sink = TelemetrySink(clock, window=4)
    for ms in (1000.0, 900.0, 3.0, 4.0, 5.0, 6.0):
        await sink.emit(_decision(clock, {"total": ms}))
    total = _stage(sink, "total")
    assert (total.count, total.samples) == (6, 4)
    assert (total.p50_ms, total.p95_ms, total.max_ms) == (4.0, 6.0, 6.0)
    assert sink.snapshot().stage_sum_ms["total"] == 1918.0


async def test_non_decision_events_count_only_as_events(clock: Clock) -> None:
    sink = TelemetrySink(clock)
    await sink.emit(AuditEvent(type="policy_rejected", ts=clock.now(), detail="bad yaml"))
    await sink.emit(_decision(clock, {"total": 1.0}))
    snap = sink.snapshot()
    assert snap.events == {"policy_rejected": 1, "decision": 1}
    assert snap.requests_total == 1
    assert snap.decisions == {"allow": 1}


async def test_rps_counts_decisions_of_last_minute(clock: Any) -> None:
    sink = TelemetrySink(clock)
    for _ in range(30):
        await sink.emit(_decision(clock, {"total": 1.0}))
    assert sink.snapshot().rps_1m == 0.5
    clock.advance(61)
    assert sink.snapshot().rps_1m == 0.0
    assert sink.snapshot().requests_total == 30


async def test_stage_order_total_overhead_upstream_then_alphabetical(clock: Clock) -> None:
    sink = TelemetrySink(clock)
    await sink.emit(
        _decision(clock, {"upstream": 5.0, "output:pii": 1.0, "access": 1.0, "total": 9.0})
    )
    names = [s.stage for s in sink.snapshot().stages]
    assert names == ["total", "overhead", "upstream", "access", "output:pii"]


async def test_render_prometheus_format(clock: Clock) -> None:
    sink = TelemetrySink(clock)
    pii = FindingSummary("pii", Category.PII, 0.9, Action.REDACT)
    await sink.emit(
        _decision(
            clock, {"total": 100.0, "upstream": 80.0, "input:pii": 0.5}, Action.REDACT, (pii,)
        )
    )
    assert render_prometheus(sink.snapshot()) == (
        "# HELP control_layer_stage_latency_seconds Per-stage latency"
        " (quantiles over last N samples).\n"
        "# TYPE control_layer_stage_latency_seconds summary\n"
        'control_layer_stage_latency_seconds{stage="total",quantile="0.5"} 0.1\n'
        'control_layer_stage_latency_seconds{stage="total",quantile="0.95"} 0.1\n'
        'control_layer_stage_latency_seconds_sum{stage="total"} 0.1\n'
        'control_layer_stage_latency_seconds_count{stage="total"} 1\n'
        'control_layer_stage_latency_seconds{stage="overhead",quantile="0.5"} 0.02\n'
        'control_layer_stage_latency_seconds{stage="overhead",quantile="0.95"} 0.02\n'
        'control_layer_stage_latency_seconds_sum{stage="overhead"} 0.02\n'
        'control_layer_stage_latency_seconds_count{stage="overhead"} 1\n'
        'control_layer_stage_latency_seconds{stage="upstream",quantile="0.5"} 0.08\n'
        'control_layer_stage_latency_seconds{stage="upstream",quantile="0.95"} 0.08\n'
        'control_layer_stage_latency_seconds_sum{stage="upstream"} 0.08\n'
        'control_layer_stage_latency_seconds_count{stage="upstream"} 1\n'
        'control_layer_stage_latency_seconds{stage="input:pii",quantile="0.5"} 0.0005\n'
        'control_layer_stage_latency_seconds{stage="input:pii",quantile="0.95"} 0.0005\n'
        'control_layer_stage_latency_seconds_sum{stage="input:pii"} 0.0005\n'
        'control_layer_stage_latency_seconds_count{stage="input:pii"} 1\n'
        "# HELP control_layer_decisions_total Decisions by action.\n"
        "# TYPE control_layer_decisions_total counter\n"
        'control_layer_decisions_total{decision="redact"} 1\n'
        "# HELP control_layer_findings_total Findings by control and resulting action.\n"
        "# TYPE control_layer_findings_total counter\n"
        'control_layer_findings_total{control_id="pii",action="redact"} 1\n'
        "# HELP control_layer_audit_events_total Audit events by type.\n"
        "# TYPE control_layer_audit_events_total counter\n"
        'control_layer_audit_events_total{type="decision"} 1\n'
    )


def test_render_prometheus_escapes_labels_and_skips_empty_stages() -> None:
    snap = TelemetrySnapshot(
        generated_at=0.0,
        started_at=0.0,
        window=4,
        requests_total=0,
        rps_1m=0.0,
        decisions={},
        events={},
        findings={},
        stages=(StageStats('in"put\\x\ny', count=0, samples=0, p50_ms=0, p95_ms=0, max_ms=0),),
        stage_sum_ms={'in"put\\x\ny': 0.0},
    )
    text = render_prometheus(snap)
    assert 'stage="in\\"put\\\\x\\ny"' in text
    assert 'quantile="' not in text
    assert "NaN" not in text
    assert text.endswith("\n")


async def test_snapshot_json_is_telemetry_v1_rounded_to_0_1_ms(clock: Clock) -> None:
    sink = TelemetrySink(clock)
    pii = FindingSummary("pii", Category.PII, 0.9, Action.REDACT)
    await sink.emit(_decision(clock, {"total": 12.345, "upstream": 10.0}, Action.REDACT, (pii,)))
    body = snapshot_to_json(sink.snapshot())
    assert body["schema"] == "telemetry.v1"
    assert body["findings"] == [{"control_id": "pii", "action": "redact", "count": 1}]
    stages = body["stages"]
    assert isinstance(stages, list)
    assert stages[0] == {
        "stage": "total",
        "count": 1,
        "samples": 1,
        "p50_ms": 12.3,
        "p95_ms": 12.3,
        "max_ms": 12.3,
    }
    assert stages[1]["p50_ms"] == 2.3
