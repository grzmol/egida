"""Policy edits for coding harnesses: one agent per harness, a shared budget and limits large
enough for coding sessions. Pure functions on a PolicyDocument; nothing touches the disk."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from typing import Any, Final

from egida.console.document import DocumentError, PolicyDocument
from egida.console.harnesses import REGISTRY
from egida.console.harnesses.base import Harness

__all__ = ["BUDGET", "BUDGET_LIMITS", "MIN_LIMITS", "apply_policy", "plan_policy"]

BUDGET: Final = "harness"
BUDGET_LIMITS: Final[Mapping[str, int | float]] = {
    "max_tokens": 5_000_000,
    "max_cost": 100.0,
    "max_requests": 5000,
    "window_s": 3600,
    "max_identical": 20,
    "identical_window_s": 10,
}
MIN_LIMITS: Final[Mapping[str, int]] = {
    "max_input_chars": 2_000_000,
    "max_messages": 2000,
    "max_tokens": 32000,
}
_LIMIT_DEFAULTS: Final[Mapping[str, int]] = {
    "max_input_chars": 100_000,
    "max_messages": 100,
    "max_tokens": 1024,
}


def _sha256(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _comment(harness: Harness) -> str:
    return f"harness: {harness.name}, managed by egd"


def _agent(harness: Harness, model: str, keys: Mapping[str, str]) -> dict[str, Any]:
    try:
        key = keys[harness.id]
    except KeyError:
        raise DocumentError(f"No API key was generated for {harness.name}.") from None
    return {
        "key_sha256": _sha256(key),
        "allowed_models": [model],
        "allowed_tools": ["*"],
        "budget": BUDGET,
    }


def _first_upstream(doc: PolicyDocument) -> str:
    upstreams = doc.names("upstreams")
    if not upstreams:
        raise DocumentError("The policy has no upstream; add one under Upstreams first.")
    return upstreams[0]


def _limit(doc: PolicyDocument, name: str) -> int:
    value = doc.get(("limits", name), _LIMIT_DEFAULTS[name])
    return value if isinstance(value, int) else _LIMIT_DEFAULTS[name]


def _unselected(
    doc: PolicyDocument, selected: Sequence[Harness], registry: Sequence[Harness] | None
) -> list[Harness]:
    if registry is None:
        registry = REGISTRY
    chosen = {harness.id for harness in selected}
    agents = set(doc.names("agents"))
    return [h for h in registry if h.id not in chosen and h.id in agents]


def plan_policy(
    doc: PolicyDocument,
    selected: Sequence[Harness],
    model: str,
    keys: Mapping[str, str],
    *,
    registry: Sequence[Harness] | None = None,
) -> list[str]:
    """What `apply_policy` would change, one readable line per change."""
    lines: list[str] = []
    if model not in doc.names("models"):
        lines.append(f"add model {model} (upstream {_first_upstream(doc)}, price 0)")
    if BUDGET not in doc.names("budgets"):
        lines.append(
            f"add budget {BUDGET} ({BUDGET_LIMITS['max_requests']} requests and "
            f"{BUDGET_LIMITS['max_tokens']} tokens per hour)"
        )
    for name, wanted in MIN_LIMITS.items():
        current = _limit(doc, name)
        if current < wanted:
            lines.append(f"raise limits.{name} from {current} to {wanted}")
    agents = set(doc.names("agents"))
    for harness in selected:
        _agent(harness, model, keys)
        verb = "update agent" if harness.id in agents else "add agent"
        lines.append(f"{verb} {harness.id} with a new key, model {model}, any tool")
    lines += [f"remove agent {h.id}" for h in _unselected(doc, selected, registry)]
    return lines


def apply_policy(
    doc: PolicyDocument,
    selected: Sequence[Harness],
    model: str,
    keys: Mapping[str, str],
    *,
    registry: Sequence[Harness] | None = None,
) -> None:
    """Add the model, the shared budget, raise the limits, write one agent per selected harness
    and delete the agents of registry harnesses that are not selected. DocumentError when the
    policy has no upstream for a new model or a key is missing."""
    agents = {harness.id: _agent(harness, model, keys) for harness in selected}
    if model not in doc.names("models"):
        doc.add_entry(
            "models",
            model,
            {"upstream": _first_upstream(doc), "price_in_per_1k": 0.0, "price_out_per_1k": 0.0},
        )
    if BUDGET not in doc.names("budgets"):
        doc.add_entry("budgets", BUDGET, dict(BUDGET_LIMITS))
    for name, wanted in MIN_LIMITS.items():
        if _limit(doc, name) < wanted:
            doc.set(("limits", name), wanted)
    existing = set(doc.names("agents"))
    for harness in selected:
        spec = agents[harness.id]
        if harness.id in existing:
            for field, value in spec.items():
                doc.set(("agents", harness.id, field), value)
        else:
            doc.add_entry("agents", harness.id, spec)
        doc.set_comment(("agents", harness.id), _comment(harness))
    for harness in _unselected(doc, selected, registry):
        doc.delete_entry("agents", harness.id)
