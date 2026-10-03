"""In-memory budgets (A3): C15 limits, C16 loops, sliding window, settle/release, races."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from control_layer.adapters.budget_memory import InMemoryBudgetStore
from control_layer.core.models import Usage
from control_layer.core.policy import BudgetLimits
from control_layer.core.ports import BudgetRequest

pytestmark = pytest.mark.anyio

LIMITS = BudgetLimits(
    max_tokens=1000,
    max_cost=1.0,
    max_requests=10,
    window_s=60,
    max_identical=3,
    identical_window_s=10,
)


def _req(now: float = 0.0, fp: str = "a", **kw: Any) -> BudgetRequest:
    values: dict[str, Any] = {
        "agent_id": "agent",
        "budget_name": "default",
        "limits": LIMITS,
        "est_tokens": 10,
        "est_cost": 0.01,
        "fingerprint": fp,
        "now": now,
    }
    values.update(kw)
    return BudgetRequest(**values)


async def test_requests_limit_and_window_reset() -> None:
    store = InMemoryBudgetStore()
    for i in range(10):
        assert (await store.reserve(_req(fp=str(i)))).allowed
    refused = await store.reserve(_req(fp="x"))
    assert (refused.allowed, refused.reason) == (False, "requests")
    assert refused.usage.requests == 10
    assert (await store.reserve(_req(now=61, fp="x"))).allowed  # window slid past


@pytest.mark.parametrize(
    ("kw", "reason"), [({"est_tokens": 1001}, "tokens"), ({"est_cost": 1.5}, "cost")]
)
async def test_token_and_cost_limits(kw: dict[str, Any], reason: str) -> None:
    verdict = await InMemoryBudgetStore().reserve(_req(**kw))
    assert (verdict.allowed, verdict.reason) == (False, reason)


async def test_identical_requests_are_a_loop_until_window_passes() -> None:
    store = InMemoryBudgetStore()
    for t in range(3):
        assert (await store.reserve(_req(now=t))).allowed
    loop = await store.reserve(_req(now=3))
    assert loop.reason == "loop"
    assert (await store.reserve(_req(now=3, fp="other"))).allowed
    assert (await store.reserve(_req(now=11))).allowed  # first two prints expired


async def test_settle_replaces_estimate_and_release_keeps_fingerprint() -> None:
    store = InMemoryBudgetStore()
    first = await store.reserve(_req(est_tokens=500))
    assert first.reservation_id
    await store.settle(first.reservation_id, Usage(20, 5), 0.002)
    assert store.usage("agent").tokens == 25

    second = await store.reserve(_req(est_tokens=500))
    assert second.reservation_id
    await store.settle(second.reservation_id, Usage(0, 0), 0.0)  # upstream sent no usage
    assert store.usage("agent").tokens == 525

    third = await store.reserve(_req())
    assert third.reservation_id
    await store.release(third.reservation_id)
    assert store.usage("agent").requests == 2
    assert (await store.reserve(_req())).reason == "loop"  # 3 identical prints remain


async def test_concurrent_reservations_never_exceed_limit() -> None:
    store = InMemoryBudgetStore()
    verdicts = await asyncio.gather(*(store.reserve(_req(fp=str(i))) for i in range(20)))
    assert sum(v.allowed for v in verdicts) == 10


async def test_new_limits_apply_without_restart() -> None:
    store = InMemoryBudgetStore()
    for i in range(3):
        await store.reserve(_req(fp=str(i)))
    tighter = LIMITS.model_copy(update={"max_requests": 3})
    assert (await store.reserve(_req(fp="x", limits=tighter))).reason == "requests"
    assert store.usage("agent").max_requests == 3


async def test_agents_are_isolated() -> None:
    store = InMemoryBudgetStore()
    for i in range(10):
        await store.reserve(_req(fp=str(i)))
    assert (await store.reserve(_req(agent_id="other"))).allowed
