"""Pure budget arithmetic (C15/C16). State lives in a BudgetStore adapter."""

from __future__ import annotations

import hashlib
import json
import math

from control_layer.core.models import Interaction, Side, Usage
from control_layer.core.policy import ModelSpec
from control_layer.core.texts import iter_texts

__all__ = ["cost", "estimate_tokens", "fingerprint", "input_chars", "usage_cost"]


def input_chars(interaction: Interaction) -> int:
    return sum(len(text) for _, text in iter_texts(interaction, Side.INPUT))


def estimate_tokens(interaction: Interaction, max_tokens: int) -> int:
    """Worst case reserved up front: ~4 chars per prompt token plus the full completion budget."""
    return math.ceil(input_chars(interaction) / 4) + max_tokens


def cost(model: ModelSpec, prompt_tokens: int, completion_tokens: int) -> float:
    return (
        prompt_tokens / 1000 * model.price_in_per_1k
        + completion_tokens / 1000 * model.price_out_per_1k
    )


def usage_cost(model: ModelSpec, usage: Usage) -> float:
    return cost(model, usage.prompt_tokens, usage.completion_tokens)


def fingerprint(interaction: Interaction) -> str:
    """Request identity for loop detection: model, tool definitions and every message with its
    tool calls. Tool calls count: the same chat text with different tool arguments is progress,
    not a loop."""
    canonical = json.dumps(
        {
            "model": interaction.model,
            "messages": [
                [m.role, m.content, m.tool_call_id, [[c.name, c.arguments] for c in m.tool_calls]]
                for m in interaction.messages
            ],
            "tools": [[t.name, t.description, t.parameters_json] for t in interaction.tools],
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
