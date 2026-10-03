"""pi: provider `egida` in models.json and the default provider and model in settings.json."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from egida.console.harnesses._managed import ConfigEdit, ManagedFileHarness
from egida.console.harnesses.base import Endpoint, HarnessEnv

__all__ = ["Pi"]


class Pi(ManagedFileHarness):
    id: ClassVar[str] = "pi"
    name: ClassVar[str] = "pi"
    note: ClassVar[str] = (
        "adds provider egida to models.json and makes it the default; start with pi"
    )
    binaries: ClassVar[tuple[str, ...]] = ("pi",)

    def agent_dir(self, env: HarnessEnv) -> Path:
        return env.dir_from("PI_CODING_AGENT_DIR", env.home / ".pi" / "agent")

    def config_paths(self, env: HarnessEnv) -> tuple[Path, ...]:
        directory = self.agent_dir(env)
        return (directory / "models.json", directory / "settings.json")

    def config_dirs(self, env: HarnessEnv) -> tuple[Path, ...]:
        return (self.agent_dir(env),)

    def config_edits(self, env: HarnessEnv, endpoint: Endpoint) -> dict[Path, ConfigEdit]:
        models, settings = self.config_paths(env)
        provider = {
            "baseUrl": endpoint.openai_base,
            "api": "openai-completions",
            "apiKey": endpoint.key,
            "models": [{"id": endpoint.model}],
        }
        return {
            models: ConfigEdit(
                {("providers", "egida"): provider}, f"provider egida at {endpoint.openai_base}"
            ),
            settings: ConfigEdit(
                {("defaultProvider",): "egida", ("defaultModel",): endpoint.model},
                f"default provider egida, model {endpoint.model}",
            ),
        }
