"""One list row per policy field: shows the value and opens the editor that fits the field's type.

bool toggles, short choices cycle (pi's SettingsList), longer choices and references open a
select list, numbers and text open an input line, multi-choice fields a ✓ list, free string lists
and string maps their own list. Every value goes through `schema.check` before it is written, so
the input line can show the field's own error; policy-wide problems surface through Session.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from functools import partial
from typing import Any

from control_layer.egida.document import PathKey
from control_layer.egida.schema import FieldSpec, check, parse_input
from control_layer.egida.session import Session
from control_layer.egida.widgets import (
    InputView,
    ListView,
    MultiSelectView,
    Option,
    Row,
    RowTone,
    SelectView,
)

__all__ = ["field_row", "format_value", "string_list_view", "string_map_view"]

_MISSING: Any = object()
_CYCLE_LIMIT = 3  # pi cycles short value lists in place; longer ones open a select list
_DEFAULT = "default"


def format_value(value: Any) -> str:
    """Compact one-line text of a plain policy value."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return format(value, "g")
    if isinstance(value, list | tuple):
        return ", ".join(format_value(v) for v in value) or "none"
    if isinstance(value, dict):
        return ", ".join(f"{k}={format_value(v)}" for k, v in value.items()) or "none"
    if value is None:
        return "none"
    return str(value)


def field_row(
    session: Session,
    path: PathKey,
    spec: FieldSpec,
    *,
    label: str | None = None,
    help_text: str = "",
    order: Sequence[str] = (),
    choices: Sequence[str] | None = None,
    inherited: str | None = None,
) -> Row:
    """Row for the field at `path`. `choices` restricts text/list fields to names (references
    such as budgets or models); `inherited` is what an unset optional field falls back to."""
    title = label or spec.name
    value = session.doc.get(path, _MISSING)
    current = None if value is _MISSING else value
    shown, tone = _shown(spec, current, inherited)
    edit = _editor(session, path, spec, title, help_text, order, choices, current)
    return Row(
        label=title,
        value=shown,
        help=help_text,
        action=edit,
        tone=tone,
        id=".".join(map(str, path)),
    )


def _shown(spec: FieldSpec, current: Any, inherited: str | None) -> tuple[str, RowTone]:
    if current is not None:
        return format_value(current), "normal"
    if spec.optional:
        return (f"{_DEFAULT} ({inherited})" if inherited else _DEFAULT), "normal"
    if spec.required:
        return "missing", "error"
    return f"{format_value(spec.default)} ({_DEFAULT})", "normal"


def _editor(
    session: Session,
    path: PathKey,
    spec: FieldSpec,
    title: str,
    help_text: str,
    order: Sequence[str],
    choices: Sequence[str] | None,
    current: Any,
) -> Callable[[], None]:
    def commit(value: Any) -> None:
        checked = check(spec, value)  # ValueError reaches the input line that called us
        session.change(lambda doc: doc.set(path, checked, order))

    def commit_or_notify(value: Any) -> None:
        try:
            commit(value)
        except ValueError as exc:
            session.ui.notify("error", f"{title}: not changed", str(exc))

    def unset() -> None:
        session.change(lambda doc: doc.unset(path))

    effective = current if current is not None else spec.default
    options = tuple(choices) if choices is not None else spec.choices

    if spec.kind == "bool":
        return lambda: commit_or_notify(not bool(effective))

    if spec.kind == "choice" or (spec.kind == "text" and choices is not None):
        return _choice_editor(
            session, spec, title, help_text, options, choices, current, unset, commit_or_notify
        )

    if spec.kind == "multi" or (spec.kind == "list" and options):
        selected = [str(v) for v in current or []]
        names = list(options) + [v for v in selected if v not in options]

        def open_multi() -> None:
            session.ui.push(
                MultiSelectView(
                    title,
                    help_text,
                    [Option(v, v) for v in names],
                    selected,
                    commit_or_notify,
                    min_selected=_min_items(spec),
                )
            )

        return open_multi

    if spec.kind == "list":
        return lambda: session.ui.push(
            string_list_view(session, path, spec, title=title, help_text=help_text, order=order)
        )

    if spec.kind == "map":
        return lambda: session.ui.push(
            string_map_view(session, path, spec, title=title, help_text=help_text, order=order)
        )

    # int, float, text, raw: one input line
    initial = "" if current is None else format_value(current)
    placeholder = f"empty = {_DEFAULT}" if spec.optional else ""

    def submit(text: str) -> None:
        if spec.optional and not text.strip():
            unset()
            return
        commit(parse_input(spec, text))

    return lambda: session.ui.push(
        InputView(title, help_text, initial, submit, placeholder=placeholder)
    )


