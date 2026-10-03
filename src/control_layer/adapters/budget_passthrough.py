"""BudgetStore that admits everything (A1 skeleton). Replaced by InMemoryBudgetStore in A3."""

from __future__ import annotations

import itertools

from control_layer.core.models import BudgetUsage, Usage
from control_layer.core.ports import BudgetRequest, BudgetVerdict

__all__ = ["PassthroughBudgetStore"]


class PassthroughBudgetStore:
    def __init__(self) -> None:
        self._ids = itertools.count(1)

    async def reserve(self, req: BudgetRequest) -> BudgetVerdict:
        return BudgetVerdict(
            allowed=True,
            reservation_id=f"res_{next(self._ids)}",
            reason="ok",
            usage=self._empty(req.agent_id, req),
        )

    async def settle(self, reservation_id: str, usage: Usage, cost: float) -> None:
        return None

    async def release(self, reservation_id: str) -> None:
        return None

    def usage(self, agent_id: str) -> BudgetUsage:
        return BudgetUsage(agent_id, 0, 0, 0.0, 0, 0, 0.0, 0)

    @staticmethod
    def _empty(agent_id: str, req: BudgetRequest) -> BudgetUsage:
        limits = req.limits
        return BudgetUsage(
            agent_id=agent_id,
            window_s=limits.window_s,
            tokens=0,
            cost=0.0,
            requests=0,
            max_tokens=limits.max_tokens,
            max_cost=limits.max_cost,
            max_requests=limits.max_requests,
        )
