"""opencode: an OpenAI-compatible provider `egida` in opencode.json and the default model."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from egida.console.harnesses._managed import ConfigEdit, ManagedFileHarness
from egida.console.harnesses.base import Endpoint, HarnessEnv

__all__ = ["Opencode"]


class Opencode(ManagedFileHarness):
    id: ClassVar[str] = "opencode"
    name: ClassVar[str] = "opencode"
    note: ClassVar[str] = (
        "sets provider egida and the default model in opencode.json; start with opencode"
    )
    binaries: ClassVar[tuple[str, ...]] = ("opencode",)

    def config_paths(self, env: HarnessEnv) -> tuple[Path, ...]:
        return (env.xdg_config_home() / "opencode" / "opencode.json",)

    def install_paths(self, env: HarnessEnv) -> tuple[Path, ...]:
        return (env.home / ".opencode" / "bin" / "opencode",)

    def config_edits(self, env: HarnessEnv, endpoint: Endpoint) -> dict[Path, ConfigEdit]:
        provider = {
            "npm": "@ai-sdk/openai-compatible",
            "name": "Egida",
            "options": {"baseURL": endpoint.openai_base, "apiKey": endpoint.key},
            "models": {endpoint.model: {"name": f"{endpoint.model} (Egida)"}},
        }
        values = {("provider", "egida"): provider, ("model",): f"egida/{endpoint.model}"}
        summary = f"provider egida at {endpoint.openai_base}, model egida/{endpoint.model}"
        return {self.config_paths(env)[0]: ConfigEdit(values, summary)}
