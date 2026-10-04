"""Harness registry: coding tools whose model traffic Egida routes through the proxy.

`REGISTRY` lists every harness in the order the setup wizard shows them. A harness id is also the
id of its policy agent.
"""

from __future__ import annotations

from egida.console.harnesses.aider import Aider
from egida.console.harnesses.base import (
    Change,
    Endpoint,
    Harness,
    HarnessEnv,
    HarnessError,
    HarnessState,
    Mode,
    Protocol,
)
from egida.console.harnesses.claude import ClaudeCode
from egida.console.harnesses.codex import Codex
from egida.console.harnesses.continue_dev import ContinueDev
from egida.console.harnesses.copilot import CopilotCli
from egida.console.harnesses.droid import Droid
from egida.console.harnesses.gemini import AntigravityCli, GeminiCli
from egida.console.harnesses.omp import OhMyPi
from egida.console.harnesses.opencode import Opencode
from egida.console.harnesses.pi import Pi
from egida.console.harnesses.unavailable import AntigravityIde, Cursor

__all__ = [
    "REGISTRY",
    "Change",
    "Endpoint",
    "Harness",
    "HarnessEnv",
    "HarnessError",
    "HarnessState",
    "Mode",
    "Protocol",
    "by_id",
]

REGISTRY: tuple[Harness, ...] = (
    ClaudeCode(),
    Codex(),
    AntigravityCli(),
    AntigravityIde(),
    GeminiCli(),
    Opencode(),
    Aider(),
    Droid(),
    Pi(),
    OhMyPi(),
    ContinueDev(),
    CopilotCli(),
    Cursor(),
)

_BY_ID: dict[str, Harness] = {harness.id: harness for harness in REGISTRY}


def by_id(harness_id: str) -> Harness:
    """The registered harness with this id; KeyError naming the known ids otherwise."""
    try:
        return _BY_ID[harness_id]
    except KeyError:
        known = ", ".join(_BY_ID)
        raise KeyError(f"Unknown harness {harness_id!r}; known harnesses: {known}.") from None
