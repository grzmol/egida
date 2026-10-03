"""Editable policy file for Egida: round-trip YAML that keeps comments, blank lines, quoting and
indentation, edits addressed by key paths, the proxy's own validation and atomic saving.

ruamel.yaml keeps the comment that ends a line together with every blank/comment line that follows
it in one token on the node of that line (for a block collection: on its deepest last key). Those
following lines belong to their place in the file, not to the node, so every structural edit here
moves them: a deleted node hands them to the node before it, an appended node takes them over from
the old last node, and moved controls leave them at their positions.
"""

from __future__ import annotations

import contextlib
import difflib
import io
import os
import stat
import tempfile
from collections import deque
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from pydantic import BaseModel
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.error import CommentMark, MarkedYAMLError, YAMLError
from ruamel.yaml.scalarbool import ScalarBoolean
from ruamel.yaml.scalarfloat import ScalarFloat
from ruamel.yaml.scalarint import ScalarInt
from ruamel.yaml.scalarstring import ScalarString
from ruamel.yaml.tokens import CommentToken
from ruamel.yaml.util import load_yaml_guess_indent

from egida.adapters.policy_file import parse_policy
from egida.core.errors import PolicyError

__all__ = [
    "NAMED_SECTIONS",
    "ConflictError",
    "DocumentError",
    "InUseError",
    "PathKey",
    "PolicyDocument",
]

PathKey = tuple[str | int, ...]
NAMED_SECTIONS: Final = ("upstreams", "models", "agents", "budgets")
_ROOT_ORDER: Final = ("version", "defaults", "limits", *NAMED_SECTIONS, "controls")
_NEW_FILE_MODE: Final = 0o644


class DocumentError(Exception):
    """An edit, load or save was refused; str(exc) is a user-facing sentence."""


class ConflictError(DocumentError):
    """The file changed on disk since it was opened or last saved."""


class InUseError(DocumentError):
    """A named entry cannot be deleted while other entries refer to it."""

    def __init__(self, message: str, users: Sequence[str]) -> None:
        super().__init__(message)
        self.users: tuple[str, ...] = tuple(users)


def _is_container(node: Any) -> bool:
    return isinstance(node, CommentedMap | CommentedSeq)


def _is_block(node: Any) -> bool:
    return _is_container(node) and not node.fa.flow_style(False)


def _keys(container: Any) -> list[Any]:
    return list(container) if isinstance(container, CommentedMap) else list(range(len(container)))


def _is_index(key: object) -> bool:
    return isinstance(key, int) and not isinstance(key, bool)


def _child(node: Any, key: str | int) -> tuple[bool, Any]:
    if isinstance(node, CommentedMap):
        return (key in node, node.get(key))
    if isinstance(node, CommentedSeq) and _is_index(key) and 0 <= int(key) < len(node):
        return (True, node[key])
    return (False, None)


def _split(value: str) -> tuple[str, str]:
    """Token text → (end-of-line comment without newline, following lines)."""
    if value.lstrip(" ").startswith("#"):
        eol, _, rest = value.partition("\n")
        return eol.lstrip(" "), rest
    if value.startswith("\n"):
        return "", value[1:]
    return "", value


def _ends_with_blank_line(text: str) -> bool:
    return text == "\n" or text.endswith("\n\n")


