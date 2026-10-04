"""Budget arithmetic (A3)."""

from __future__ import annotations

import dataclasses

from egida.core.budget import cost, estimate_tokens, fingerprint
from egida.core.models import Interaction, Message, ToolCall, ToolDef
from egida.core.policy import ModelSpec


def _interaction(text: str) -> Interaction:
    return Interaction("r", "a", "m", (Message(role="user", content=text),))


def test_estimate_reserves_prompt_plus_full_completion() -> None:
    assert estimate_tokens(_interaction(""), 100) == 100
    assert estimate_tokens(_interaction("zażółć gęślą"), 0) == 3  # ceil(12 chars / 4)


def test_cost_uses_per_1k_prices_and_zero_price_is_free() -> None:
    spec = ModelSpec(upstream="u", price_in_per_1k=0.002, price_out_per_1k=0.004)
    assert cost(spec, 1000, 500) == 0.002 + 0.002
    assert cost(ModelSpec(upstream="u"), 1000, 1000) == 0.0


def test_fingerprint_identifies_identical_requests_only() -> None:
    a = _interaction("check inbox")
    assert fingerprint(a) == fingerprint(dataclasses.replace(a, request_id="other"))
    assert fingerprint(a) != fingerprint(_interaction("check inbox again"))


def test_fingerprint_tells_apart_requests_differing_only_in_tool_calls_or_tools() -> None:
    """An agent running different tool calls under the same chat text is not looping."""

    def agent_turn(arguments: str, tools: tuple[ToolDef, ...] = ()) -> Interaction:
        call = ToolCall("c1", "run", arguments)
        messages = (
            Message("user", "Use the tool."),
            Message("assistant", "", tool_calls=(call,)),
            Message("tool", "ok", tool_call_id="c1"),
        )
        return Interaction("r", "a", "m", messages, tools=tools)

    first = agent_turn('{"cmd": "ls docs/"}')
    assert fingerprint(first) == fingerprint(agent_turn('{"cmd": "ls docs/"}'))
    assert fingerprint(first) != fingerprint(agent_turn('{"cmd": "cat README.md"}'))
    other_tool = (ToolDef("run", "Runs a command.", "{}"),)
    assert fingerprint(first) != fingerprint(agent_turn('{"cmd": "ls docs/"}', other_tool))
