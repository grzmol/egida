"""omp (oh-my-pi): provider `egida` in ~/.omp/agent/models.yml. The default model stays as it is."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from egida.console.harnesses._managed import ConfigEdit, ManagedFileHarness
from egida.console.harnesses.base import Endpoint, HarnessEnv
from egida.console.harnesses.files import YAML_FORMAT, FileFormat

__all__ = ["OhMyPi"]


class OhMyPi(ManagedFileHarness):
    id: ClassVar[str] = "omp"
    name: ClassVar[str] = "omp"
    note: ClassVar[str] = "adds provider egida; pick egida/<model> with --model or /model"
    binaries: ClassVar[tuple[str, ...]] = ("omp",)
    file_format: ClassVar[FileFormat] = YAML_FORMAT

    def config_paths(self, env: HarnessEnv) -> tuple[Path, ...]:
        return (env.home / ".omp" / "agent" / "models.yml",)

    def config_edits(self, env: HarnessEnv, endpoint: Endpoint) -> dict[Path, ConfigEdit]:
        provider = {
            "baseUrl": endpoint.openai_base,
            "api": "openai-completions",
            "apiKey": endpoint.key,
            "authHeader": True,
            "models": [{"id": endpoint.model, "name": f"{endpoint.model} (Egida)"}],
        }
        summary = f"provider egida at {endpoint.openai_base}; pick egida/{endpoint.model}"
        return {self.config_paths(env)[0]: ConfigEdit({("providers", "egida"): provider}, summary)}
