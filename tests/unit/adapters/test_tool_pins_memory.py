"""InMemoryToolPinStore (C09): trust on first use, all or nothing, per agent, atomic."""

from __future__ import annotations

import asyncio

import pytest

from control_layer.adapters.tool_pins_memory import InMemoryToolPinStore

pytestmark = pytest.mark.anyio


async def test_first_use_pins_and_a_changed_digest_is_reported() -> None:
    store = InMemoryToolPinStore()
    assert await store.pin("agent", {"add": "d1"}) == {}
    assert await store.pin("agent", {"add": "d1"}) == {}
    assert await store.pin("agent", {"add": "d2"}) == {"add": "d1"}


async def test_rejected_request_pins_nothing_new() -> None:
    store = InMemoryToolPinStore()
    await store.pin("agent", {"a": "a1"})
    assert await store.pin("agent", {"a": "a2", "b": "b1"}) == {"a": "a1"}
    assert await store.pin("agent", {"b": "b2"}) == {}  # b was not pinned by the rejected request


async def test_agents_are_isolated() -> None:
    store = InMemoryToolPinStore()
    assert await store.pin("one", {"add": "d1"}) == {}
    assert await store.pin("two", {"add": "d2"}) == {}


async def test_concurrent_first_use_pins_exactly_one_definition() -> None:
    store = InMemoryToolPinStore()
    results = await asyncio.gather(
        store.pin("agent", {"add": "d1"}), store.pin("agent", {"add": "d2"})
    )
    assert sorted(len(r) for r in results) == [0, 1]
