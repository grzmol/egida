"""In-memory ToolPinStore (C09): trust on first use per (agent, tool name). Single process;
pins are lost on restart (a persistent store goes behind the same port)."""

from __future__ import annotations

from collections.abc import Mapping

__all__ = ["InMemoryToolPinStore"]


class InMemoryToolPinStore:
    def __init__(self) -> None:
        self._pins: dict[str, dict[str, str]] = {}

    async def pin(self, agent_id: str, digests: Mapping[str, str]) -> dict[str, str]:
        # No await in this method: under asyncio it runs atomically, so two requests cannot both
        # pin a new name. Do not add a lock or I/O here; a shared store needs its own atomicity.
        pinned = self._pins.setdefault(agent_id, {})
        mismatches = {
            name: pinned[name]
            for name, digest in digests.items()
            if name in pinned and pinned[name] != digest
        }
        if not mismatches:  # all or nothing: a rejected request pins nothing new
            for name, digest in digests.items():
                pinned.setdefault(name, digest)
        return mismatches