class _Slot:
    """The token that ends the line of `container[key]`."""

    __slots__ = ("_container", "_key")

    def __init__(self, container: Any, key: Any) -> None:
        self._container = container
        self._key = key

    def _child_comment(self) -> list[Any] | None:
        """ruamel's second copy of a collection key's comment, kept on the collection itself."""
        container, key = self._container, self._key
        child: Any = container[key] if key in _keys(container) else None
        if _is_container(child) and child.ca.comment:
            comment: list[Any] = child.ca.comment
            return comment
        return None

    def _token(self) -> CommentToken | None:
        container, key = self._container, self._key
        index = 0 if isinstance(container, CommentedSeq) else 2
        entry = container.ca.items.get(key)
        token = entry[index] if entry and len(entry) > index else None
        if not isinstance(token, CommentToken):
            copy = self._child_comment()
            token = copy[0] if copy else None
        return token if isinstance(token, CommentToken) else None

    def _write(self, eol: str, trailing: str, column: int) -> None:
        container, key = self._container, self._key
        index = 0 if isinstance(container, CommentedSeq) else 2
        size = 2 if isinstance(container, CommentedSeq) else 4
        items = container.ca.items
        if eol or trailing:
            entry = items.setdefault(key, [None] * size)
            entry[index] = CommentToken(eol + "\n" + trailing, CommentMark(column), None)
        elif key in items:
            items[key][index] = None
            if all(part is None for part in items[key]):
                del items[key]
        copy = self._child_comment()
        if copy:
            copy[0] = None

    def _column(self) -> int:
        token = self._token()
        return token.column if token is not None else 0

    def eol(self) -> str:
        token = self._token()
        return _split(token.value)[0] if token is not None else ""

    def trailing(self) -> str:
        token = self._token()
        return _split(token.value)[1] if token is not None else ""

    def set_eol(self, eol: str, column: int) -> None:
        self._write(eol, self.trailing(), column if not self.eol() else self._column())

    def set_trailing(self, trailing: str) -> None:
        self._write(self.eol(), trailing, self._column())

    def take_trailing(self) -> str:
        trailing = self.trailing()
        if trailing:
            self.set_trailing("")
        return trailing

    def add_trailing(self, text: str) -> None:
        if not text:
            return
        current = self.trailing()
        if text.startswith("\n") and _ends_with_blank_line(current):
            text = text[1:]
        self.set_trailing(current + text)


class _HeaderSlot:
    """The comment block above the first key of the file."""

    __slots__ = ("_root",)

    def __init__(self, root: CommentedMap) -> None:
        self._root = root

    def add_trailing(self, text: str) -> None:
        comment = self._root.ca.comment
        if not comment or not comment[1]:
            text = text.lstrip("\n")  # no header: the file does not start with blank lines
        if not text:
            return
        if not comment:
            self._root.ca.comment = comment = [None, []]
        if comment[1] is None:
            comment[1] = []
        tokens: list[CommentToken] = comment[1]
        for line in text.splitlines(keepends=True):
            tokens.append(CommentToken(line, CommentMark(0), None))


def _last_slot(container: Any, key: Any) -> _Slot:
    """Slot of the last line of `container[key]` (its deepest last key for block collections)."""
    node = container[key]
    while _is_block(node) and len(node):
        container, key = node, _keys(node)[-1]
        node = container[key]
    return _Slot(container, key)


def _restyle(old: object, new: object) -> object:
    """Keep the quoting style of a replaced string."""
    if isinstance(old, ScalarString) and isinstance(new, str) and not isinstance(new, ScalarString):
        return type(old)(new)
    return new


def _to_node(value: object, *, block: bool = False) -> Any:
    """Plain python → ruamel node: flow collections; `block` makes the top mapping block style."""
    if value is None or isinstance(value, bool | ScalarString):
        return value
    if isinstance(value, str):
        return str(value)
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return float(value)
    if isinstance(value, Mapping):
        mapping = CommentedMap()
        for key, item in value.items():
            mapping[_to_node(key)] = _to_node(item)
        if block and mapping:
            mapping.fa.set_block_style()
        else:
            mapping.fa.set_flow_style()
        return mapping
    if isinstance(value, list | tuple):
        seq = CommentedSeq(_to_node(item) for item in value)
        seq.fa.set_flow_style()
        return seq
    raise TypeError(f"cannot store a {type(value).__name__} in the policy")


def _plain(node: object) -> Any:
    """ruamel node → independent plain python value."""
    if isinstance(node, Mapping):
        return {_plain(key): _plain(value) for key, value in node.items()}
    if isinstance(node, list | tuple):
        return [_plain(item) for item in node]
    if isinstance(node, bool | ScalarBoolean):
        return bool(node)
    if isinstance(node, ScalarString):
        return str(node)
    if isinstance(node, ScalarFloat):
        return float(node)
    if isinstance(node, ScalarInt):
        return int(node)
    return node