def _choice_editor(
    session: Session,
    spec: FieldSpec,
    title: str,
    help_text: str,
    options: Sequence[str],
    choices: Sequence[str] | None,
    current: Any,
    unset: Callable[[], None],
    commit_or_notify: Callable[[Any], None],
) -> Callable[[], None]:
    values = ([_DEFAULT] if spec.optional else []) + [str(v) for v in options]
    if current is not None:
        selected = str(current)
    else:
        selected = _DEFAULT if spec.optional else str(spec.default)

    def pick(value: str) -> None:
        if value == _DEFAULT:
            unset()
        else:
            commit_or_notify(value)

    if choices is None and len(values) <= _CYCLE_LIMIT:
        position = values.index(selected) if selected in values else -1
        following = values[(position + 1) % len(values)]
        return lambda: pick(following)

    def open_select() -> None:
        session.ui.push(
            SelectView(
                title,
                help_text,
                [Option(v, v) for v in values],
                selected if selected in values else None,
                pick,
            )
        )

    return open_select


def _min_items(spec: FieldSpec) -> int:
    try:
        check(spec, [])
    except ValueError:
        return 1
    return 0


def string_list_view(
    session: Session,
    path: PathKey,
    spec: FieldSpec,
    *,
    title: str,
    help_text: str,
    order: Sequence[str] = (),
) -> ListView:
    """Free list of strings: Enter edits an entry (empty removes it), "Add" appends, Del removes."""

    def items() -> list[str]:
        return [str(v) for v in session.doc.get(path, None) or []]

    def write(values: list[str]) -> None:
        checked = check(spec, values)
        session.change(lambda doc: doc.set(path, checked, order))

    def edit(index: int) -> None:
        def submit(text: str) -> None:
            values = items()
            if text.strip():
                values[index] = text.strip()
            else:
                del values[index]
            write(values)

        session.ui.push(InputView(title, "Empty removes the entry.", items()[index], submit))

    def add() -> None:
        def submit(text: str) -> None:
            if not text.strip():
                raise ValueError("Enter a value.")
            write([*items(), text.strip()])

        session.ui.push(InputView(f"Add to {title}", help_text, "", submit))

    def remove(row: Row) -> None:
        if not row.id.startswith("item:"):
            return
        values = items()
        del values[int(row.id.removeprefix("item:"))]
        try:
            write(values)
        except ValueError as exc:
            session.ui.notify("error", f"{title}: not changed", str(exc))

    def rows() -> list[Row]:
        listed = [
            Row(label=value, action=partial(edit, i), id=f"item:{i}")
            for i, value in enumerate(items())
        ]
        return [*listed, Row(label="Add", help=help_text, action=add, tone="add", id="add")]

    return ListView(
        title,
        rows,
        subtitle=help_text,
        hint="Enter to edit · Del to remove · Esc to go back",
        keys={"delete": remove, "backspace": remove},
    )


def string_map_view(
    session: Session,
    path: PathKey,
    spec: FieldSpec,
    *,
    title: str,
    help_text: str,
    order: Sequence[str] = (),
) -> ListView:
    """Name → text entries (e.g. extra regex patterns by label): Enter edits the text, "Add"
    asks for a name and then the text, Del removes."""

    def entries() -> dict[str, str]:
        raw: Mapping[str, Any] = session.doc.get(path, None) or {}
        return {str(k): str(v) for k, v in raw.items()}

    def write(values: dict[str, str]) -> None:
        checked = check(spec, values)
        session.change(lambda doc: doc.set(path, checked, order))

    def edit(name: str) -> None:
        def submit(text: str) -> None:
            write(entries() | {name: text})

        session.ui.push(InputView(f"{title} · {name}", help_text, entries()[name], submit))

    def add() -> None:
        def named(name: str) -> None:
            name = name.strip()
            if not name:
                raise ValueError("Enter a name.")
            if name in entries():
                raise ValueError(f"{name!r} already exists.")

            def valued(text: str) -> None:
                write(entries() | {name: text})

            session.ui.push(InputView(f"{title} · {name}", help_text, "", valued))

        session.ui.push(InputView(f"Add to {title}", "Name of the new entry.", "", named))

    def remove(row: Row) -> None:
        if not row.id.startswith("key:"):
            return
        values = entries()
        values.pop(row.id.removeprefix("key:"), None)
        try:
            write(values)
        except ValueError as exc:
            session.ui.notify("error", f"{title}: not changed", str(exc))

    def rows() -> list[Row]:
        listed = [
            Row(label=name, value=text, action=partial(edit, name), id=f"key:{name}")
            for name, text in entries().items()
        ]
        return [*listed, Row(label="Add", help=help_text, action=add, tone="add", id="add")]

    return ListView(
        title,
        rows,
        subtitle=help_text,
        hint="Enter to edit · Del to remove · Esc to go back",
        keys={"delete": remove, "backspace": remove},
    )
