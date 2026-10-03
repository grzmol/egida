"""File helpers for harness configs: atomic writes, backups, format round trips and the ledger.

The ledger (`config_dir/harnesses.json`, mode 0o600) keeps, per harness, the values Egida overwrote,
so `remove` restores exactly those keys. Values Egida wrote are stored only as a fingerprint
(`fingerprint`), never in plain text: the harness key stays in the harness config alone.

Nested settings are addressed by a key path (`("env", "ANTHROPIC_BASE_URL")`). `set_entries`
writes values and returns ledger entries; `restore_entries` undoes them, but only where the current
value is still the one Egida wrote (a value the user changed afterwards stays).
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import stat
import tempfile
import time
from abc import abstractmethod
from collections.abc import Callable, Iterable, Mapping, MutableMapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal

import tomlkit
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap
from ruamel.yaml.error import YAMLError
from tomlkit.exceptions import TOMLKitError
from tomlkit.toml_document import TOMLDocument

from egida.console.harnesses.base import Change, Endpoint, Harness, HarnessEnv, HarnessError

__all__ = [
    "DOTENV",
    "JSON",
    "MISSING",
    "TOML",
    "YAML_FORMAT",
    "DotenvMap",
    "EditingHarness",
    "FileEdit",
    "FileFormat",
    "Ledger",
    "Planned",
    "atomic_write",
    "backup",
    "delete_edit",
    "delete_path",
    "dump_dotenv",
    "dump_json",
    "dump_toml",
    "dump_yaml",
    "ensure_config_dir",
    "fingerprint",
    "get_path",
    "launch_command",
    "launch_env_edit",
    "launch_env_path",
    "load_dotenv",
    "load_json",
    "load_toml",
    "load_yaml",
    "merge_edit",
    "owned_edit",
    "plain",
    "read_dotenv",
    "render_dotenv",
    "restore_edit",
    "restore_entries",
    "set_entries",
    "set_path",
    "update_dotenv",
    "write_edits",
]

KEEP_BACKUPS: Final = 5
NEW_FILE_MODE: Final = 0o644
SECRET_FILE_MODE: Final = 0o600
PRIVATE_DIR_MODE: Final = 0o700
LEDGER_NAME: Final = "harnesses.json"


class _Missing:
    def __repr__(self) -> str:
        return "MISSING"


MISSING: Final = _Missing()
"""Returned by `get_path` for a key that is not there."""


# --- writes and backups ---------------------------------------------------------------------------


def atomic_write(path: Path, text: str, *, mode: int | None = None) -> None:
    """Write `text` through a temp file in the same directory, fsync, then one rename. An existing
    file keeps its mode; a new file gets `mode` (default 0o644). Missing parents are created."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            file_mode = stat.S_IMODE(path.stat().st_mode)
        except FileNotFoundError:
            file_mode = NEW_FILE_MODE if mode is None else mode
        fd, temp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    except OSError as exc:
        raise HarnessError(f"Cannot write {path}: {exc.strerror or exc}.") from exc
    temp = Path(temp_name)
    replaced = False
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp, file_mode)
        os.replace(temp, path)
        replaced = True
    except OSError as exc:
        raise HarnessError(f"Cannot write {path}: {exc.strerror or exc}.") from exc
    finally:
        if not replaced:
            temp.unlink(missing_ok=True)


def ensure_config_dir(env: HarnessEnv) -> Path:
    """Egida's user directory, created with mode 0o700 (it holds keys and backups)."""
    try:
        env.config_dir.mkdir(parents=True, exist_ok=True, mode=PRIVATE_DIR_MODE)
        os.chmod(env.config_dir, PRIVATE_DIR_MODE)
    except OSError as exc:
        raise HarnessError(f"Cannot create {env.config_dir}: {exc.strerror or exc}.") from exc
    return env.config_dir


_BACKUP_SUFFIX = re.compile(r"\.(\d+)(?:\.(\d+))?$")


def _backup_order(path: Path) -> tuple[int, int]:
    match = _BACKUP_SUFFIX.search(path.name)
    if match is None:
        return (0, 0)
    return (int(match.group(1)), int(match.group(2) or 0))