def _mapping_indent(root: CommentedMap) -> int:
    """Indentation of nested block mappings, measured on the first one in the file."""
    queue: deque[Any] = deque([root])
    while queue:
        node = queue.popleft()
        if isinstance(node, CommentedMap):
            for key, value in node.items():
                if isinstance(value, CommentedMap) and _is_block(value) and len(value):
                    first = next(iter(value))
                    step = int(value.lc.key(first)[1]) - int(node.lc.key(key)[1])
                    if step > 0:
                        return step
                if _is_container(value):
                    queue.append(value)
        elif isinstance(node, CommentedSeq):
            queue.extend(item for item in node if _is_container(item))
    return 2


def _new_yaml() -> YAML:
    yaml = YAML(typ="rt")
    yaml.preserve_quotes = True
    yaml.width = 4096
    return yaml


def _parse(path: Path, text: str) -> tuple[YAML, CommentedMap]:
    yaml = _new_yaml()
    try:
        try:
            root, seq_indent, seq_offset = load_yaml_guess_indent(text, yaml=yaml)
        except IndexError:  # its line scanner trips over lines made of dashes; YAML may be fine
            root, seq_indent, seq_offset = yaml.load(text), None, None
    except MarkedYAMLError as exc:
        mark = exc.problem_mark or exc.context_mark
        where = f" at line {mark.line + 1}:{mark.column + 1}" if mark is not None else ""
        problem = exc.problem or exc.context or "syntax error"
        raise DocumentError(f"Cannot open {path}: invalid YAML{where}: {problem}.") from exc
    except YAMLError as exc:
        raise DocumentError(f"Cannot open {path}: invalid YAML: {exc}.") from exc
    if not isinstance(root, CommentedMap):
        raise DocumentError(
            f"Cannot open {path}: a policy is a YAML mapping (`key: value` lines) at the top level."
        )
    mapping = _mapping_indent(root)
    if seq_indent is None or seq_offset is None:
        seq_indent, seq_offset = mapping + 2, mapping
    yaml.indent(mapping=mapping, sequence=seq_indent, offset=seq_offset)
    return yaml, root


def _read(path: Path) -> tuple[bytes, str, YAML, CommentedMap]:
    try:
        data = path.read_bytes()
    except FileNotFoundError as exc:
        raise DocumentError(f"Cannot open {path}: the file does not exist.") from exc
    except OSError as exc:
        raise DocumentError(f"Cannot open {path}: {exc.strerror or exc}.") from exc
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DocumentError(f"Cannot open {path}: not UTF-8 text (byte {exc.start}).") from exc
    yaml, root = _parse(path, text)
    return data, text, yaml, root


def _atomic_write(target: Path, data: bytes) -> None:
    """Temp file in the target's directory, fsync, original mode, then one rename."""
    try:
        mode = stat.S_IMODE(target.stat().st_mode)
    except FileNotFoundError:
        mode = _NEW_FILE_MODE
    fd, temp = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".tmp")
    replaced = False
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp, mode)
        os.replace(temp, target)
        replaced = True
    finally:
        if not replaced:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(temp)


