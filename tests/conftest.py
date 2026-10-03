"""Shared fixtures. Owner: Grzegorz (Dev A). `--target` is used by Sebastian's case runner."""

# Async tests use the anyio pytest plugin (ships with anyio): mark with @pytest.mark.anyio.

from __future__ import annotations

import copy
from typing import Any

import pytest

DEMO_KEY = "sk-demo-agent"
DEMO_KEY_SHA256 = "337d3b58b003feda566bd8b4a36d7cdb732ec597f01fe52542cbfd873b1c7ba0"

_POLICY: dict[str, Any] = {
    "version": 1,
    "defaults": {"on_error": "block", "timeout_ms": 1500},
    "limits": {"max_input_chars": 100_000, "max_messages": 100, "max_tokens": 1024},
    "upstreams": {"ollama": {"base_url": "http://127.0.0.1:11434/v1", "timeout_s": 60}},
    "models": {
        "llama3.2:3b": {"upstream": "ollama", "price_in_per_1k": 0.0002, "price_out_per_1k": 0.0006}
    },
    "agents": {
        "demo-agent": {
            "key_sha256": DEMO_KEY_SHA256,
            "allowed_models": ["llama3.2:3b"],
            "allowed_tools": [],
            "budget": "default",
        }
    },
    "budgets": {
        "default": {
            "max_tokens": 50_000,
            "max_cost": 1.0,
            "max_requests": 300,
            "window_s": 3600,
            "max_identical": 5,
            "identical_window_s": 10,
        }
    },
    "controls": [],
}


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--target",
        action="store",
        default=None,
        help="Base URL of a running control layer instance (live selftest), e.g. http://127.0.0.1:8080",
    )


@pytest.fixture
def target(request: pytest.FixtureRequest) -> str | None:
    value = request.config.getoption("--target")
    return str(value) if value else None


@pytest.fixture
def policy_dict() -> dict[str, Any]:
    """A valid policy v1 as a plain dict (fresh deep copy per test)."""
    return copy.deepcopy(_POLICY)


class FixedClock:
    """Deterministic Clock for tests; advance() moves both wall and monotonic time."""

    def __init__(self, start: float = 1_759_489_200.0) -> None:
        self._wall = start
        self._mono = 0.0

    def now(self) -> float:
        return self._wall

    def monotonic(self) -> float:
        return self._mono

    def advance(self, seconds: float) -> None:
        self._wall += seconds
        self._mono += seconds


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock()


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
