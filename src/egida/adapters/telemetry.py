"""Latency and decision telemetry computed from audit events (R5, A6 §4).

`TelemetrySink` is an AuditSink placed in the audit fanout: every `latency_ms` key of an event
(`total`, `access`, `input:pii`, `upstream`, ...) becomes a stage with a cumulative count/sum and a
bounded window of recent samples for p50/p95/max. The synthetic stage `overhead` is
`total - upstream`, the time added by the Egida proxy itself (== `total` when the model was not
called).

Hand-written Prometheus text format instead of `prometheus-client`: its Summary does not compute
quantiles and Histogram quantiles need a Prometheus server; we compute percentiles ourselves for
the JSON view anyway. Seconds in `/metrics` (Prometheus convention), milliseconds in JSON.
"""

from __future__ import annotations

import math
from collections import Counter, deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from egida.core.audit import AuditEvent
from egida.core.ports import Clock

__all__ = [
    "PROMETHEUS_CONTENT_TYPE",
    "TELEMETRY_SCHEMA",
    "StageStats",
    "TelemetrySink",
    "TelemetrySnapshot",
    "percentile",
    "render_prometheus",
    "snapshot_to_json",
]

TELEMETRY_SCHEMA = "telemetry.v1"
PROMETHEUS_CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"
RPS_WINDOW_S = 60.0
_FIRST_STAGES = ("total", "overhead", "upstream")


def percentile(values: Sequence[float], q: float) -> float | None:
    """Nearest-rank percentile, `q` in 0..100 (`percentile(v, 95)`); None for no values.

    Hand-written because `statistics.quantiles` raises for fewer than two samples.
    """
    if not 0 <= q <= 100:
        raise ValueError(f"percentile q must be in 0..100, got {q}")
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(q * len(ordered) / 100) - 1)]


@dataclass(frozen=True, slots=True)
class StageStats:
    stage: str
    count: int  # cumulative since start
    samples: int  # samples in the window the percentiles come from (<= window)
    p50_ms: float
    p95_ms: float
    max_ms: float


@dataclass(frozen=True, slots=True)
class TelemetrySnapshot:
    generated_at: float
    started_at: float
    window: int
    requests_total: int
    rps_1m: float
    decisions: Mapping[str, int]
    events: Mapping[str, int]
    findings: Mapping[tuple[str, str], int]  # (control_id, action) -> count
    stages: tuple[StageStats, ...]
    stage_sum_ms: Mapping[str, float]  # cumulative sum, the `_sum` series in Prometheus


class _Stage:
    __slots__ = ("count", "samples", "sum_ms")

    def __init__(self, window: int) -> None:
        self.samples: deque[float] = deque(maxlen=window)
        self.count = 0
        self.sum_ms = 0.0

    def add(self, ms: float) -> None:
        self.samples.append(ms)
        self.count += 1
        self.sum_ms += ms


class TelemetrySink:
    """AuditSink keeping in-process telemetry (lost on restart; no history is read at start)."""

    def __init__(self, clock: Clock, window: int = 1024) -> None:
        if window < 1:
            raise ValueError(f"telemetry window must be >= 1, got {window}")
        self._clock = clock
        self._window = window
        self._started_at = clock.now()
        self._requests = 0
        self._decisions: Counter[str] = Counter()
        self._events: Counter[str] = Counter()
        self._findings: Counter[tuple[str, str]] = Counter()
        self._stages: dict[str, _Stage] = {}
        self._recent: deque[float] = deque()  # decision timestamps of the last RPS_WINDOW_S

    async def emit(self, event: AuditEvent) -> None:
        # No await in here: under asyncio the whole update runs atomically, without a lock.
        self._events[event.type] += 1
        if event.type == "decision":
            self._requests += 1
            if event.decision is not None:
                self._decisions[event.decision.value] += 1
            for f in event.findings:
                self._findings[(f.control_id, f.action.value)] += 1
            self._recent.append(event.ts)
        latency = event.latency_ms
        for stage, ms in latency.items():
            self._stage(stage).add(ms)
        if "total" in latency:
            overhead = latency["total"] - latency.get("upstream", 0.0)
            self._stage("overhead").add(max(0.0, overhead))
        self._trim()

    def snapshot(self) -> TelemetrySnapshot:
        self._trim()
        names = sorted(self._stages, key=lambda s: (_rank(s), s))
        stages = tuple(_stats(name, self._stages[name]) for name in names)
        return TelemetrySnapshot(
            generated_at=self._clock.now(),
            started_at=self._started_at,
            window=self._window,
            requests_total=self._requests,
            rps_1m=len(self._recent) / RPS_WINDOW_S,
            decisions=dict(self._decisions),
            events=dict(self._events),
            findings=dict(self._findings),
            stages=stages,
            stage_sum_ms={name: self._stages[name].sum_ms for name in names},
        )

    def _stage(self, name: str) -> _Stage:
        stage = self._stages.get(name)
        if stage is None:
            stage = self._stages[name] = _Stage(self._window)
        return stage

    def _trim(self) -> None:
        cutoff = self._clock.now() - RPS_WINDOW_S
        while self._recent and self._recent[0] < cutoff:
            self._recent.popleft()


