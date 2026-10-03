"""Continue: a model entry `Egida <model>` in ~/.continue/config.yaml (created when missing)."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, ClassVar

from egida.console.harnesses._managed import ConfigEdit, ListEntry, ManagedFileHarness
from egida.console.harnesses.base import Endpoint, HarnessEnv
from egida.console.harnesses.files import YAML_FORMAT, FileFormat

__all__ = ["ContinueDev"]

NAME_PREFIX = "Egida "
SCAFFOLD = {"name": "Local Config", "version": "1.0.0", "schema": "v1"}


def _is_ours(entry: Mapping[str, Any]) -> bool:
    return str(entry.get("name", "")).startswith(NAME_PREFIX) and entry.get("provider") == "openai"


class ContinueDev(ManagedFileHarness):
    id: ClassVar[str] = "continue"
    name: ClassVar[str] = "Continue"
    note: ClassVar[str] = (
        "adds a model to ~/.continue/config.yaml; pick 'Egida <model>' in Continue"
    )
    file_format: ClassVar[FileFormat] = YAML_FORMAT

    def config_paths(self, env: HarnessEnv) -> tuple[Path, ...]:
        return (env.home / ".continue" / "config.yaml",)

    def config_edits(self, env: HarnessEnv, endpoint: Endpoint) -> dict[Path, ConfigEdit]:
        entry = {
            "name": f"{NAME_PREFIX}{endpoint.model}",
            "provider": "openai",
            "model": endpoint.model,
            "apiBase": endpoint.openai_base,
            "apiKey": endpoint.key,
            "roles": ["chat", "edit", "apply"],
        }
        edit = ConfigEdit(
            values={},
            summary=f"model {NAME_PREFIX}{endpoint.model} at {endpoint.openai_base}",
            list_entry=ListEntry(("models",), entry, _is_ours),
            scaffold=SCAFFOLD,
        )
        return {self.config_paths(env)[0]: edit}