def backup(env: HarnessEnv, harness_id: str, path: Path) -> Path | None:
    """Copy `path` to `config_dir/backups/<id>/<name>.<unix_ts>` (mode 0o600, it may hold keys) and
    keep the newest five copies of that file. None when `path` does not exist."""
    if not path.is_file():
        return None
    folder = ensure_config_dir(env) / "backups" / harness_id
    prefix = path.name + "."
    try:
        folder.mkdir(parents=True, exist_ok=True, mode=PRIVATE_DIR_MODE)
        copies = [
            item
            for item in folder.iterdir()
            if item.name.startswith(prefix)
            and _BACKUP_SUFFIX.fullmatch(item.name[len(path.name) :])
        ]
        # A copy always sorts after every earlier one, even within the same second.
        stamp, counter = int(time.time()), 0
        newest = max((_backup_order(item) for item in copies), default=None)
        if newest is not None and newest >= (stamp, 0):
            stamp, counter = newest[0], newest[1] + 1
        target = folder / (f"{prefix}{stamp}.{counter}" if counter else f"{prefix}{stamp}")
        shutil.copyfile(path, target)
        os.chmod(target, SECRET_FILE_MODE)
        for old in sorted([*copies, target], key=_backup_order)[:-KEEP_BACKUPS]:
            old.unlink(missing_ok=True)
    except OSError as exc:
        raise HarnessError(f"Cannot back up {path} to {folder}: {exc.strerror or exc}.") from exc
    return target


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError) as exc:
        raise HarnessError(f"Cannot read {path}: {exc}.") from exc


# --- formats --------------------------------------------------------------------------------------


def load_json(path: Path) -> dict[str, Any]:
    """The JSON object in `path`; {} when the file is missing or empty."""
    text = _read_text(path)
    if text is None or not text.strip():
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise HarnessError(f"{path} is not valid JSON: {exc}.") from exc
    if not isinstance(data, dict):
        raise HarnessError(f"{path} does not hold a JSON object.")
    return data


