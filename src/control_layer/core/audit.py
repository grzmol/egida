"""Audit event `audit.v1`. Raw prompt/response content NEVER goes into an event.

`seq`, `prev_hash` and `hash` are added by the JSONL adapter (hash chain), not here.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

from control_layer.core.models import Action, BudgetUsage, Category, Usage

__all__ = ["AUDIT_SCHEMA", "AuditEvent", "AuditEventType", "FindingSummary"]

AUDIT_SCHEMA = "audit.v1"

AuditEventType = Literal[
    "decision",
    "policy_reloaded",
    "policy_rejected",
    "feed_reloaded",
    "feed_rejected",
    "control_error",
    "upstream_error",
]


@dataclass(frozen=True, slots=True)
class FindingSummary:
    control_id: str
    category: Category
    score: float
    action: Action  # action derived by the pipeline (ALLOW when below threshold)
    tags: tuple[str, ...] = ()
    evidence: str = ""  # masked by the detector


@dataclass(frozen=True, slots=True)
class AuditEvent:
    type: AuditEventType
    ts: float
    request_id: str | None = None
    agent_id: str | None = None
    model: str | None = None
    policy_version: int | None = None
    policy_sha256: str | None = None
    feed_version: str | None = None
    decision: Action | None = None
    blocked_by: str | None = None
    findings: tuple[FindingSummary, ...] = ()
    usage: Usage | None = None
    cost: float | None = None
    budget: BudgetUsage | None = None
    latency_ms: Mapping[str, float] = field(default_factory=dict)
    detail: str | None = None

    def to_dict(self) -> dict[str, object]:
        """JSON-serializable dict with `schema` = audit.v1 (enums as their string values)."""
        data = dataclasses.asdict(self)
        data["latency_ms"] = dict(self.latency_ms)
        data["findings"] = [dict(f) for f in data["findings"]]
        for item in data["findings"]:
            item["tags"] = list(item["tags"])
        return {"schema": AUDIT_SCHEMA, **data}
