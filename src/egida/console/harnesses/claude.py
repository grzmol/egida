"""Claude Code: the `env` block of its user settings points the Anthropic client at the proxy.

Claude Code speaks only the Anthropic Messages API (served by `adapters/anthropic_api.py`). Values
in the settings `env` block win over the shell, so `claude` uses the proxy without extra flags.
`ANTHROPIC_AUTH_TOKEN` is sent as `Authorization: Bearer <key>`.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, ClassVar, Final

from egida.console.harnesses.base import Endpoint, HarnessEnv, Mode, Protocol
from egida.console.harnesses.files import (
    JSON,
    EditingHarness,
    Planned,
    get_path,
    load_json,
    merge_edit,
    restore_edit,
)

__all__ = ["ClaudeCode"]

_MODEL_VARS: Final = (
    "ANTHROPIC_MODEL",
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    "CLAUDE_CODE_SUBAGENT_MODEL",
)


class ClaudeCode(EditingHarness):
    id: ClassVar[str] = "claude-code"
    name: ClassVar[str] = "Claude Code"
    protocol: ClassVar[Protocol | None] = "anthropic"
    mode: ClassVar[Mode] = "config"
    note: ClassVar[str] = (
        "sets the proxy URL, key and model in the env block of settings.json; start with: claude"
    )
    binaries: ClassVar[tuple[str, ...]] = ("claude",)

    def settings_path(self, env: HarnessEnv) -> Path:
        return env.dir_from("CLAUDE_CONFIG_DIR", env.home / ".claude") / "settings.json"

    def config_paths(self, env: HarnessEnv) -> tuple[Path, ...]:
        return (self.settings_path(env),)

    def install_paths(self, env: HarnessEnv) -> tuple[Path, ...]:
        return (env.home / ".claude" / "local" / "claude", env.home / ".local" / "bin" / "claude")

    def edits(
        self, env: HarnessEnv, endpoint: Endpoint, earlier: Mapping[str, Any]
    ) -> list[Planned]:
        path = self.settings_path(env)
        values: dict[str, str] = {
            "ANTHROPIC_BASE_URL": endpoint.base_url,
            "ANTHROPIC_AUTH_TOKEN": endpoint.key,
            **dict.fromkeys(_MODEL_VARS, endpoint.model),
            "CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS": "1",
            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        }
        edit = merge_edit(
            path,
            JSON,
            {("env", key): value for key, value in values.items()},
            earlier.get(str(path)),
        )
        summary = f"env: ANTHROPIC_BASE_URL={endpoint.base_url}, Egida key, model {endpoint.model}"
        return [(edit, summary)]

    def undo(self, env: HarnessEnv, files: Mapping[str, Any]) -> list[Planned]:
        path = self.settings_path(env)
        record = files.get(str(path))
        if record is None:
            return []
        edit = restore_edit(path, JSON, record)
        return [] if edit is None else [(edit, "env: restore the values Egida replaced")]

    def points_at(self, env: HarnessEnv, record: Mapping[str, Any]) -> bool:
        current = get_path(load_json(self.settings_path(env)), ("env", "ANTHROPIC_BASE_URL"))
        return isinstance(current, str) and current == record.get("base_url")
