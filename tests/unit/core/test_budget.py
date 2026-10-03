"""Budget arithmetic (A3)."""

from __future__ import annotations

import dataclasses

from control_layer.core.budget import cost, estimate_tokens, fingerprint
from control_layer.core.models import Interaction, Message
from control_layer.core.policy import ModelSpec


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
