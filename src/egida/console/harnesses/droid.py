"""Droid (Factory): a custom model in ~/.factory/settings.json, selected as the session default."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, ClassVar

from egida.console.harnesses._managed import ConfigEdit, ListEntry, ManagedFileHarness
from egida.console.harnesses.base import Endpoint, HarnessEnv

__all__ = ["Droid"]

ID_PREFIX = "custom:egida-"


def _is_ours(entry: Mapping[str, Any]) -> bool:
    return str(entry.get("id", "")).startswith(ID_PREFIX)


class Droid(ManagedFileHarness):
    id: ClassVar[str] = "droid"
    name: ClassVar[str] = "Droid"
    note: ClassVar[str] = (
        "adds a custom model in ~/.factory/settings.json and makes it the default; start with droid"
    )
    binaries: ClassVar[tuple[str, ...]] = ("droid",)

    def config_paths(self, env: HarnessEnv) -> tuple[Path, ...]:
        return (env.home / ".factory" / "settings.json",)

    def install_paths(self, env: HarnessEnv) -> tuple[Path, ...]:
        return (env.home / ".local" / "bin" / "droid",)

    def config_edits(self, env: HarnessEnv, endpoint: Endpoint) -> dict[Path, ConfigEdit]:
        model_id = f"{ID_PREFIX}{endpoint.model}"
        entry = {
            "model": endpoint.model,
            "displayName": f"{endpoint.model} [Egida]",
            "baseUrl": endpoint.openai_base,
            "apiKey": endpoint.key,
            "provider": "generic-chat-completion-api",
            "maxOutputTokens": 8192,
            "id": model_id,
        }
        edit = ConfigEdit(
            values={("sessionDefaultSettings", "model"): model_id},
            summary=f"custom model {model_id} at {endpoint.openai_base}, session default",
            list_entry=ListEntry(("customModels",), entry, _is_ours, index_key="index"),
        )
        return {self.config_paths(env)[0]: edit}
