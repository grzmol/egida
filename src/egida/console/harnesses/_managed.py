"""Shared edits for OpenAI-compatible harnesses configured through one or more JSON or YAML files.

A subclass names, per file, the key paths Egida sets, at most one entry Egida keeps in a list (for
example Droid's `customModels`), and keys a new file starts with. `EditingHarness` does the
writing and the ledger; this module builds the edits. The ledger keeps fingerprints of what Egida
wrote and the values it overwrote, so `remove` restores those values and deletes only Egida's own
entries; values the user changed afterwards stay as they are.
"""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Callable, Iterator, Mapping, MutableMapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

from egida.console.harnesses.base import (
    Endpoint,
    HarnessEnv,
    HarnessError,
    Mode,
    Protocol,
    display_path,
)
from egida.console.harnesses.files import (
    JSON,
    MISSING,
    SECRET_FILE_MODE,
    EditingHarness,
    FileEdit,
    FileFormat,
    Planned,
    delete_path,
    fingerprint,
    get_path,
    plain,
    restore_entries,
    set_entries,
    set_path,
)

__all__ = ["ConfigEdit", "ListEntry", "ManagedFileHarness"]


@dataclass(frozen=True, slots=True)
class ListEntry:
    """One entry Egida keeps in the list at `path`; `is_ours` recognises Egida's entries."""

    path: tuple[str, ...]
    entry: Mapping[str, Any]
    is_ours: Callable[[Mapping[str, Any]], bool]
    index_key: str | None = None  # set to the entry's position in the list


@dataclass(frozen=True, slots=True)
class ConfigEdit:
    values: Mapping[tuple[str, ...], Any]
    summary: str
    list_entry: ListEntry | None = None
    scaffold: Mapping[str, Any] = field(
        default_factory=dict
    )  # top-level keys a new file starts with


def _strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


class ManagedFileHarness(EditingHarness):
    protocol: ClassVar[Protocol | None] = "openai-chat"
    mode: ClassVar[Mode] = "config"
    file_format: ClassVar[FileFormat] = JSON

    @abstractmethod
    def config_edits(self, env: HarnessEnv, endpoint: Endpoint) -> dict[Path, ConfigEdit]:
        """Per file: what Egida sets."""

    def _convert(self, value: Any) -> Any:
        """Plain data in the file format's containers (YAML maps keep their order and comments)."""
        if isinstance(value, Mapping):
            converted = self.file_format.new_map()
            for key, item in value.items():
                converted[key] = self._convert(item)
            return converted
        if isinstance(value, list):
            return [self._convert(item) for item in value]
        return value

    # --- apply -----------------------------------------------------------------------------------

    def edits(
        self, env: HarnessEnv, endpoint: Endpoint, earlier: Mapping[str, Any]
    ) -> list[Planned]:
        fmt = self.file_format
        planned: list[Planned] = []
        for path, edit in self.config_edits(env, endpoint).items():
            existed_now = path.exists()
            data = fmt.load(path)
            before = fmt.dump(data) if existed_now else None
            recorded: Mapping[str, Any] = earlier.get(str(path), {})
            scaffold: list[dict[str, Any]] = list(recorded.get("scaffold", ()))
            try:
                if not existed_now and edit.scaffold:
                    values: dict[tuple[str, ...], Any] = {
                        (key,): self._convert(value) for key, value in edit.scaffold.items()
                    }
                    scaffold = set_entries(data, values, new_map=fmt.new_map)
                entries = set_entries(
                    data,
                    {key: self._convert(value) for key, value in edit.values.items()},
                    recorded.get("entries", ()),
                    new_map=fmt.new_map,
                )
                record: dict[str, Any] = {
                    "existed": bool(recorded.get("existed", existed_now)),
                    "entries": entries,
                    "scaffold": scaffold,
                }
                if edit.list_entry is not None:
                    record["list"] = self._put_list_entry(
                        data, edit.list_entry, recorded.get("list")
                    )
            except HarnessError as exc:
                raise HarnessError(f"{path}: {exc}") from exc
            text = fmt.dump(data)
            file_edit = FileEdit(
                path=path,
                action="update" if existed_now else "create",
                text=text,
                changed=text != before,
                record=record,
                mode=SECRET_FILE_MODE,
            )
            planned.append((file_edit, edit.summary))
        return planned

    def _put_list_entry(
        self, data: MutableMapping[str, Any], spec: ListEntry, earlier: Mapping[str, Any] | None
    ) -> dict[str, Any]:
        current = get_path(data, spec.path)
        created = current is MISSING
        if created:
            current = []
            set_path(data, spec.path, current, new_map=self.file_format.new_map)
        elif not isinstance(current, list):
            raise HarnessError(f"Setting {'.'.join(spec.path)} is not a list.")
        current[:] = [
            item for item in current if not (isinstance(item, Mapping) and spec.is_ours(item))
        ]
        entry = dict(spec.entry)
        if spec.index_key is not None:
            entry[spec.index_key] = len(current)
        current.append(self._convert(entry))
        return {
            "path": list(spec.path),
            "written": fingerprint(entry),
            "created": bool(earlier["created"]) if earlier else created,
        }

    # --- remove ----------------------------------------------------------------------------------

    def undo(self, env: HarnessEnv, files: Mapping[str, Any]) -> list[Planned]:
        fmt = self.file_format
        planned: list[Planned] = []
        for name, record in files.items():
            path = Path(name)
            if not path.exists():
                continue
            data = fmt.load(path)
            before = fmt.dump(data)
            if "list" in record:
                _drop_list_entry(data, record["list"])
            restore_entries(data, record.get("entries", ()))
            if not record.get("existed", True) and _only_scaffold(data, record.get("scaffold", ())):
                planned.append(
                    (FileEdit(path, "delete", None, True, {}), f"delete {display_path(env, path)}")
                )
                continue
            text = fmt.dump(data)
            if text != before:
                planned.append(
                    (
                        FileEdit(path, "update", text, True, {}),
                        f"remove Egida settings from {display_path(env, path)}",
                    )
                )
        return planned

    def points_at(self, env: HarnessEnv, record: Mapping[str, Any]) -> bool:
        target = str(record.get("base_url", "")).rstrip("/") + "/v1"
        for name in record.get("files", {}):
            path = Path(name)
            if path.exists() and target in set(_strings(plain(self.file_format.load(path)))):
                return True
        return False


def _drop_list_entry(data: MutableMapping[str, Any], record: Mapping[str, Any]) -> None:
    path = list(record["path"])
    current = get_path(data, path)
    if not isinstance(current, list):
        return
    current[:] = [item for item in current if fingerprint(item) != record["written"]]
    if record.get("created") and not current:
        delete_path(data, path)


def _only_scaffold(data: Mapping[str, Any], scaffold: Any) -> bool:
    """True when `data` holds nothing but the unchanged keys Egida started a new file with."""
    written = {entry["path"][0]: entry["written"] for entry in scaffold}
    return all(key in written and fingerprint(value) == written[key] for key, value in data.items())
