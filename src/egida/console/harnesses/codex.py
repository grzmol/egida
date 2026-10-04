"""Codex: a model provider `egida` in the user `config.toml`, selected as the default provider.

Codex speaks only the OpenAI Responses API (`wire_api = "responses"`, served by
`adapters/responses_api.py`). Codex does not know local model ids, so Egida also writes a model
catalog (`egida-models.json`) next to the config and points `model_catalog_json` at it. Hosted web
search is switched off because the chat upstream behind the proxy cannot run it.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, ClassVar, Final

from egida.console.harnesses.base import Endpoint, HarnessEnv, Mode, Protocol
from egida.console.harnesses.files import (
    TOML,
    EditingHarness,
    Planned,
    delete_edit,
    dump_json,
    get_path,
    load_toml,
    merge_edit,
    owned_edit,
    restore_edit,
)

__all__ = ["Codex"]

PROVIDER: Final = "egida"
CONTEXT_WINDOW: Final = 131072


def catalog(model: str) -> dict[str, Any]:
    """Codex model catalog with one entry for `model` (the shape `ollama launch` writes)."""
    return {
        "models": [
            {
                "slug": model,
                "display_name": model,
                "context_window": CONTEXT_WINDOW,
                "shell_type": "default",
                "visibility": "list",
                "supported_in_api": True,
                "priority": 0,
                "truncation_policy": {"mode": "bytes", "limit": 10000},
                "input_modalities": ["text"],
                "base_instructions": "",
                "support_verbosity": True,
                "default_verbosity": "low",
                "supports_parallel_tool_calls": False,
                "supports_reasoning_summaries": False,
                "supported_reasoning_levels": [],
                "default_reasoning_level": None,
                "experimental_supported_tools": [],
            }
        ]
    }


class Codex(EditingHarness):
    id: ClassVar[str] = "codex"
    name: ClassVar[str] = "Codex"
    protocol: ClassVar[Protocol | None] = "openai-responses"
    mode: ClassVar[Mode] = "config"
    note: ClassVar[str] = (
        "adds model provider egida to config.toml and makes it the default; start with: codex"
    )
    binaries: ClassVar[tuple[str, ...]] = ("codex",)

    def codex_home(self, env: HarnessEnv) -> Path:
        return env.dir_from("CODEX_HOME", env.home / ".codex")

    def config_path(self, env: HarnessEnv) -> Path:
        return self.codex_home(env) / "config.toml"

    def catalog_path(self, env: HarnessEnv) -> Path:
        return self.codex_home(env) / "egida-models.json"

    def config_paths(self, env: HarnessEnv) -> tuple[Path, ...]:
        return (self.config_path(env), self.catalog_path(env))

    def config_dirs(self, env: HarnessEnv) -> tuple[Path, ...]:
        return (self.codex_home(env),)

    def edits(
        self, env: HarnessEnv, endpoint: Endpoint, earlier: Mapping[str, Any]
    ) -> list[Planned]:
        config = self.config_path(env)
        catalog_file = self.catalog_path(env)
        provider = {
            "name": "Egida",
            "base_url": endpoint.openai_base,
            "wire_api": "responses",
            "experimental_bearer_token": endpoint.key,
        }
        values: dict[tuple[str, ...], Any] = {
            ("model_provider",): PROVIDER,
            ("model",): endpoint.model,
            ("model_catalog_json",): str(catalog_file),
            ("web_search",): "disabled",
            ("model_providers", PROVIDER): provider,
        }
        config_edit = merge_edit(config, TOML, values, earlier.get(str(config)))
        catalog_edit = owned_edit(catalog_file, dump_json(catalog(endpoint.model)))
        summary = f"provider egida ({endpoint.openai_base}, Responses API), model {endpoint.model}"
        return [
            (config_edit, summary),
            (catalog_edit, f"model catalog with {endpoint.model}"),
        ]

    def undo(self, env: HarnessEnv, files: Mapping[str, Any]) -> list[Planned]:
        planned: list[Planned] = []
        config = self.config_path(env)
        record = files.get(str(config))
        if record is not None:
            edit = restore_edit(config, TOML, record)
            if edit is not None:
                planned.append((edit, "remove provider egida, restore the previous model settings"))
        catalog_file = self.catalog_path(env)
        if str(catalog_file) in files:
            removed = delete_edit(catalog_file)
            if removed is not None:
                planned.append((removed, "remove the Egida model catalog"))
        return planned

    def points_at(self, env: HarnessEnv, record: Mapping[str, Any]) -> bool:
        doc = load_toml(self.config_path(env))
        base = get_path(doc, ("model_providers", PROVIDER, "base_url"))
        base_url = str(record.get("base_url", "")).rstrip("/") + "/v1"
        return bool(get_path(doc, ("model_provider",)) == PROVIDER and base == base_url)
