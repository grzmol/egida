"""Common types of the harness registry: one `Harness` per coding tool Egida can route.

A harness is a coding tool (Claude Code, Codex, ...). Egida points its model traffic at the proxy in
one of two ways: `mode = "config"` rewrites the tool's own configuration file, `mode = "launch"`
keeps an env file in Egida's directory and `egd launch <id>` starts the tool with it. Harnesses
without a usable custom endpoint have `mode = "unavailable"` and refuse every change.
"""

from __future__ import annotations

import os
import shutil
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Literal

__all__ = [
    "Change",
    "Endpoint",
    "Harness",
    "HarnessEnv",
    "HarnessError",
    "HarnessState",
    "Mode",
    "Protocol",
    "display_path",
]

Protocol = Literal["anthropic", "openai-chat", "openai-responses", "gemini"]
Mode = Literal["config", "launch", "unavailable"]


class HarnessError(Exception):
    """A user-facing sentence, e.g. "~/.codex/config.toml is not valid TOML: ..."."""


@dataclass(frozen=True, slots=True)
class HarnessEnv:
    """Where harness files live. Tests build one with a temporary home and a fake `which`."""

    home: Path
    config_dir: Path  # Egida user dir: ledger, backups, launch env files
    environ: Mapping[
        str, str
    ]  # CLAUDE_CONFIG_DIR, CODEX_HOME, XDG_CONFIG_HOME, PI_CODING_AGENT_DIR, ...
    which: Callable[[str], str | None]  # binary lookup

    @classmethod
    def current(cls) -> HarnessEnv:
        home = Path.home()
        xdg = os.environ.get("XDG_CONFIG_HOME")
        config_root = Path(xdg) if xdg else home / ".config"
        return cls(
            home=home,
            config_dir=config_root / "egida",
            environ=dict(os.environ),
            which=shutil.which,
        )

    def dir_from(self, variable: str, default: Path) -> Path:
        """`$variable` (with `~` expanded against `home`) when set and non-empty, else `default`."""
        value = self.environ.get(variable, "")
        if not value:
            return default
        if value == "~" or value.startswith("~/"):
            return self.home / value[2:]
        return Path(value)

    def xdg_config_home(self) -> Path:
        return self.dir_from("XDG_CONFIG_HOME", self.home / ".config")


@dataclass(frozen=True, slots=True)
class Endpoint:
    base_url: str  # proxy root without /v1, e.g. "http://127.0.0.1:8080"
    key: str  # this harness agent's API key (plain text; only here and in the harness config)
    model: str  # policy model the harness uses

    @property
    def openai_base(self) -> str:
        """Base URL for OpenAI-style clients: the proxy root plus `/v1`."""
        return self.base_url.rstrip("/") + "/v1"


@dataclass(frozen=True, slots=True)
class Change:
    path: Path
    action: Literal["create", "update", "delete"]
    summary: str  # one line for the wizard review


@dataclass(frozen=True, slots=True)
class HarnessState:
    installed: bool
    enabled: bool  # Egida's settings are present (ledger entry and config points at Egida)
    detail: str  # one line, e.g. "found claude on PATH · ~/.claude/settings.json"


def display_path(env: HarnessEnv, path: Path) -> str:
    """`path` with the home directory shown as `~`."""
    try:
        return "~/" + path.relative_to(env.home).as_posix()
    except ValueError:
        return str(path)


class Harness(ABC):
    id: ClassVar[str]  # also the policy agent id
    name: ClassVar[str]
    protocol: ClassVar[Protocol | None]
    mode: ClassVar[Mode]
    note: ClassVar[str]  # one line: what Egida changes, how to start it, or why unavailable
    binaries: ClassVar[tuple[str, ...]] = ()

    def config_paths(self, env: HarnessEnv) -> tuple[Path, ...]:
        """Files Egida reads or writes for this harness (the first one is shown in `state`)."""
        return ()

    def install_paths(self, env: HarnessEnv) -> tuple[Path, ...]:
        """Known install locations checked when no binary is on PATH."""
        return ()

    def config_dirs(self, env: HarnessEnv) -> tuple[Path, ...]:
        """Directories whose existence means the harness has been used on this machine."""
        return tuple(path.parent for path in self.config_paths(env))

    def found_binary(self, env: HarnessEnv) -> str | None:
        for binary in self.binaries:
            found = env.which(binary)
            if found:
                return found
        for path in self.install_paths(env):
            if path.exists():
                return str(path)
        return None

    def installed(self, env: HarnessEnv) -> bool:
        if self.found_binary(env) is not None:
            return True
        return any(path.is_dir() for path in self.config_dirs(env))

    def state(self, env: HarnessEnv) -> HarnessState:
        installed = self.installed(env)
        enabled = self.mode != "unavailable" and self.enabled(env)
        parts: list[str] = []
        binary = self.found_binary(env)
        if binary is not None:
            on_path = any(env.which(name) for name in self.binaries)
            shown = self.binaries[0] if on_path else display_path(env, Path(binary))
            parts.append(f"found {shown} on PATH" if on_path else f"found {shown}")
        elif installed:
            parts.append("config found")
        else:
            parts.append("not found")
        paths = self.config_paths(env)
        if paths:
            parts.append(display_path(env, paths[0]))
        return HarnessState(installed=installed, enabled=enabled, detail=" · ".join(parts))

    @abstractmethod
    def enabled(self, env: HarnessEnv) -> bool:
        """Ledger entry exists and the harness configuration still points at its base URL."""

    @abstractmethod
    def plan(self, env: HarnessEnv, endpoint: Endpoint) -> list[Change]:
        """The changes `apply` would make. Reads files, writes nothing."""

    @abstractmethod
    def apply(self, env: HarnessEnv, endpoint: Endpoint) -> list[Change]:
        """Back up, write atomically, record previous values in the ledger."""

    @abstractmethod
    def remove(self, env: HarnessEnv) -> list[Change]:
        """Delete Egida's entries and restore the values Egida overwrote; keep user edits."""

    def launch(self, env: HarnessEnv, args: Sequence[str]) -> tuple[list[str], dict[str, str]]:
        """argv and extra environment for `egd launch <id>`."""
        raise HarnessError(f"{self.name} is not started through Egida: {self.note}")

    def plan_remove(self, env: HarnessEnv) -> list[Change]:
        """The changes `remove` would make. Reads files, writes nothing."""
        return []
