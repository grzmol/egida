"""GitHub Copilot CLI: bring-your-own-key provider settings, read from the environment only.

Copilot CLI has no config file for a custom provider, so Egida keeps the variables in a launch env
file and `egd launch copilot-cli` starts `copilot` with them. The provider type stays the default
(`openai`, Chat Completions).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, ClassVar

from egida.console.harnesses.base import Endpoint, HarnessEnv, Mode, Protocol
from egida.console.harnesses.files import (
    EditingHarness,
    Planned,
    delete_edit,
    launch_command,
    launch_env_edit,
    launch_env_path,
    read_dotenv,
)

__all__ = ["CopilotCli"]


class CopilotCli(EditingHarness):
    id: ClassVar[str] = "copilot-cli"
    name: ClassVar[str] = "Copilot CLI"
    protocol: ClassVar[Protocol | None] = "openai-chat"
    mode: ClassVar[Mode] = "launch"
    note: ClassVar[str] = (
        "keeps the provider variables in a launch env file; start with: egd launch copilot-cli"
    )
    binaries: ClassVar[tuple[str, ...]] = ("copilot",)

    def config_paths(self, env: HarnessEnv) -> tuple[Path, ...]:
        return (launch_env_path(env, self.id),)

    def install_paths(self, env: HarnessEnv) -> tuple[Path, ...]:
        return (env.home / ".local" / "bin" / "copilot",)

    def config_dirs(self, env: HarnessEnv) -> tuple[Path, ...]:
        return (env.home / ".copilot",)

    def edits(
        self, env: HarnessEnv, endpoint: Endpoint, earlier: Mapping[str, Any]
    ) -> list[Planned]:
        values = {
            "COPILOT_PROVIDER_BASE_URL": endpoint.openai_base,
            "COPILOT_PROVIDER_API_KEY": endpoint.key,
            "COPILOT_MODEL": endpoint.model,
        }
        edit = launch_env_edit(env, self.id, values)
        return [
            (
                edit,
                f"launch env: proxy {endpoint.openai_base}, Egida key, model {endpoint.model}",
            )
        ]

    def undo(self, env: HarnessEnv, files: Mapping[str, Any]) -> list[Planned]:
        removed = delete_edit(launch_env_path(env, self.id))
        return [] if removed is None else [(removed, "delete the launch env file")]

    def points_at(self, env: HarnessEnv, record: Mapping[str, Any]) -> bool:
        base = str(record.get("base_url", "")).rstrip("/") + "/v1"
        return read_dotenv(launch_env_path(env, self.id)).get("COPILOT_PROVIDER_BASE_URL") == base

    def launch(self, env: HarnessEnv, args: Sequence[str]) -> tuple[list[str], dict[str, str]]:
        return launch_command(env, self, args)
