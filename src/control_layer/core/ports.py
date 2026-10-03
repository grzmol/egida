"""Ports: the only way core talks to the outside world (ADR-0001). Adapters implement them.

Frozen contract v1 — changes need an announcement (docs/WORKPLAN.md) and an ADR.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar, Literal, Protocol, runtime_checkable

from pydantic import BaseModel

from control_layer.core.audit import AuditEvent
from control_layer.core.models import BudgetUsage, Finding, Interaction, Message, Side, Usage
from control_layer.core.policy import BudgetLimits, Policy, UpstreamConfig

if TYPE_CHECKING:  # core.signatures imports this module; the annotation needs no runtime import
    from control_layer.core.signatures import CompiledFeed

__all__ = [
    "AuditSink",
    "BudgetRequest",
    "BudgetStore",
    "BudgetVerdict",
    "Clock",
    "Detector",
    "DetectorDeps",
    "DetectorFactory",
    "FeedSnapshot",
    "GuardModelClient",
    "ModelClient",
    "ModelResult",
    "PolicySnapshot",
    "PolicySource",
    "ScanContext",
    "SignatureFeed",
    "SupportsWarmUp",
]


# --- detectors ----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ScanContext:
    interaction: Interaction
    side: Side
    control_id: str
    params: BaseModel  # instance of the detector's Params, validated at policy load


class Detector(Protocol):
    """A control. Returns findings; never decides the action and never hides its own errors.

    Finding.control_id must equal ctx.control_id. Exceptions propagate to the pipeline,
    which applies the control's on_error. CPU work longer than a few ms goes to a worker thread.
    """

    kind: ClassVar[str]
    Params: ClassVar[type[BaseModel]]

    async def scan(self, ctx: ScanContext) -> list[Finding]: ...


class GuardModelClient(Protocol):
    """Raw text generation for guard LLMs (temperature 0). Errors raise UpstreamError."""

    async def generate(self, model: str, prompt: str, max_tokens: int) -> str: ...

    async def load(self, model: str) -> None: ...


@dataclass(frozen=True, slots=True)
class DetectorDeps:
    """Dependencies injected into detector factories by app.py."""

    guard: GuardModelClient | None = None


DetectorFactory = Callable[[DetectorDeps], Detector]


@runtime_checkable
class SupportsWarmUp(Protocol):
    async def warm_up(self, params: BaseModel) -> None: ...


# --- model upstream -------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ModelResult:
    message: Message
    usage: Usage
    finish_reason: str


class ModelClient(Protocol):
    async def complete(self, interaction: Interaction, upstream: UpstreamConfig) -> ModelResult:
        """Call the model. Raises UpstreamError on transport/HTTP/payload failures."""
        ...


# --- policy ---------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PolicySnapshot:
    policy: Policy
    sha256: str
    loaded_at: float
    source: str


class PolicySource(Protocol):
    def current(self) -> PolicySnapshot: ...

    def last_error(self) -> str | None: ...


# --- signature feed (A5) --------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FeedSnapshot:
    feed: CompiledFeed
    version: str
    sha256: str
    loaded_at: float
    source: str


class SignatureFeed(Protocol):
    """Mirror of PolicySource: the active, already validated feed (last valid on bad edits)."""

    def current(self) -> FeedSnapshot: ...

    def last_error(self) -> str | None: ...


# --- budgets --------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BudgetRequest:
    agent_id: str
    budget_name: str
    limits: BudgetLimits
    est_tokens: int
    est_cost: float
    fingerprint: str  # sha256 of canonical (model, messages) — loop detection
    now: float  # clock.monotonic()


@dataclass(frozen=True, slots=True)
class BudgetVerdict:
    allowed: bool
    reservation_id: str | None  # None when refused
    reason: Literal["ok", "tokens", "cost", "requests", "loop"]
    usage: BudgetUsage


class BudgetStore(Protocol):
    async def reserve(self, req: BudgetRequest) -> BudgetVerdict: ...

    async def settle(self, reservation_id: str, usage: Usage, cost: float) -> None: ...

    async def release(self, reservation_id: str) -> None: ...

    def usage(self, agent_id: str) -> BudgetUsage: ...


# --- audit and time -------------------------------------------------------------


class AuditSink(Protocol):
    async def emit(self, event: AuditEvent) -> None: ...


class Clock(Protocol):
    def now(self) -> float:
        """Wall-clock epoch seconds (audit timestamps)."""
        ...

    def monotonic(self) -> float:
        """Monotonic seconds (latencies, budget windows)."""
        ...
