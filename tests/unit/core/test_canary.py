"""C22 canary format and injection (core/canary.py)."""

from __future__ import annotations

import pytest

from control_layer.core.canary import CANARY_RE, inject_canary, new_canary
from control_layer.core.models import Interaction, Message

TOKEN = "cl-canary-0123456789abcdef"  # noqa: S105 (canary token, not a credential)


def _chat(*messages: Message) -> Interaction:
    return Interaction(request_id="r", agent_id="a", model="m", messages=messages)


def test_new_canary_matches_the_detector_regex_and_is_random() -> None:
    tokens = {new_canary() for _ in range(50)}
    assert len(tokens) == 50
    assert all(CANARY_RE.fullmatch(t) for t in tokens)


def test_inject_prefixes_the_first_system_message_only() -> None:
    original = _chat(
        Message(role="system", content="You are a bank assistant."),
        Message(role="user", content="hi"),
        Message(role="system", content="second"),
    )
    marked = inject_canary(original, TOKEN)
    assert marked.messages[0].content == f"<!-- {TOKEN} -->\nYou are a bank assistant."
    assert marked.messages[1:] == original.messages[1:]
    assert original.messages[0].content == "You are a bank assistant."  # input not mutated


def test_inject_without_system_message_changes_nothing() -> None:
    original = _chat(Message(role="user", content="hi"))
    assert inject_canary(original, TOKEN) == original


@pytest.mark.parametrize("token", ["cl-canary-XYZ", "cl-canary-0123456789ABCDEF", f"{TOKEN} -->"])
def test_inject_rejects_malformed_tokens(token: str) -> None:
    with pytest.raises(ValueError, match="canary"):
        inject_canary(_chat(Message(role="system", content="s")), token)