class PolicyDocument:
    """One policy file opened for editing. Every mutation bumps `revision`; nothing touches the
    disk before `save()`."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._revision = 0
        self._render: tuple[int, str] | None = None
        self._validation: tuple[int, Mapping[str, type[BaseModel]], list[str]] | None = None
        self._disk_bytes, self._disk_text, self._yaml, self._root = _read(path)

    @classmethod
    def open(cls, path: Path) -> PolicyDocument:
        return cls(path)

    # ----------------------------------------------------------------- state

    @property
    def revision(self) -> int:
        return self._revision

    def render(self) -> str:
        if self._render is None or self._render[0] != self._revision:
            buffer = io.StringIO()
            self._yaml.dump(self._root, buffer)
            self._render = (self._revision, buffer.getvalue())
        return self._render[1]

    @property
    def dirty(self) -> bool:
        return self.render() != self._disk_text

    def diff(self) -> list[str]:
        name = self.path.name
        return list(
            difflib.unified_diff(
                self._disk_text.splitlines(),
                self.render().splitlines(),
                fromfile=f"{name} (on disk)",
                tofile=f"{name} (edited)",
                n=2,
                lineterm="",
            )
        )

    def validate(self, param_models: Mapping[str, type[BaseModel]]) -> list[str]:
        cached = self._validation
        if cached is not None and cached[0] == self._revision and cached[1] is param_models:
            return list(cached[2])
        try:
            parse_policy(self.render().encode("utf-8"), param_models)
            errors: list[str] = []
        except PolicyError as exc:
            errors = list(exc.errors)
        self._validation = (self._revision, param_models, errors)
        return list(errors)

    # ----------------------------------------------------------------- disk

    def save(self, *, force: bool = False) -> None:
        text = self.render()
        data = text.encode("utf-8")
        target = Path(os.path.realpath(self.path))
        if not force:
            try:
                on_disk: bytes | None = target.read_bytes()
            except FileNotFoundError:
                on_disk = None
            except OSError as exc:
                raise DocumentError(f"Cannot save {self.path}: {exc.strerror or exc}.") from exc
            if on_disk != self._disk_bytes:
                raise ConflictError(
                    f"{self.path} changed on disk since it was opened. "
                    "Reload it to drop your edits, or overwrite it with yours."
                )
        try:
            _atomic_write(target, data)
        except OSError as exc:
            raise DocumentError(f"Cannot save {self.path}: {exc.strerror or exc}.") from exc
        self._disk_bytes, self._disk_text = data, text

    def reload(self) -> None:
        self._disk_bytes, self._disk_text, self._yaml, self._root = _read(self.path)
        self._touch()

    # ----------------------------------------------------------------- reading

    def get(self, path: PathKey, default: Any = None) -> Any:
        found, node = self._find(path)
        return _plain(node) if found else default

    def names(self, section: str) -> list[str]:
        node = self._root.get(section)
        return [str(key) for key in node] if isinstance(node, CommentedMap) else []

    def users(self, section: str, name: str) -> list[str]:
        self._check_section(section)
        if section == "upstreams":
            refs = [(model, spec.get("upstream")) for model, spec in self._entries("models")]
            return [f"models.{model}" for model, ref in refs if ref == name]
        if section == "models":
            found = []
            for agent, spec in self._entries("agents"):
                allowed = spec.get("allowed_models")
                if isinstance(allowed, list) and name in allowed:
                    found.append(f"agents.{agent}")
            return found
        if section == "budgets":
            return [
                f"agents.{a}" for a, spec in self._entries("agents") if spec.get("budget") == name
            ]
        return []

    # ----------------------------------------------------------------- generic edits

    def set(self, path: PathKey, value: Any, order: Sequence[str] = ()) -> None:
        if not path:
            raise DocumentError("Choose a setting to change: the path is empty.")
        self._check_writable(path)
        node = _to_node(value, block=len(path) == 1)
        container = self._ensure_parents(path)
        self._assign(path[:-1], container, path[-1], value, node, order)
        self._touch()

    def unset(self, path: PathKey) -> None:
        if not path or not self._find(path)[0]:
            return
        self._remove(path)
        self._touch()

    def set_comment(self, path: PathKey, text: str | None) -> None:
        found, _ = self._find(path)
        if not path or not found:
            raise DocumentError(f"Cannot comment on {self._label(path)}: it does not exist.")
        if text is not None and ("\n" in text or "\r" in text):
            raise DocumentError("A comment must fit on one line.")
        container = self._find(path[:-1])[1]
        key = path[-1]
        item = container[key]
        if (
            isinstance(container, CommentedSeq)
            and isinstance(item, CommentedMap)
            and _is_block(item)
        ):
            if not item:
                raise DocumentError(f"Cannot comment on {self._label(path)}: it is empty.")
            container, key = item, next(iter(item))  # the `- key:` line of a block item
        body = (text or "").strip()
        if body.startswith("#"):
            body = body[1:].strip()
        slot = _Slot(container, key)
        slot.set_eol(f"# {body}" if body else "", self._comment_column(container))
        self._touch()

    # ----------------------------------------------------------------- named sections

    def add_entry(self, section: str, name: str, value: Mapping[str, Any]) -> None:
        self._check_section(section)
        self._check_new_name(section, name)
        node = _to_node(value, block=True)
        mapping = self._section_for_write(section)
        self._insert((section,), mapping, len(mapping), name, node)
        self._touch()

    def rename_entry(self, section: str, old: str, new: str) -> None:
        self._check_section(section)
        mapping = self._root.get(section)
        if not isinstance(mapping, CommentedMap) or old not in mapping:
            raise DocumentError(f"{self._kind(section)} '{old}' does not exist.")
        if new == old:
            return
        self._check_new_name(section, new)
        position = list(mapping).index(old)
        comments = mapping.ca.items.pop(old, None)
        value = mapping[old]
        del mapping[old]
        mapping.insert(position, new, value)
        if comments is not None:
            mapping.ca.items[new] = comments
        self._rename_references(section, old, new)
        self._touch()

    def delete_entry(self, section: str, name: str) -> None:
        self._check_section(section)
        if name not in self.names(section):
            raise DocumentError(f"{self._kind(section)} '{name}' does not exist.")
        users = self.users(section, name)
        if users:
            raise InUseError(
                f"{self._kind(section)} '{name}' is used by {', '.join(users)}. "
                "Change those first.",
                users,
            )
        self._remove((section, name))
        self._touch()

    # ----------------------------------------------------------------- controls

    def add_control(self, spec: Mapping[str, Any]) -> int:
        controls = self._root.get("controls")
        if controls is not None and not isinstance(controls, CommentedSeq):
            raise DocumentError("Cannot add a control: `controls` in the file is not a list.")
        control_id = spec.get("id")
        if controls is not None and control_id is not None:
            if any(isinstance(c, Mapping) and c.get("id") == control_id for c in controls):
                raise DocumentError(f"A control with id '{control_id}' already exists.")
        node = _to_node(spec, block=True)
        if controls is None:
            controls = CommentedSeq()
            controls.fa.set_block_style()
            if "controls" in self._root:
                self._root["controls"] = controls
            else:
                self._place_root("controls", controls)
        elif not controls:
            controls.fa.set_block_style()
        self._insert(("controls",), controls, len(controls), len(controls), node)
        self._touch()
        return len(controls) - 1

    def delete_control(self, index: int) -> None:
        self._control_count(index)
        self._remove(("controls", index))
        self._touch()

    def move_control(self, index: int, delta: int) -> int:
        count = self._control_count(index)
        target = min(max(index + delta, 0), count - 1)
        if target == index:
            return index
        controls: CommentedSeq = self._root["controls"]
        block = _is_block(controls)
        positions = [_last_slot(controls, i).take_trailing() for i in range(count)] if block else []
        item = controls[index]
        del controls[index]
        controls.insert(target, item)
        for i, trailing in enumerate(positions):
            _last_slot(controls, i).add_trailing(trailing)
        self._touch()
        return target

    # ----------------------------------------------------------------- internals

    def _touch(self) -> None:
        self._revision += 1

    def _find(self, path: PathKey) -> tuple[bool, Any]:
        node: Any = self._root
        for key in path:
            found, node = _child(node, key)
            if not found:
                return (False, None)
        return (True, node)

    @staticmethod
    def _label(path: PathKey) -> str:
        return ".".join(str(part) for part in path) or "the policy"

    @staticmethod
    def _kind(section: str) -> str:
        return section[:-1].capitalize()

    def _check_section(self, section: str) -> None:
        if section not in NAMED_SECTIONS:
            raise DocumentError(f"'{section}' is not one of {', '.join(NAMED_SECTIONS)}.")

    def _check_new_name(self, section: str, name: str) -> None:
        if not name.strip():
            raise DocumentError(f"{self._kind(section)} name must not be empty.")
        if name in self.names(section):
            raise DocumentError(
                f"{self._kind(section)} '{name}' already exists. Pick another name."
            )

    def _entries(self, section: str) -> list[tuple[str, CommentedMap]]:
        node = self._root.get(section)
        if not isinstance(node, CommentedMap):
            return []
        return [(str(key), spec) for key, spec in node.items() if isinstance(spec, CommentedMap)]

    def _rename_references(self, section: str, old: str, new: str) -> None:
        if section == "upstreams":
            for _, spec in self._entries("models"):
                if spec.get("upstream") == old:
                    spec["upstream"] = _restyle(spec["upstream"], new)
        elif section == "models":
            for _, spec in self._entries("agents"):
                allowed = spec.get("allowed_models")
                if isinstance(allowed, list):
                    for i, item in enumerate(allowed):
                        if item == old:
                            allowed[i] = _restyle(item, new)
        elif section == "budgets":
            for _, spec in self._entries("agents"):
                if spec.get("budget") == old:
                    spec["budget"] = _restyle(spec["budget"], new)

    def _control_count(self, index: int) -> int:
        controls = self._root.get("controls")
        count = len(controls) if isinstance(controls, CommentedSeq) else 0
        if not 0 <= index < count:
            raise DocumentError(f"There is no control number {index + 1} (the policy has {count}).")
        return count

    def _check_writable(self, path: PathKey) -> None:
        """Refuse paths that cannot be created before anything changes."""
        node: Any = self._root
        for depth, key in enumerate(path[:-1]):
            found, child = _child(node, key)
            if not found or child is None:
                if not isinstance(node, CommentedMap) or _is_index(path[depth + 1]):
                    raise DocumentError(f"Cannot create {self._label(path[: depth + 2])}.")
                node = CommentedMap()
                continue
            if not _is_container(child):
                raise DocumentError(
                    f"Cannot set {self._label(path)}: "
                    f"{self._label(path[: depth + 1])} is a value, not a section."
                )
            node = child
        key = path[-1]
        if isinstance(node, CommentedSeq) and (
            not _is_index(key) or not 0 <= int(key) <= len(node)
        ):
            raise DocumentError(f"Cannot set {self._label(path)}: no such list position.")

    def _ensure_parents(self, path: PathKey) -> Any:
        node: Any = self._root
        for depth, key in enumerate(path[:-1]):
            found, child = _child(node, key)
            if found and child is not None:
                node = child
                continue
            new = CommentedMap()
            if depth == 0:
                new.fa.set_block_style()  # a root section
            else:
                new.fa.set_flow_style()
            if found:
                node[key] = new
            elif depth == 0:
                self._place_root(str(key), new)
            else:
                self._insert(path[:depth], node, len(node), key, new)
            node = new
        return node

    def _section_for_write(self, section: str) -> CommentedMap:
        node = self._root.get(section)
        if section not in self._root:
            node = CommentedMap()
            node.fa.set_block_style()
            self._place_root(section, node)
        elif node is None:
            node = CommentedMap()
            node.fa.set_block_style()
            self._root[section] = node
        elif not isinstance(node, CommentedMap):
            raise DocumentError(
                f"Cannot add to `{section}`: in the file it is not a mapping of names."
            )
        elif not node:
            node.fa.set_block_style()
        return node

    def _place_root(self, key: str, node: Any) -> None:
        self._insert(
            (), self._root, self._ordered_position(self._root, key, _ROOT_ORDER), key, node
        )

    @staticmethod
    def _ordered_position(container: CommentedMap, key: Any, order: Sequence[str]) -> int:
        keys = list(container)
        if key in order:
            at = list(order).index(key)
            before = [keys.index(k) for k in order[:at] if k in container]
            if before:
                return max(before) + 1
            after = [keys.index(k) for k in order[at + 1 :] if k in container]
            if after:
                return min(after)
        return len(keys)

    def _assign(
        self,
        parent: PathKey,
        container: Any,
        key: str | int,
        value: Any,
        node: Any,
        order: Sequence[str],
    ) -> None:
        found, old = _child(container, key)
        if not found:
            if isinstance(container, CommentedSeq):
                self._insert(parent, container, len(container), len(container), node)
            else:
                self._insert(
                    parent, container, self._ordered_position(container, key, order), key, node
                )
            return
        path = (*parent, key)
        if isinstance(old, CommentedMap) and isinstance(value, Mapping):
            for stale in [k for k in old if k not in value]:
                self._remove((*path, stale))
            for sub_key, sub_value in value.items():
                self._assign(path, old, sub_key, sub_value, _to_node(sub_value), list(value))
            return
        if isinstance(old, CommentedSeq) and isinstance(value, list | tuple):
            while len(old) > len(value):
                self._remove((*path, len(old) - 1))
            for i, item in enumerate(value):
                self._assign(path, old, i, item, _to_node(item), ())
            return
        trailing = _last_slot(container, key).take_trailing() if _is_block(container) else ""
        container[key] = _restyle(old, node)
        if trailing:
            _last_slot(container, key).add_trailing(trailing)

    def _insert(self, parent: PathKey, container: Any, pos: int, key: Any, node: Any) -> None:
        """Insert at `pos`; the lines that followed the node before `pos` now follow the new one."""
        keys = _keys(container)
        if not _is_block(container):
            self._raw_insert(container, pos, key, node)
            return
        if pos > 0:
            before: _Slot | None = _last_slot(container, keys[pos - 1])
        elif not keys and parent:
            before = _last_slot(self._find(parent[:-1])[1], parent[-1])
        else:
            before = None
        moved = before.take_trailing() if before is not None else ""
        self._raw_insert(container, pos, key, node)
        new_key = key if isinstance(container, CommentedMap) else pos
        after = _last_slot(container, new_key)
        after.add_trailing(moved)
        if container is self._root:  # root sections stay separated by a blank line
            if pos > 0 and not _last_slot(container, keys[pos - 1]).trailing():
                _last_slot(container, keys[pos - 1]).set_trailing("\n")
            if pos < len(keys) and not after.trailing().startswith("\n"):
                after.set_trailing("\n" + after.trailing())

    @staticmethod
    def _raw_insert(container: Any, pos: int, key: Any, node: Any) -> None:
        if isinstance(container, CommentedMap):
            container.insert(pos, key, node)
        else:
            container.insert(pos, node)

    def _remove(self, path: PathKey) -> None:
        """Delete the node at `path`; the lines that followed it now follow the node before it."""
        container = self._find(path[:-1])[1]
        key = path[-1]
        if _is_block(container):
            moved = _last_slot(container, key).take_trailing()
            target = self._before_slot(path)
        else:
            moved, target = "", None
        if isinstance(container, CommentedMap):
            container.ca.items.pop(key, None)
        del container[key]
        if not container and container is not self._root:
            container.fa.set_flow_style()  # an empty block collection renders broken; `{}`/`[]`
        if target is not None:
            target.add_trailing(moved)

    def _before_slot(self, path: PathKey) -> _Slot | _HeaderSlot:
        """Where the lines just above the node at `path` live."""
        container = self._find(path[:-1])[1]
        keys = _keys(container)
        pos = keys.index(path[-1])
        if pos > 0:
            return _last_slot(container, keys[pos - 1])
        if len(path) == 1:
            return _HeaderSlot(self._root)
        grandparent = self._find(path[:-2])[1]
        if isinstance(grandparent, CommentedMap):
            return _Slot(grandparent, path[-2])
        return self._before_slot(path[:-1])

    @staticmethod
    def _comment_column(container: Any) -> int:
        """Column of the sibling comments, so a new comment lines up with them."""
        index = 0 if isinstance(container, CommentedSeq) else 2
        for entry in container.ca.items.values():
            token = entry[index] if len(entry) > index else None
            if isinstance(token, CommentToken) and token.value.lstrip(" ").startswith("#"):
                return int(token.column)
        return 0