def dump_json(data: Mapping[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _yaml() -> YAML:
    yaml = YAML(typ="rt")
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.width = 4096
    return yaml


def load_yaml(path: Path) -> CommentedMap:
    """The YAML mapping in `path` as a round-trip map (comments kept); empty when missing."""
    text = _read_text(path)
    if text is None or not text.strip():
        return CommentedMap()
    try:
        data = _yaml().load(text)
    except YAMLError as exc:
        raise HarnessError(f"{path} is not valid YAML: {exc}.") from exc
    if data is None:
        return CommentedMap()
    if not isinstance(data, CommentedMap):
        raise HarnessError(f"{path} does not hold a YAML mapping.")
    return data


def dump_yaml(data: CommentedMap) -> str:
    stream = io.StringIO()
    _yaml().dump(data, stream)
    return stream.getvalue()


def load_toml(path: Path) -> TOMLDocument:
    """The TOML document in `path` (comments kept); empty when missing."""
    text = _read_text(path)
    if text is None:
        return tomlkit.document()
    try:
        return tomlkit.parse(text)
    except TOMLKitError as exc:
        raise HarnessError(f"{path} is not valid TOML: {exc}.") from exc


def dump_toml(doc: TOMLDocument) -> str:
    """TOML text of `doc`. Blank lines tomlkit leaves at the start or end after a key is added
    above a table and removed again are dropped, so a restore gives back the original text."""
    text = tomlkit.dumps(doc).lstrip("\n").rstrip("\n")
    return text + "\n" if text else ""


# --- dotenv ---------------------------------------------------------------------------------------

_DOTENV_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$")
_PLAIN_VALUE = re.compile(r"^[A-Za-z0-9_./:@+,=-]*$")


def _dotenv_value(raw: str) -> str:
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        inner = raw[1:-1]
        return inner.replace('\\"', '"').replace("\\\\", "\\") if raw[0] == '"' else inner
    return re.split(r"\s+#", raw, maxsplit=1)[0].strip()


def _dotenv_line(key: str, value: str) -> str:
    if _PLAIN_VALUE.match(value):
        return f"{key}={value}"
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'{key}="{escaped}"'


def read_dotenv(path: Path) -> dict[str, str]:
    """KEY=value pairs of a dotenv file (the last one wins); {} when missing."""
    text = _read_text(path)
    values: dict[str, str] = {}
    for line in (text or "").splitlines():
        match = _DOTENV_LINE.match(line)
        if match:
            values[match.group(1)] = _dotenv_value(match.group(2))
    return values


def render_dotenv(text: str, values: Mapping[str, str | None]) -> str:
    """`text` with `values` set (None removes the key); other lines and comments kept."""
    lines = text.splitlines()
    out: list[str] = []
    done: set[str] = set()
    for line in lines:
        match = _DOTENV_LINE.match(line)
        if match is None or match.group(1) not in values:
            out.append(line)
            continue
        key = match.group(1)
        value = values[key]
        if value is None or key in done:
            continue
        out.append(_dotenv_line(key, value))
        done.add(key)
    for key, value in values.items():
        if value is not None and key not in done:
            out.append(_dotenv_line(key, value))
    return "\n".join(out) + "\n" if out else ""


def update_dotenv(path: Path, values: Mapping[str, str | None]) -> dict[str, str | None]:
    """Set `values` in the dotenv file `path` (None removes the key) and return the previous value
    of each key (None = was absent). A new file gets mode 0o600 because it holds a key."""
    text = _read_text(path)
    before = read_dotenv(path)
    previous: dict[str, str | None] = {key: before.get(key) for key in values}
    new_text = render_dotenv(text or "", values)
    if new_text != (text or "") or text is None:
        atomic_write(path, new_text, mode=SECRET_FILE_MODE)
    return previous


# --- nested values and ledger entries -------------------------------------------------------------


def plain(value: Any) -> Any:
    """`value` as plain JSON data (tomlkit and ruamel containers and scalars unwrapped)."""
    if isinstance(value, Mapping):
        return {str(key): plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    if isinstance(value, bool):
        return bool(value)
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return float(value)
    if isinstance(value, str):
        return str(value)
    return value


def fingerprint(value: Any) -> str:
    """sha256 of the canonical JSON of `value`: lets the ledger recognise Egida's own value later
    without storing it (it may be a key)."""
    canonical = json.dumps(plain(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def get_path(data: Mapping[str, Any], path: Sequence[str]) -> Any:
    node: Any = data
    for key in path:
        if not isinstance(node, Mapping) or key not in node:
            return MISSING
        node = node[key]
    return node


def set_path(
    data: MutableMapping[str, Any],
    path: Sequence[str],
    value: Any,
    *,
    new_map: Callable[[], MutableMapping[str, Any]] = dict,
) -> list[list[str]]:
    """Set `value` at `path`, creating missing parent maps with `new_map`. Returns the parent paths
    it created. A parent that exists but is not a map is an error."""
    created: list[list[str]] = []
    node: MutableMapping[str, Any] = data
    for depth, key in enumerate(path[:-1]):
        if key not in node:
            node[key] = new_map()
            created.append(list(path[: depth + 1]))
        child = node[key]
        if not isinstance(child, MutableMapping):
            raise HarnessError(f"Setting {'.'.join(path[: depth + 1])} is not a table or object.")
        node = child
    node[path[-1]] = value
    return created


def delete_path(data: MutableMapping[str, Any], path: Sequence[str]) -> bool:
    parent = get_path(data, path[:-1]) if len(path) > 1 else data
    if isinstance(parent, MutableMapping) and path[-1] in parent:
        del parent[path[-1]]
        return True
    return False


def set_entries(
    data: MutableMapping[str, Any],
    values: Mapping[tuple[str, ...], Any],
    recorded: Iterable[Mapping[str, Any]] = (),
    *,
    new_map: Callable[[], MutableMapping[str, Any]] = dict,
) -> list[dict[str, Any]]:
    """Write `values` (key path -> value) into `data` and return ledger entries: `path`, `written`
    (fingerprint), and either `previous` (the value overwritten) or `absent: true`, plus `created`
    (parent maps Egida added). Entries in `recorded` (from an earlier apply) keep their original
    `previous`/`absent`/`created`, so a second apply never records Egida's own values."""
    earlier = {tuple(entry["path"]): entry for entry in recorded}
    entries: list[dict[str, Any]] = []
    for path, value in values.items():
        old = earlier.get(path)
        current = get_path(data, path)
        created = set_path(data, path, value, new_map=new_map)
        entry: dict[str, Any] = {"path": list(path), "written": fingerprint(value)}
        if old is not None:
            for key in ("previous", "absent", "created"):
                if key in old:
                    entry[key] = old[key]
            entry["created"] = [*entry.get("created", []), *created]
        else:
            if current is MISSING:
                entry["absent"] = True
            else:
                entry["previous"] = plain(current)
            entry["created"] = created
        entries.append(entry)
    return entries


def restore_entries(data: MutableMapping[str, Any], entries: Iterable[Mapping[str, Any]]) -> None:
    """Undo `set_entries`: where the value is still Egida's, put back the previous value or delete
    the key; then drop parent maps Egida created if they are empty now. User edits stay."""
    created: list[list[str]] = []
    for entry in entries:
        path = list(entry["path"])
        current = get_path(data, path)
        if current is not MISSING and fingerprint(current) == entry["written"]:
            if entry.get("absent"):
                delete_path(data, path)
            else:
                set_path(data, path, entry.get("previous"))
        created.extend(list(item) for item in entry.get("created", []))
    for parent in sorted(created, key=len, reverse=True):
        node = get_path(data, parent)
        if isinstance(node, Mapping) and not node:
            delete_path(data, parent)


# --- ledger ---------------------------------------------------------------------------------------


class Ledger:
    """Per-harness records of what Egida changed, in `config_dir/harnesses.json` (mode 0o600)."""

    def __init__(self, env: HarnessEnv) -> None:
        self.env = env
        self.path = env.config_dir / LEDGER_NAME

    def _load(self) -> dict[str, Any]:
        data = load_json(self.path)
        harnesses = data.get("harnesses", {})
        if not isinstance(harnesses, dict):
            raise HarnessError(f"{self.path} is damaged: 'harnesses' is not an object.")
        return harnesses

    def _save(self, harnesses: Mapping[str, Any]) -> None:
        ensure_config_dir(self.env)
        atomic_write(
            self.path,
            dump_json({"version": 1, "harnesses": dict(harnesses)}),
            mode=SECRET_FILE_MODE,
        )

    def get(self, harness_id: str) -> dict[str, Any] | None:
        record = self._load().get(harness_id)
        return record if isinstance(record, dict) else None

    def put(self, harness_id: str, record: Mapping[str, Any]) -> None:
        harnesses = self._load()
        harnesses[harness_id] = plain(record)
        self._save(harnesses)

    def pop(self, harness_id: str) -> dict[str, Any] | None:
        harnesses = self._load()
        record = harnesses.pop(harness_id, None)
        if record is not None:
            self._save(harnesses)
        return record if isinstance(record, dict) else None


# --- whole-file edits -----------------------------------------------------------------------------


class DotenvMap(dict[str, str]):
    """A dotenv file as a dict that remembers its text, so `dump_dotenv` keeps comments."""

    def __init__(self, text: str = "") -> None:
        super().__init__()
        self.text = text
        for line in text.splitlines():
            match = _DOTENV_LINE.match(line)
            if match:
                self[match.group(1)] = _dotenv_value(match.group(2))


def load_dotenv(path: Path) -> DotenvMap:
    return DotenvMap(_read_text(path) or "")


def dump_dotenv(data: DotenvMap) -> str:
    before = DotenvMap(data.text)
    values: dict[str, str | None] = {key: None for key in before if key not in data}
    values.update({key: value for key, value in data.items() if before.get(key) != value})
    return render_dotenv(data.text, values) if values or data.text else ""


@dataclass(frozen=True, slots=True)
class FileFormat:
    """How to read and write one config format as a nested mapping."""

    load: Callable[[Path], Any]
    dump: Callable[[Any], str]
    new_map: Callable[[], MutableMapping[str, Any]] = dict
    new_mode: int = NEW_FILE_MODE  # mode of a file Egida creates


JSON: Final = FileFormat(load=load_json, dump=dump_json)
YAML_FORMAT: Final = FileFormat(load=load_yaml, dump=dump_yaml, new_map=CommentedMap)
TOML: Final = FileFormat(
    load=load_toml, dump=dump_toml, new_map=lambda: tomlkit.table(is_super_table=True)
)
DOTENV: Final = FileFormat(load=load_dotenv, dump=dump_dotenv, new_mode=SECRET_FILE_MODE)


@dataclass(frozen=True, slots=True)
class FileEdit:
    """One planned file change. `text` None deletes the file; `record` goes into the ledger
    (`{"existed": bool, "entries": [...]}` for merges, `{"existed": bool, "owned": true}` for whole
    files Egida owns)."""

    path: Path
    action: Literal["create", "update", "delete"]
    text: str | None
    changed: bool
    record: dict[str, Any]
    mode: int = NEW_FILE_MODE


def merge_edit(
    path: Path,
    fmt: FileFormat,
    values: Mapping[tuple[str, ...], Any],
    earlier: Mapping[str, Any] | None = None,
) -> FileEdit:
    """Plan writing `values` into the config file `path`. `earlier` is this file's record from a
    previous apply. A file that does not parse raises HarnessError (nothing is written)."""
    existed_now = path.exists()
    data = fmt.load(path)
    before = fmt.dump(data) if existed_now else None
    try:
        entries = set_entries(data, values, (earlier or {}).get("entries", ()), new_map=fmt.new_map)
    except HarnessError as exc:
        raise HarnessError(f"{path}: {exc}") from exc
    text = fmt.dump(data)
    existed = bool(earlier["existed"]) if earlier is not None else existed_now
    return FileEdit(
        path=path,
        action="update" if existed_now else "create",
        text=text,
        changed=text != before,
        record={"existed": existed, "entries": entries},
        mode=fmt.new_mode,
    )


def restore_edit(path: Path, fmt: FileFormat, record: Mapping[str, Any]) -> FileEdit | None:
    """Plan undoing a `merge_edit`. A file Egida created and that is empty afterwards is deleted.
    None when the file is gone or nothing changes."""
    if not path.exists():
        return None
    data = fmt.load(path)
    before = fmt.dump(data)
    restore_entries(data, record.get("entries", ()))
    if not record.get("existed", True) and not plain(data):
        return FileEdit(path=path, action="delete", text=None, changed=True, record={})
    text = fmt.dump(data)
    if text == before:
        return None
    return FileEdit(path=path, action="update", text=text, changed=True, record={})


def owned_edit(path: Path, text: str, *, mode: int = NEW_FILE_MODE) -> FileEdit:
    """Plan writing a file Egida owns completely (catalog, launch env file)."""
    try:
        before = path.read_text(encoding="utf-8") if path.exists() else None
    except (OSError, UnicodeDecodeError) as exc:
        raise HarnessError(f"Cannot read {path}: {exc}.") from exc
    return FileEdit(
        path=path,
        action="update" if before is not None else "create",
        text=text,
        changed=text != before,
        record={"owned": True},
        mode=mode,
    )


def delete_edit(path: Path) -> FileEdit | None:
    """Plan deleting a file Egida owns; None when it is already gone."""
    if not path.exists():
        return None
    return FileEdit(path=path, action="delete", text=None, changed=True, record={})


def write_edits(env: HarnessEnv, harness_id: str, edits: Iterable[FileEdit]) -> None:
    """Carry out planned edits: back up each existing file once, then write atomically or delete.
    Files inside Egida's own directory (launch env files) are not backed up."""
    for edit in edits:
        if not edit.changed:
            continue
        if env.config_dir in edit.path.parents:
            ensure_config_dir(env)
        else:
            backup(env, harness_id, edit.path)
        if edit.text is None:
            try:
                edit.path.unlink(missing_ok=True)
            except OSError as exc:
                raise HarnessError(f"Cannot delete {edit.path}: {exc.strerror or exc}.") from exc
        else:
            atomic_write(edit.path, edit.text, mode=edit.mode)


# --- launch env files -----------------------------------------------------------------------------


def launch_env_path(env: HarnessEnv, harness_id: str) -> Path:
    """`config_dir/launch/<id>.env`: the environment `egd launch <id>` starts the harness with."""
    return env.config_dir / "launch" / f"{harness_id}.env"


def launch_env_edit(env: HarnessEnv, harness_id: str, values: Mapping[str, str]) -> FileEdit:
    """Plan writing the launch env file (mode 0o600, it holds the key)."""
    header = (
        f"# Written by egd for `egd launch {harness_id}`. Holds an Egida API key; do not share.\n"
    )
    return owned_edit(
        launch_env_path(env, harness_id), render_dotenv(header, values), mode=SECRET_FILE_MODE
    )


def launch_command(
    env: HarnessEnv,
    harness: Harness,
    args: Sequence[str],
    values: Mapping[str, str] | None = None,
) -> tuple[list[str], dict[str, str]]:
    """argv (the harness binary, then `args`) and the env to start it with: `values`, or by
    default the harness's launch env file."""
    if values is None:
        values = read_dotenv(launch_env_path(env, harness.id))
    if not values:
        raise HarnessError(
            f"{harness.name} is not set up for Egida yet; select it in `egd setup` first."
        )
    binary = harness.found_binary(env)
    if binary is None:
        names = ", ".join(harness.binaries)
        raise HarnessError(f"{harness.name} is not installed: {names} not found on PATH.")
    return [binary, *args], dict(values)


# --- harnesses made of file edits -----------------------------------------------------------------

Planned = tuple[FileEdit, str]  # an edit and its one-line summary for the wizard review


class EditingHarness(Harness):
    """A harness whose setup is a list of file edits. Subclasses describe the edits; this class
    plans, writes (backup first, atomic), and keeps the ledger record:
    `{"base_url", "model", "files": {"<path>": <FileEdit.record>}}`."""

    @abstractmethod
    def edits(
        self, env: HarnessEnv, endpoint: Endpoint, earlier: Mapping[str, Any]
    ) -> list[Planned]:
        """Edits for `apply`. `earlier` maps a path string to its record from the last apply."""

    @abstractmethod
    def undo(self, env: HarnessEnv, files: Mapping[str, Any]) -> list[Planned]:
        """Edits for `remove`, from the recorded `files`."""

    @abstractmethod
    def points_at(self, env: HarnessEnv, record: Mapping[str, Any]) -> bool:
        """The harness config still uses `record["base_url"]` (read errors count as False)."""

    def enabled(self, env: HarnessEnv) -> bool:
        try:
            record = Ledger(env).get(self.id)
            return record is not None and self.points_at(env, record)
        except HarnessError:
            return False

    def _earlier(self, env: HarnessEnv) -> dict[str, Any]:
        record = Ledger(env).get(self.id)
        files = record.get("files", {}) if record else {}
        return files if isinstance(files, dict) else {}

    def plan(self, env: HarnessEnv, endpoint: Endpoint) -> list[Change]:
        return [
            Change(e.path, e.action, s)
            for e, s in self.edits(env, endpoint, self._earlier(env))
            if e.changed
        ]

    def apply(self, env: HarnessEnv, endpoint: Endpoint) -> list[Change]:
        planned = self.edits(env, endpoint, self._earlier(env))
        write_edits(env, self.id, [edit for edit, _ in planned])
        files = {str(edit.path): edit.record for edit, _ in planned}
        Ledger(env).put(
            self.id, {"base_url": endpoint.base_url, "model": endpoint.model, "files": files}
        )
        return [Change(e.path, e.action, s) for e, s in planned if e.changed]

    def plan_remove(self, env: HarnessEnv) -> list[Change]:
        record = Ledger(env).get(self.id)
        if record is None:
            return []
        return [
            Change(e.path, e.action, s)
            for e, s in self.undo(env, record.get("files", {}))
            if e.changed
        ]

    def remove(self, env: HarnessEnv) -> list[Change]:
        ledger = Ledger(env)
        record = ledger.get(self.id)
        if record is None:
            return []
        planned = self.undo(env, record.get("files", {}))
        write_edits(env, self.id, [edit for edit, _ in planned])
        ledger.pop(self.id)
        return [Change(e.path, e.action, s) for e, s in planned if e.changed]
