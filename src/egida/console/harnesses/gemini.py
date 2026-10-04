"""Gemini CLI and Antigravity CLI: Google GenAI clients pointed at the proxy's Gemini entry point.

Both send `x-goog-api-key` to `GOOGLE_GEMINI_BASE_URL` (served by `adapters/gemini_api.py`).
Gemini CLI reads `~/.gemini/.env`, so Egida writes the three variables there and selects the API
key auth type in `~/.gemini/settings.json`. Gemini CLI loads that `.env` only in trusted folders;
`egd launch gemini-cli` passes the same variables in the environment for the other cases.
Antigravity CLI (`agy`) loads no `.env` file: Egida sets `modelProvider: "gemini"` in its settings
and keeps the variables in a launch env file; `egd launch antigravity-cli` starts `agy` with them.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, ClassVar, Final

from egida.console.harnesses.base import Endpoint, HarnessEnv, HarnessError, Mode, Protocol
from egida.console.harnesses.files import (
    DOTENV,
    JSON,
    EditingHarness,
    Planned,
    delete_edit,
    get_path,
    launch_command,
    launch_env_edit,
    launch_env_path,
    load_json,
    merge_edit,
    read_dotenv,
    restore_edit,
)

__all__ = ["AntigravityCli", "GeminiCli"]


GEMINI_VARS: Final[tuple[str, ...]] = ("GOOGLE_GEMINI_BASE_URL", "GEMINI_API_KEY", "GEMINI_MODEL")
AUTH_TYPE_PATH: Final[tuple[str, ...]] = ("security", "auth", "selectedType")


def gemini_values(endpoint: Endpoint) -> dict[str, str]:
    return dict(zip(GEMINI_VARS, (endpoint.base_url, endpoint.key, endpoint.model), strict=True))


class GeminiCli(EditingHarness):
    id: ClassVar[str] = "gemini-cli"
    name: ClassVar[str] = "Gemini CLI"
    protocol: ClassVar[Protocol | None] = "gemini"
    mode: ClassVar[Mode] = "config"
    note: ClassVar[str] = (
        "~/.gemini/.env and settings.json; Gemini CLI loads .env only in trusted folders,"
        " otherwise start it with `egd launch gemini-cli`"
    )
    binaries: ClassVar[tuple[str, ...]] = ("gemini",)

    def env_path(self, env: HarnessEnv) -> Path:
        return env.home / ".gemini" / ".env"

    def settings_path(self, env: HarnessEnv) -> Path:
        return env.home / ".gemini" / "settings.json"

    def config_paths(self, env: HarnessEnv) -> tuple[Path, ...]:
        return (self.env_path(env), self.settings_path(env))

    def edits(
        self, env: HarnessEnv, endpoint: Endpoint, earlier: Mapping[str, Any]
    ) -> list[Planned]:
        path = self.env_path(env)
        values: dict[tuple[str, ...], Any] = {
            (key,): value for key, value in gemini_values(endpoint).items()
        }
        env_edit = merge_edit(path, DOTENV, values, earlier.get(str(path)))
        settings = self.settings_path(env)
        auth = {AUTH_TYPE_PATH: "gemini-api-key"}
        settings_edit = merge_edit(settings, JSON, auth, earlier.get(str(settings)))
        return [
            (env_edit, f"proxy {endpoint.base_url}, Egida key, GEMINI_MODEL={endpoint.model}"),
            (settings_edit, 'security.auth.selectedType "gemini-api-key"'),
        ]

    def undo(self, env: HarnessEnv, files: Mapping[str, Any]) -> list[Planned]:
        planned: list[Planned] = []
        for path, fmt, summary in (
            (self.env_path(env), DOTENV, "restore the Gemini variables Egida replaced"),
            (self.settings_path(env), JSON, "restore the previous auth type"),
        ):
            record = files.get(str(path))
            edit = None if record is None else restore_edit(path, fmt, record)
            if edit is not None:
                planned.append((edit, summary))
        return planned

    def points_at(self, env: HarnessEnv, record: Mapping[str, Any]) -> bool:
        base = read_dotenv(self.env_path(env)).get("GOOGLE_GEMINI_BASE_URL")
        return base == record.get("base_url")

    def launch(self, env: HarnessEnv, args: Sequence[str]) -> tuple[list[str], dict[str, str]]:
        """`gemini` with Egida's variables in its environment: works in untrusted folders and in
        headless `-p` runs, where Gemini CLI does not load `~/.gemini/.env`."""
        if not self.enabled(env):
            raise HarnessError(
                f"{self.name} is not set up for Egida yet; select it in `egd setup` first."
            )
        current = read_dotenv(self.env_path(env))
        values = {key: current[key] for key in GEMINI_VARS if key in current}
        return launch_command(env, self, args, values)


class AntigravityCli(EditingHarness):
    id: ClassVar[str] = "antigravity-cli"
    name: ClassVar[str] = "Antigravity CLI"
    protocol: ClassVar[Protocol | None] = "gemini"
    mode: ClassVar[Mode] = "launch"
    note: ClassVar[str] = (
        "sets modelProvider gemini in agy settings; start with: egd launch antigravity-cli"
    )
    binaries: ClassVar[tuple[str, ...]] = ("agy",)

    def settings_path(self, env: HarnessEnv) -> Path:
        return env.home / ".gemini" / "antigravity-cli" / "settings.json"

    def config_paths(self, env: HarnessEnv) -> tuple[Path, ...]:
        return (self.settings_path(env), launch_env_path(env, self.id))

    def install_paths(self, env: HarnessEnv) -> tuple[Path, ...]:
        return (env.home / ".local" / "bin" / "agy",)

    def config_dirs(self, env: HarnessEnv) -> tuple[Path, ...]:
        return (self.settings_path(env).parent,)

    def edits(
        self, env: HarnessEnv, endpoint: Endpoint, earlier: Mapping[str, Any]
    ) -> list[Planned]:
        settings = self.settings_path(env)
        settings_edit = merge_edit(
            settings, JSON, {("modelProvider",): "gemini"}, earlier.get(str(settings))
        )
        env_edit = launch_env_edit(env, self.id, gemini_values(endpoint))
        summary = f"launch env: proxy {endpoint.base_url}, Egida key, model {endpoint.model}"
        return [
            (settings_edit, 'modelProvider "gemini" (Gemini API key mode)'),
            (env_edit, summary),
        ]

    def undo(self, env: HarnessEnv, files: Mapping[str, Any]) -> list[Planned]:
        planned: list[Planned] = []
        settings = self.settings_path(env)
        record = files.get(str(settings))
        if record is not None:
            edit = restore_edit(settings, JSON, record)
            if edit is not None:
                planned.append((edit, "restore the previous modelProvider"))
        removed = delete_edit(launch_env_path(env, self.id))
        if removed is not None:
            planned.append((removed, "delete the launch env file"))
        return planned

    def points_at(self, env: HarnessEnv, record: Mapping[str, Any]) -> bool:
        if get_path(load_json(self.settings_path(env)), ("modelProvider",)) != "gemini":
            return False
        return read_dotenv(launch_env_path(env, self.id)).get(
            "GOOGLE_GEMINI_BASE_URL"
        ) == record.get("base_url")

    def launch(self, env: HarnessEnv, args: Sequence[str]) -> tuple[list[str], dict[str, str]]:
        return launch_command(env, self, args)
