"""In-memory metrics computed from audit events (AuditSink). Single source of truth: audit.v1.

emit() runs on the event loop and does no I/O, so plain structures without locks suffice.
Events carry no prompt or response content (audit.v1), so nothing here can leak it.
"""

import dataclasses
import math
from collections import Counter, defaultdict, deque

from control_layer.core.audit import AuditEvent
from control_layer.core.models import Action

EVENT_BUFFER = 500
LATENCY_WINDOW = 1000
_ACTION_COUNTER = {Action.BLOCK: "block", Action.REDACT: "redact", Action.ALLOW: "below_threshold"}


def nearest_rank(samples: list[float], percentile: float) -> float | None:
    if not samples:
        return None
    ordered = sorted(samples)
    return ordered[max(math.ceil(percentile / 100 * len(ordered)) - 1, 0)]


class MetricsMemory:
    def __init__(self) -> None:
        self._decisions: Counter[str] = Counter()
        self._controls: defaultdict[str, Counter[str]] = defaultdict(Counter)
        self._latency: defaultdict[str, deque[float]] = defaultdict(
            lambda: deque(maxlen=LATENCY_WINDOW)
        )
        self._budgets: dict[str, dict[str, object]] = {}
        self._cost: defaultdict[str, float] = defaultdict(float)
        self._upstream_errors = 0
        self._policy: dict[str, dict[str, object] | None] = {
            "last_reloaded": None,
            "last_rejected": None,
        }
        self._events: deque[dict[str, object]] = deque(maxlen=EVENT_BUFFER)

    async def emit(self, event: AuditEvent) -> None:
        self._events.append(event.to_dict())
        if event.type == "decision" and event.decision is not None:
            self._decisions[event.decision.value] += 1
            for finding in event.findings:
                self._controls[finding.control_id][_ACTION_COUNTER[finding.action]] += 1
            for stage, ms in event.latency_ms.items():
                self._latency[stage].append(ms)
            if event.agent_id is not None:
                if event.budget is not None:
                    self._budgets[event.agent_id] = dataclasses.asdict(event.budget)
                self._cost[event.agent_id] += event.cost or 0.0
        elif event.type == "control_error":
            self._controls[event.control_id or event.blocked_by or "unknown"]["errors"] += 1
        elif event.type == "upstream_error":
            self._upstream_errors += 1
        elif event.type in ("policy_reloaded", "policy_rejected"):
            key = "last_reloaded" if event.type == "policy_reloaded" else "last_rejected"
            self._policy[key] = {
                "ts": event.ts,
                "policy_version": event.policy_version,
                "policy_sha256": event.policy_sha256,
                "detail": event.detail,
            }

    def stats(self) -> dict[str, object]:
        return {
            "requests": {
                "total": sum(self._decisions.values()),
                **{a.value: self._decisions[a.value] for a in Action},
            },
            "controls": {
                control: {k: counts[k] for k in ("block", "redact", "below_threshold", "errors")}
                for control, counts in self._controls.items()
            },
            "latency_ms": {
                stage: {
                    "p50": nearest_rank(list(samples), 50),
                    "p95": nearest_rank(list(samples), 95),
                    "count": len(samples),
                }
                for stage, samples in self._latency.items()
            },
            "budgets": dict(self._budgets),
            "cost": dict(self._cost),
            "upstream_errors": self._upstream_errors,
            "policy": dict(self._policy),
        }

    def events(
        self, limit: int = 100, decision: str | None = None, control: str | None = None
    ) -> list[dict[str, object]]:
        """Newest first. `control` matches blocked_by or any finding's control_id."""
        selected = []
        for event in reversed(self._events):
            if decision is not None and event.get("decision") != decision:
                continue
            if control is not None and not _mentions(event, control):
                continue
            selected.append(event)
            if len(selected) == limit:
                break
        return selected


def _mentions(event: dict[str, object], control: str) -> bool:
    findings = event.get("findings")
    ids = {f["control_id"] for f in findings} if isinstance(findings, (list, tuple)) else set()
    return control == event.get("blocked_by") or control in ids
