"""Domain model of the control layer.

Frozen contract v1 — changes need an announcement (docs/WORKPLAN.md).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

__all__ = [
    "Action",
    "BudgetUsage",
    "Category",
    "ControlError",
    "Decision",
    "Finding",
    "Interaction",
    "Message",
    "Role",
    "Side",
    "Span",
    "ToolCall",
    "ToolDef",
    "Usage",
]


class Action(StrEnum):
    """Decision for an interaction. Declaration order = severity (ALLOW < REDACT < BLOCK)."""

    ALLOW = "allow"
    REDACT = "redact"
    BLOCK = "block"


class Side(StrEnum):
    INPUT = "input"
    OUTPUT = "output"


class Category(StrEnum):
    ACCESS = "access"
    LIMIT = "limit"
    BUDGET = "budget"
    PII = "pii"
    SECRET = "secret"  # noqa: S105 — category name, not a credential
    INJECTION = "injection"
    HARMFUL = "harmful"
    SIGNATURE = "signature"
    TOOL = "tool"
    EXFILTRATION = "exfiltration"


Role = Literal["system", "user", "assistant", "tool"]


@dataclass(frozen=True, slots=True)
class ToolCall:
    id: str
    name: str
    arguments: str  # raw JSON as text


@dataclass(frozen=True, slots=True)
class ToolDef:
    name: str
    description: str
    parameters_json: str


@dataclass(frozen=True, slots=True)
class Message:
    role: Role
    content: str
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()


@dataclass(frozen=True, slots=True)
class Usage:
    prompt_tokens: int
    completion_tokens: int


@dataclass(frozen=True, slots=True)
class Interaction:
    request_id: str
    agent_id: str
    model: str
    messages: tuple[Message, ...]
    tools: tuple[ToolDef, ...] = ()
    max_tokens: int | None = None
    stream: bool = False
    output: Message | None = None  # set by the pipeline after the model call


@dataclass(frozen=True, slots=True)
class Span:
    """Character range [start, end) in the ORIGINAL text addressed by `target` (see core.texts)."""

    target: str
    start: int
    end: int
    label: str


@dataclass(frozen=True, slots=True)
class Finding:
    control_id: str
    category: Category
    score: float  # in [0, 1]
    spans: tuple[Span, ...] = ()
    evidence: str = ""  # already masked, max 200 chars
    tags: tuple[str, ...] = ()  # e.g. "owasp.llm01-2025", "asi.asi01", "atlas.AML.T0051"


@dataclass(frozen=True, slots=True)
class ControlError:
    control_id: str
    kind: Literal["timeout", "exception"]
    message: str


@dataclass(frozen=True, slots=True)
class Decision:
    action: Action
    findings: tuple[Finding, ...]
    blocked_by: str | None = None
    errors: tuple[ControlError, ...] = ()


@dataclass(frozen=True, slots=True)
class BudgetUsage:
    """Usage of one agent's budget in the current sliding window (incl. in-flight reservations)."""

    agent_id: str
    window_s: int
    tokens: int
    cost: float
    requests: int
    max_tokens: int
    max_cost: float
    max_requests: int
