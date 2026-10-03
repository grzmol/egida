"""In-memory BudgetStore: sliding-window token/cost/request budgets per agent (C15) and loop
detection by request fingerprint (C16). Single process; state is lost on restart."""

from __future__ import annotations

import itertools
from collections import deque
from dataclasses import dataclass
from typing import Literal

from egida.core.models import BudgetUsage, Usage
from egida.core.policy import BudgetLimits
from egida.core.ports import BudgetRequest, BudgetVerdict

__all__ = ["InMemoryBudgetStore"]


@dataclass(slots=True)
class _Entry:
    agent_id: str
    t: float
    tokens: int
    cost: float


class InMemoryBudgetStore:
    # ponytail: process memory, one instance; Redis behind the same port for multi-instance
    def __init__(self) -> None:
        self._ids = itertools.count(1)
        self._entries: dict[str, _Entry] = {}  # reservation id -> entry (in flight or settled)
        self._prints: dict[tuple[str, str], deque[float]] = {}  # (agent, fingerprint) -> times
        self._limits: dict[str, BudgetLimits] = {}  # last limits seen per agent, for usage()

    async def reserve(self, req: BudgetRequest) -> BudgetVerdict:
        # No await from here to the return: check-and-write is atomic on the event loop.
        # ponytail: add an asyncio.Lock if this method ever awaits before writing.
        limits = req.limits
        self._limits[req.agent_id] = limits
        self._expire(req.agent_id, req.now - limits.window_s)
        prints = self._prints.setdefault((req.agent_id, req.fingerprint), deque())
        while prints and prints[0] < req.now - limits.identical_window_s:
            prints.popleft()
        used = self.usage(req.agent_id)
        reason: Literal["tokens", "cost", "requests", "loop"]
        if len(prints) >= limits.max_identical:
            reason = "loop"
        elif used.requests + 1 > limits.max_requests:
            reason = "requests"
        elif used.tokens + req.est_tokens > limits.max_tokens:
            reason = "tokens"
        elif used.cost + req.est_cost > limits.max_cost:
            reason = "cost"
        else:
            reservation_id = f"res_{next(self._ids)}"
            self._entries[reservation_id] = _Entry(
                req.agent_id, req.now, req.est_tokens, req.est_cost
            )
            prints.append(req.now)
            return BudgetVerdict(True, reservation_id, "ok", self.usage(req.agent_id))
        return BudgetVerdict(False, None, reason, used)

    async def settle(self, reservation_id: str, usage: Usage, cost: float) -> None:
        entry = self._entries.get(reservation_id)
        tokens = usage.prompt_tokens + usage.completion_tokens
        if entry is not None and tokens > 0:  # no usage reported: keep the (higher) estimate
            entry.tokens, entry.cost = tokens, cost

    async def release(self, reservation_id: str) -> None:
        # the fingerprint stays: a blocked loop is still a loop
        self._entries.pop(reservation_id, None)

    def usage(self, agent_id: str) -> BudgetUsage:
        limits = self._limits.get(agent_id)
        mine = [e for e in self._entries.values() if e.agent_id == agent_id]
        return BudgetUsage(
            agent_id=agent_id,
            window_s=limits.window_s if limits else 0,
            tokens=sum(e.tokens for e in mine),
            cost=sum(e.cost for e in mine),
            requests=len(mine),
            max_tokens=limits.max_tokens if limits else 0,
            max_cost=limits.max_cost if limits else 0.0,
            max_requests=limits.max_requests if limits else 0,
        )

    def _expire(self, agent_id: str, cutoff: float) -> None:
        stale = [k for k, e in self._entries.items() if e.agent_id == agent_id and e.t < cutoff]
        for key in stale:
            del self._entries[key]
