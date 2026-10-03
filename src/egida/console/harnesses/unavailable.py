"""Harnesses without a custom model endpoint Egida can use. They are listed so the wizard can say
why, and every change is refused."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from egida.console.harnesses.base import (
    Change,
    Endpoint,
    Harness,
    HarnessEnv,
    HarnessError,
    Mode,
    Protocol,
)

__all__ = ["AntigravityIde", "Cursor", "UnavailableHarness"]


class UnavailableHarness(Harness):
    protocol: ClassVar[Protocol | None] = None
    mode: ClassVar[Mode] = "unavailable"
    apps: ClassVar[tuple[str, ...]] = ()  # macOS app bundle names

    def install_paths(self, env: HarnessEnv) -> tuple[Path, ...]:
        roots = (Path("/Applications"), env.home / "Applications")
        return tuple(root / app for root in roots for app in self.apps)

    def enabled(self, env: HarnessEnv) -> bool:
        return False

    def plan(self, env: HarnessEnv, endpoint: Endpoint) -> list[Change]:
        raise HarnessError(f"{self.name} cannot use Egida: {self.note}")

    def apply(self, env: HarnessEnv, endpoint: Endpoint) -> list[Change]:
        raise HarnessError(f"{self.name} cannot use Egida: {self.note}")

    def remove(self, env: HarnessEnv) -> list[Change]:
        return []


class AntigravityIde(UnavailableHarness):
    id: ClassVar[str] = "antigravity"
    name: ClassVar[str] = "Antigravity IDE"
    note: ClassVar[str] = (
        "Antigravity IDE has no custom model endpoint; use the Antigravity CLI (agy) entry."
    )
    binaries: ClassVar[tuple[str, ...]] = ("antigravity",)
    apps: ClassVar[tuple[str, ...]] = ("Antigravity.app",)


class Cursor(UnavailableHarness):
    id: ClassVar[str] = "cursor"
    name: ClassVar[str] = "Cursor"
    note: ClassVar[str] = (
        "Cursor sends every request through Cursor's servers; a local endpoint is not reachable."
    )
    binaries: ClassVar[tuple[str, ...]] = ("cursor",)
    apps: ClassVar[tuple[str, ...]] = ("Cursor.app",)
