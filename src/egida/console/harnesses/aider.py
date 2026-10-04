"""aider: OpenAI-compatible model, base URL and key in ~/.aider.conf.yml."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from egida.console.harnesses._managed import ConfigEdit, ManagedFileHarness
from egida.console.harnesses.base import Endpoint, HarnessEnv
from egida.console.harnesses.files import YAML_FORMAT, FileFormat

__all__ = ["Aider"]


class Aider(ManagedFileHarness):
    id: ClassVar[str] = "aider"
    name: ClassVar[str] = "aider"
    note: ClassVar[str] = (
        "sets model, openai-api-base and openai-api-key in ~/.aider.conf.yml; start with aider"
    )
    binaries: ClassVar[tuple[str, ...]] = ("aider",)
    file_format: ClassVar[FileFormat] = YAML_FORMAT

    def config_paths(self, env: HarnessEnv) -> tuple[Path, ...]:
        return (env.home / ".aider.conf.yml",)

    def install_paths(self, env: HarnessEnv) -> tuple[Path, ...]:
        return (env.home / ".local" / "bin" / "aider",)

    def config_dirs(self, env: HarnessEnv) -> tuple[Path, ...]:
        return ()  # the config file sits in the home directory, which always exists

    def installed(self, env: HarnessEnv) -> bool:
        return super().installed(env) or self.config_paths(env)[0].is_file()

    def config_edits(self, env: HarnessEnv, endpoint: Endpoint) -> dict[Path, ConfigEdit]:
        values: dict[tuple[str, ...], str] = {
            ("model",): f"openai/{endpoint.model}",
            ("openai-api-base",): endpoint.openai_base,
            ("openai-api-key",): endpoint.key,
        }
        summary = f"model openai/{endpoint.model} at {endpoint.openai_base}"
        return {self.config_paths(env)[0]: ConfigEdit(values, summary)}
