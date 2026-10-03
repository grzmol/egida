"""Controls screens: the ordered control list and one control's settings and params."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from functools import partial
from typing import Any, Final

from control_layer.core.policy import ControlSpec
from control_layer.egida.document import PolicyDocument
from control_layer.egida.fields import field_row, format_value
from control_layer.egida.schema import HELP, feed_rules, fields, help_for
from control_layer.egida.session import Session
from control_layer.egida.widgets import (
    Choice,
    ConfirmView,
    InputView,
    ListView,
    Option,
    Row,
    RowTone,
    SelectView,
    View,
)

__all__ = ["controls_summary", "controls_view"]

KIND_HELP: Final[Mapping[str, str]] = {
    "signature": "Known-attack rules from the signature feed (hot reloaded); "
    "threshold filters by rule severity.",
    "pii": "Personal data (EN/PL): e-mail, phone, PESEL, NIP, IBAN, card; numbers need a valid "
    "checksum.",
    "secrets": "Credentials: cloud and API keys, private keys, JWTs, connection strings, "
    "high-entropy tokens.",
    "injection_heuristics": "Prompt-injection phrase rules (EN/PL) on normalized text, also "
    "base64 and ROT13.",
    "canary": "Blocks an answer that leaks the canary token the proxy puts in the system prompt.",
    "egress": "Exfiltration through URLs in the answer or tool arguments to hosts outside the "
    "allowlist.",
    "prompt_guard": "Llama Prompt Guard 2 classifier (ONNX, local) for jailbreaks and injections.",
    "harmful_content": "Llama Guard 3 via Ollama: violence, weapons, self-harm, hate and other "
    "harmful content.",
}
_ID_PATTERN: Final = re.compile(r"^[a-z][a-z0-9_.-]*$")
_ORDER: Final = tuple(ControlSpec.model_fields)
_OUTPUT_KINDS: Final = frozenset({"canary", "egress"})
_PLAIN_FIELDS: Final = (
    "enabled",
    "sides",
    "action",
    "threshold",
    "on_error",
    "timeout_ms",
)
_SUBTITLE: Final = (
    "Controls run top to bottom; cheap ones first. A control that is not listed does not run."
)


def _controls(doc: PolicyDocument) -> list[dict[str, Any]]:
    raw = doc.get(("controls",), None)
    if not isinstance(raw, list):
        return []
    return [c if isinstance(c, dict) else {} for c in raw]


def _ids(doc: PolicyDocument) -> list[str]:
    return [str(c.get("id", "")) for c in _controls(doc)]


def _kind_help(kind: str) -> str:
    known = KIND_HELP.get(kind)
    return f"{kind}: {known}" if known else f"{kind}: no detector of this kind is registered."


def controls_summary(session: Session) -> str:
    controls = _controls(session.doc)
    if not controls:
        return "none"
    on = sum(1 for c in controls if c.get("enabled", True) is not False)
    return f"{len(controls)} · {on} on"


def _summary(control: Mapping[str, Any]) -> str:
    if control.get("enabled", True) is False:
        return "off"
    sides = control.get("sides") or []
    side_text = "+".join(map(str, sides)) if isinstance(sides, list) else str(sides)
    threshold = format_value(control.get("threshold", 0.5))
    return f"{control.get('action', '?')} · {side_text} · ≥{threshold}"


def _check_id(doc: PolicyDocument, text: str, keep: str | None = None) -> str:
    value = text.strip()
    if not _ID_PATTERN.match(value):
        raise ValueError("Use lowercase letters, digits, '_', '.', '-'; start with a letter.")
    if value != keep and value in _ids(doc):
        raise ValueError(f"A control with id {value!r} already exists.")
    return value


def _free_id(doc: PolicyDocument, kind: str) -> str:
    taken = set(_ids(doc))
    if kind not in taken:
        return kind
    n = 2
    while f"{kind}-{n}" in taken:
        n += 1
    return f"{kind}-{n}"


def _confirm_delete(session: Session, control_id: str, after: Callable[[], None]) -> None:
    def delete() -> None:
        ids = _ids(session.doc)
        if control_id not in ids:
            return
        index = ids.index(control_id)
        if session.change(lambda doc: doc.delete_control(index)):
            after()

    session.ui.push(
        ConfirmView(
            f"Delete control {control_id}?",
            "The control stops running once the policy is saved.",
            [
                Choice("Delete control", delete, tone="danger"),
                Choice("Cancel", lambda: None),
            ],
        )
    )


def _move(session: Session, control_id: str, delta: int) -> None:
    ids = _ids(session.doc)
    if control_id in ids:
        index = ids.index(control_id)
        session.change(lambda doc: doc.move_control(index, delta))


def controls_view(session: Session) -> View:
    """Ordered control list: Enter opens a control, alt/shift+↑↓ move, Del deletes."""

    def rows() -> list[Row]:
        listed: list[Row] = []
        for control in _controls(session.doc):
            cid = str(control.get("id", ""))
            kind = str(control.get("kind", ""))
            known = kind in session.param_models
            off = control.get("enabled", True) is False
            tone: RowTone = "error" if not known else "muted" if off else "normal"
            listed.append(
                Row(
                    label=cid,
                    value=_summary(control) if known else f"unknown kind {kind!r}",
                    help=_kind_help(kind),
                    action=partial(_open, cid),
                    tone=tone,
                    id=f"control:{cid}",
                )
            )
        add_help = (
            "Add a detector to the policy."
            if listed
            else "No controls: every request passes unchecked. Add a detector to start."
        )
        return [*listed, Row(label="Add control", help=add_help, action=add, tone="add", id="add")]

    def _open(control_id: str) -> None:
        session.ui.push(control_view(session, control_id))

    def move(delta: int, row: Row) -> None:
        if row.id.startswith("control:"):
            _move(session, row.id.removeprefix("control:"), delta)
            view.select(row.id)

    def delete(row: Row) -> None:
        if row.id.startswith("control:"):
            _confirm_delete(session, row.id.removeprefix("control:"), lambda: None)

    def add() -> None:
        def kind_chosen(kind: str) -> None:
            def submit(text: str) -> None:
                cid = _check_id(session.doc, text)
                side = "output" if kind in _OUTPUT_KINDS else "input"
                spec = {
                    "id": cid,
                    "kind": kind,
                    "sides": [side],
                    "action": "block",
                    "threshold": 0.5,
                }
                if session.change(lambda doc: doc.add_control(spec)):
                    view.select(f"control:{cid}")
                    _open(cid)

            session.ui.push(
                InputView(
                    "Control id",
                    "Unique name used in the audit log and in blocked_by.",
                    _free_id(session.doc, kind),
                    submit,
                )
            )

        options = [Option(k, k, KIND_HELP.get(k, "")) for k in sorted(session.param_models)]
        session.ui.push(
            SelectView("Add control", "Pick the detector kind.", options, None, kind_chosen)
        )

    keys: dict[str, Callable[[Row], None]] = {
        "alt+up": partial(move, -1),
        "shift+up": partial(move, -1),
        "alt+down": partial(move, 1),
        "shift+down": partial(move, 1),
        "delete": delete,
        "backspace": delete,
    }
    view = ListView(
        "Controls",
        rows,
        subtitle=_SUBTITLE,
        hint="Enter to open · alt+↑↓ move · Del to delete · Esc to go back",
        keys=keys,
    )
    return view


def control_view(session: Session, control_id: str) -> ListView:
    """One control, tracked by id; renaming through the id row keeps following it."""
    tracked = [control_id]
    specs = {spec.name: spec for spec in fields(ControlSpec)}

    def index() -> int | None:
        ids = _ids(session.doc)
        return ids.index(tracked[0]) if tracked[0] in ids else None

    def edit_id(i: int) -> None:
        def submit(text: str) -> None:
            new = _check_id(session.doc, text, keep=tracked[0])
            if session.change(lambda doc: doc.set(("controls", i, "id"), new, _ORDER)):
                tracked[0] = new

        session.ui.push(InputView("Control id", HELP.get("controls.id", ""), tracked[0], submit))

    def edit_kind(i: int, kind: str, has_params: bool) -> None:
        def write(new: str) -> None:
            def mutate(doc: PolicyDocument) -> None:
                doc.set(("controls", i, "kind"), new, _ORDER)
                doc.unset(("controls", i, "params"))

            session.change(mutate)

        def chosen(new: str) -> None:
            if new == kind:
                return
            if not has_params:
                write(new)
                return
            session.ui.push(
                ConfirmView(
                    "Changing the kind removes its params",
                    f"Params of {kind} do not fit {new}; the new kind starts with its defaults.",
                    [
                        Choice(f"Change to {new}", partial(write, new), tone="danger"),
                        Choice("Cancel", lambda: None),
                    ],
                )
            )

        options = [Option(k, k, KIND_HELP.get(k, "")) for k in sorted(session.param_models)]
        session.ui.push(SelectView("Kind", HELP.get("controls.kind", ""), options, kind, chosen))

    def rows() -> list[Row]:
        i = index()
        if i is None:
            return [Row(label="This control no longer exists", tone="error", id="gone")]
        control = _controls(session.doc)[i]
        kind = str(control.get("kind", ""))
        has_params = "params" in control
        base = ("controls", i)
        result = [
            Row(
                label="id",
                value=tracked[0],
                help=HELP.get("controls.id", ""),
                action=partial(edit_id, i),
                id="id",
            ),
            Row(
                label="kind",
                value=kind,
                help=_kind_help(kind),
                action=partial(edit_kind, i, kind, has_params),
                tone="normal" if kind in session.param_models else "error",
                id="kind",
            ),
        ]
        inherited = {
            "on_error": format_value(session.doc.get(("defaults", "on_error"), None)),
            "timeout_ms": format_value(session.doc.get(("defaults", "timeout_ms"), None)),
        }
        for name in _PLAIN_FIELDS:
            spec = specs[name]
            result.append(
                field_row(
                    session,
                    (*base, name),
                    spec,
                    help_text=help_for("controls", spec),
                    order=_ORDER,
                    inherited=inherited.get(name),
                )
            )
        result += _param_rows(session, base, kind)
        result += [
            Row(label="Move up", action=lambda: _move(session, tracked[0], -1), id="up"),
            Row(label="Move down", action=lambda: _move(session, tracked[0], 1), id="down"),
            Row(
                label="Delete control…",
                help="Remove this control from the policy.",
                action=lambda: _confirm_delete(session, tracked[0], session.ui.pop),
                tone="danger",
                id="delete",
            ),
        ]
        return result

    def subtitle() -> str:
        i = index()
        return "" if i is None else _kind_help(str(session.doc.get(("controls", i, "kind"), "")))

    return ListView(lambda: f"Control {tracked[0]}", rows, subtitle=subtitle)


def _param_rows(session: Session, base: tuple[str, int], kind: str) -> list[Row]:
    model = session.param_models.get(kind)
    if model is None:
        return [
            Row(
                label="params",
                value="cannot be checked",
                help=f"No detector of kind {kind!r} is registered; pick a known kind to edit its "
                "params.",
                tone="error",
                id="params",
            )
        ]
    order = tuple(model.model_fields)
    rows: list[Row] = []
    for spec in fields(model):
        choices = None
        if kind == "signature" and spec.name == "disabled_rules":
            rules = [rule_id for rule_id, _ in feed_rules(session.profile.feed)]
            choices = rules or None
        rows.append(
            field_row(
                session,
                (*base, "params", spec.name),
                spec,
                label=f"params.{spec.name}",
                help_text=help_for("params", spec),
                order=order,
                choices=choices,
            )
        )
    return rows