def _rank(stage: str) -> int:
    return _FIRST_STAGES.index(stage) if stage in _FIRST_STAGES else len(_FIRST_STAGES)


def _stats(name: str, stage: _Stage) -> StageStats:
    samples = list(stage.samples)
    return StageStats(
        stage=name,
        count=stage.count,
        samples=len(samples),
        p50_ms=percentile(samples, 50) or 0.0,
        p95_ms=percentile(samples, 95) or 0.0,
        max_ms=max(samples, default=0.0),
    )


# --- exporters -----------------------------------------------------------------------


def _label(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _seconds(ms: float) -> str:
    return repr(round(ms / 1000, 7))


def render_prometheus(s: TelemetrySnapshot) -> str:
    """Prometheus text exposition format 0.0.4. Stages without samples get no quantile lines."""
    metric = "egida_stage_latency_seconds"
    lines = [
        f"# HELP {metric} Per-stage latency (quantiles over last N samples).",
        f"# TYPE {metric} summary",
    ]
    for st in s.stages:
        stage = _label(st.stage)
        if st.samples:
            lines.append(f'{metric}{{stage="{stage}",quantile="0.5"}} {_seconds(st.p50_ms)}')
            lines.append(f'{metric}{{stage="{stage}",quantile="0.95"}} {_seconds(st.p95_ms)}')
        lines.append(f'{metric}_sum{{stage="{stage}"}} {_seconds(s.stage_sum_ms[st.stage])}')
        lines.append(f'{metric}_count{{stage="{stage}"}} {st.count}')
    lines += [
        "# HELP egida_decisions_total Decisions by action.",
        "# TYPE egida_decisions_total counter",
    ]
    lines += [
        f'egida_decisions_total{{decision="{_label(d)}"}} {n}'
        for d, n in sorted(s.decisions.items())
    ]
    lines += [
        "# HELP egida_findings_total Findings by control and resulting action.",
        "# TYPE egida_findings_total counter",
    ]
    lines += [
        f'egida_findings_total{{control_id="{_label(c)}",action="{_label(a)}"}} {n}'
        for (c, a), n in sorted(s.findings.items())
    ]
    lines += [
        "# HELP egida_audit_events_total Audit events by type.",
        "# TYPE egida_audit_events_total counter",
    ]
    lines += [
        f'egida_audit_events_total{{type="{_label(t)}"}} {n}' for t, n in sorted(s.events.items())
    ]
    return "\n".join(lines) + "\n"


def snapshot_to_json(s: TelemetrySnapshot) -> dict[str, object]:
    """`telemetry.v1` (contract for the dashboard; fields are only ever added)."""
    return {
        "schema": TELEMETRY_SCHEMA,
        "generated_at": s.generated_at,
        "started_at": s.started_at,
        "window": s.window,
        "requests_total": s.requests_total,
        "rps_1m": round(s.rps_1m, 3),
        "decisions": dict(sorted(s.decisions.items())),
        "events": dict(sorted(s.events.items())),
        "findings": [
            {"control_id": c, "action": a, "count": n} for (c, a), n in sorted(s.findings.items())
        ],
        "stages": [
            {
                "stage": st.stage,
                "count": st.count,
                "samples": st.samples,
                "p50_ms": round(st.p50_ms, 1),
                "p95_ms": round(st.p95_ms, 1),
                "max_ms": round(st.max_ms, 1),
            }
            for st in s.stages
        ],
    }
