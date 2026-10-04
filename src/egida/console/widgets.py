"""pi's TUI components for Egida: the app frame, settings list, select/multi-select submenus,
text input, confirmation, scrollable text, result boxes, key hints and diffs.

Views render into a width and height they are given and never exceed either; the App stacks
them (the top one gets the keys) and draws pi's frame around the top one.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal, Protocol

from egida.console.keys import Key
from egida.console.theme import (
    Style,
    Token,
    char_width,
    clip,
    logo_lines,
    pad,
    supports_logo,
    truncate,
    visible_width,
    wrap,
)

if TYPE_CHECKING:
    from egida.console.term import Terminal

__all__ = [
    "App",
    "Choice",
    "ConfirmView",
    "Header",
    "InputView",
    "ListView",
    "MultiSelectView",
    "Option",
    "Row",
    "RowTone",
    "SelectView",
    "TextView",
    "Tone",
    "View",
    "box",
    "diff_lines",
    "key_hints",
]

Tone = Literal["success", "error", "info"]
RowTone = Literal["normal", "add", "danger", "muted", "error", "warning", "success"]

MIN_WIDTH: Final = 50
MIN_HEIGHT: Final = 16
_LABEL_COLUMN: Final = 36  # pi SettingsList
_PRIMARY_MIN: Final = 12  # pi SelectSubmenu column bounds
_PRIMARY_MAX: Final = 32
_SUBMENU_ROWS: Final = 10
_MIN_DESCRIPTION: Final = 10
_MIN_VIEW_ROWS: Final = 3
_TICK_SECONDS: Final = 0.25
_BOX_BG: Final[Mapping[Tone, Token]] = {
    "success": "success_bg",
    "error": "error_bg",
    "info": "pending_bg",
}
_VALUE_TONES: Final[Mapping[RowTone, Token]] = {
    "error": "error",
    "warning": "warning",
    "success": "success",
}


class View(Protocol):
    def render(self, app: App, width: int, height: int) -> list[str]: ...

    def handle(self, app: App, key: Key) -> None: ...


@dataclass(frozen=True, slots=True)
class Header:
    name: str
    version: str
    tagline: str
    hints: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class Row:
    label: str
    value: str = ""
    help: str = ""
    action: Callable[[], None] | None = None  # Enter or Space
    tone: RowTone = "normal"
    id: str = ""  # selection follows id (else label) when rows are recomputed


@dataclass(frozen=True, slots=True)
class Option:
    value: str
    label: str
    description: str = ""


@dataclass(frozen=True, slots=True)
class Choice:
    label: str
    action: Callable[[], None]
    description: str = ""
    tone: RowTone = "normal"


# ── shared rendering ─────────────────────────────────────────────────────────


def key_hints(style: Style, hints: Sequence[tuple[str, str]]) -> str:
    """pi's footer hints: dim key, muted description, muted ` · ` between pairs."""
    separator = style.fg("muted", " · ")
    return separator.join(
        style.fg("dim", key) + style.fg("muted", " " + desc) for key, desc in hints
    )


def box(style: Style, tone: Tone, title: str, body: Sequence[str], width: int) -> list[str]:
    """pi's tool result box: full-width rows on the tone's background, 1 column and 1 row of
    padding, bold title, muted body (plain text, wrapped)."""
    inner = max(1, width - 2)
    content = [style.bold(truncate(title, inner))]
    for text in body:
        content += [style.fg("muted", line) for line in wrap(text, inner) or [""]]
    rows = ["", *content, ""]
    return [style.bg(_BOX_BG[tone], pad(" " + row, width)) for row in rows]


def diff_lines(style: Style, lines: Sequence[str]) -> list[str]:
    """Unified diff lines coloured like pi: additions success, removals error, headers dim."""
    out: list[str] = []
    for line in lines:
        if line.startswith(("+++", "---", "@@")):
            out.append(style.fg("dim", line))
        elif line.startswith("+"):
            out.append(style.fg("success", line))
        elif line.startswith("-"):
            out.append(style.fg("error", line))
        else:
            out.append(style.fg("muted", line))
    return out


def _resolve(text: str | Callable[[], str]) -> str:
    return text() if callable(text) else text


def _paint(style: Style, token: Token | None, text: str) -> str:
    return text if token is None else style.fg(token, text)


def _title(style: Style, title: str, width: int) -> str:
    return style.bold(style.fg("accent", truncate(title, width)))


def _muted_block(style: Style, text: str, width: int) -> list[str]:
    return [style.fg("muted", line) for line in wrap(text, width)]


def _hint_tail(style: Style, hint: str, width: int) -> list[str]:
    return ["", style.fg("dim", truncate("  " + hint, width))]


def _head(style: Style, title: str, description: str, width: int) -> list[str]:
    """Title, then the description after a blank line (pi submenu), then a blank line."""
    lines = [_title(style, title, width)]
    described = _muted_block(style, description, width)
    if described:
        lines += ["", *described]
    return [*lines, ""]


def _window(index: int, count: int, visible: int) -> tuple[int, int]:
    """pi's visible range: the selection centred, clamped to the list."""
    start = max(0, min(index - visible // 2, count - visible))
    return start, min(start + visible, count)


def _layout(
    count: int, extra: list[str], room: int, max_rows: int | None = None
) -> tuple[int, list[str], bool]:
    """How many of `count` list rows fit in `room` lines next to `extra` (help, messages), which
    of `extra` survives, and whether a scroll indicator is needed. Rows win over `extra`."""
    limit = count if max_rows is None else min(count, max_rows)
    if limit == count and count + len(extra) <= room:
        return count, extra, False
    keep = extra if room - len(extra) - 1 >= min(count, _MIN_VIEW_ROWS) else []
    if limit == count and count + len(keep) <= room:
        return count, keep, False
    visible = max(1, min(limit, room - len(keep) - 1))
    return visible, keep, visible < count


def _fit(body: list[str], tail: list[str], height: int) -> list[str]:
    """`body` + `tail` cut to `height` lines; the tail (hint) is kept whole when possible."""
    if len(body) + len(tail) <= height:
        return body + tail
    return (body[: max(0, height - len(tail))] + tail)[: max(0, height)]


def _scroll_info(style: Style, index: int, count: int) -> str:
    return style.fg("dim", f"  ({index + 1}/{count})")


def _single_line(text: str) -> str:
    return " ".join(text.split())


def _cancel(key: Key) -> bool:
    return key.name in ("escape", "ctrl+c")


def _space(key: Key) -> bool:
    return key.name == "char" and key.text == " "


def _move(index: int, count: int, key: Key, page: int) -> int | None:
    """New index for a navigation key (up/down wrap like pi); None if `key` doesn't navigate."""
    if count == 0:
        return None
    match key.name:
        case "up":
            return count - 1 if index == 0 else index - 1
        case "down":
            return 0 if index == count - 1 else index + 1
        case "pageup":
            return max(0, index - page)
        case "pagedown":
            return min(count - 1, index + page)
        case "home":
            return 0
        case "end":
            return count - 1
    return None


def _option_line(
    style: Style,
    lead: int,
    label: str,
    description: str,
    width: int,
    column: int,
    *,
    selected: bool,
    label_token: Token | None = None,
) -> str:
    """One row of pi's SelectList after a `lead` columns wide prefix (cursor, check mark):
    label column, then the description when there is room."""
    description = _single_line(description)
    if description and width > 40:
        primary = max(1, min(column, width - lead - 4))
        shown = truncate(label, max(1, primary - 2))
        spacing = " " * max(1, primary - visible_width(shown))
        remaining = width - lead - visible_width(shown) - len(spacing) - 2
        if remaining > _MIN_DESCRIPTION:
            desc = truncate(description, remaining)
            if selected:
                return _paint(style, label_token or "accent", shown) + style.fg(
                    "accent", spacing + desc
                )
            return _paint(style, label_token, shown) + style.fg("muted", spacing + desc)
    shown = truncate(label, max(1, width - lead - 2))
    return _paint(style, label_token or ("accent" if selected else None), shown)


def _primary_column(labels: Sequence[str]) -> int:
    widest = max((visible_width(label) + 2 for label in labels), default=0)
    return max(_PRIMARY_MIN, min(widest, _PRIMARY_MAX))


def _cursor(style: Style, selected: bool) -> str:
    return style.fg("accent", "→ ") if selected else "  "


# ── App ──────────────────────────────────────────────────────────────────────


class App:
    """pi's frame (header, borders, result box, footer) around a stack of views."""

    def __init__(
        self,
        root: View,
        *,
        style: Style,
        header: Header,
        footer: Callable[[int], list[str]],
    ) -> None:
        self.style = style
        self.header = header
        self.shortcuts: dict[str, Callable[[], None]] = {}
        self.ticks: list[Callable[[], None]] = []
        self.running = True
        self._footer = footer
        self._stack: list[View] = [root]
        self._notice: tuple[Tone, str, list[str]] | None = None
        self._logo = logo_lines(style) if supports_logo() else None

    @property
    def top(self) -> View:
        return self._stack[-1]

    def push(self, view: View) -> None:
        self._stack.append(view)

    def pop(self) -> None:
        if len(self._stack) > 1:
            self._stack.pop()

    def remove(self, view: View) -> None:
        self._stack = [self._stack[0]] + [v for v in self._stack[1:] if v is not view]

    def reset(self, root: View) -> None:
        self._stack = [root]

    def notify(self, tone: Tone, title: str, body: str | Sequence[str] = ()) -> None:
        lines = ([body] if body else []) if isinstance(body, str) else list(body)
        self._notice = (tone, title, lines)

    def quit(self) -> None:
        self.running = False

    def render(self, width: int, height: int) -> list[str]:
        if height <= 0:
            return []
        if width < MIN_WIDTH or height < MIN_HEIGHT:
            message = f"Terminal too small: {width}×{height}, Egida needs {MIN_WIDTH}×{MIN_HEIGHT}"
            return [truncate(message, max(width, 0))] + [""] * (height - 1)
        style = self.style
        border = style.fg("border", "─" * width)
        lines = ["", *self._header_lines(), "", border]
        foot = [" " + clip(line, width - 2) for line in self._footer(width - 2)]
        room = height - len(lines) - 1 - len(foot)  # 1 = border under the view
        notice = self._notice_lines(width, room - _MIN_VIEW_ROWS)
        view_height = max(1, room - len(notice))
        view_lines = self.top.render(self, width - 2, view_height)[:view_height]
        lines += [" " + line if line else line for line in view_lines]
        lines += [border, *notice]
        body = lines[: max(0, height - len(foot))]
        out = body + [""] * (height - len(body) - len(foot)) + foot
        return [clip(line, width) for line in out[:height]]

    def handle(self, key: Key) -> None:
        self._notice = None
        shortcut = self.shortcuts.get(key.name)
        if shortcut is not None:
            shortcut()
            return
        self.top.handle(self, key)

    def run(self, terminal: Terminal) -> None:
        """Draw, wait up to 0.25 s for keys, handle them, run the ticks; until quit()."""
        last_tick = time.monotonic()
        while self.running:
            terminal.draw(self.render(*terminal.size()))
            for key in terminal.read_keys(_TICK_SECONDS):
                self.handle(key)
                if not self.running:
                    return
            now = time.monotonic()
            if now - last_tick >= _TICK_SECONDS:
                last_tick = now
                for tick in list(self.ticks):
                    tick()

    def _header_lines(self) -> list[str]:
        style, header = self.style, self.header
        texts = [
            style.bold(header.name) + " " + style.fg("dim", f"v{header.version}"),
            style.fg("muted", header.tagline),
            key_hints(style, header.hints),
        ]
        if self._logo is None:
            return [" " + text for text in texts]
        return [" " + logo + "  " + text for logo, text in zip(self._logo, texts, strict=True)]

    def _notice_lines(self, width: int, allowed: int) -> list[str]:
        if self._notice is None or allowed <= 0:
            return []
        tone, title, body = self._notice
        lines = box(self.style, tone, title, body, width)
        if len(lines) <= allowed:
            return lines
        if allowed >= 3:  # keep the bottom padding row
            return lines[: allowed - 1] + [lines[-1]]
        return [lines[1]]  # the title row alone


# ── ListView ─────────────────────────────────────────────────────────────────


def _row_key(row: Row) -> str:
    return row.id or row.label


class ListView:
    """pi's SettingsList: label column, value column, help of the selected row, hint line.
    Rows are recomputed on every render; the selection follows the row's id (else label)."""

    def __init__(
        self,
        title: str | Callable[[], str],
        rows: Callable[[], Sequence[Row]],
        *,
        subtitle: str | Callable[[], str] = "",
        hint: str = "Enter/Space to change · Esc to go back",
        keys: Mapping[str, Callable[[Row], None]] | None = None,
        on_back: Callable[[], None] | None = None,
    ) -> None:
        self._title = title
        self._rows = rows
        self._subtitle = subtitle
        self._hint = hint
        self._keys = dict(keys or {})
        self._on_back = on_back
        self._index = 0
        self._key: str | None = None
        self._page = _SUBMENU_ROWS

    @property
    def selected(self) -> Row | None:
        rows = self._refresh()
        return rows[self._index] if rows else None

    def select(self, row_id: str) -> None:
        """Move the selection to the row with that id (or label); no-op if there is none."""
        for index, row in enumerate(self._rows()):
            if _row_key(row) == row_id:
                self._index, self._key = index, row_id
                return

    def render(self, app: App, width: int, height: int) -> list[str]:
        style = app.style
        rows = self._refresh()
        head = [_title(style, _resolve(self._title), width)]
        head += _muted_block(style, _resolve(self._subtitle), width)
        head.append("")
        tail = _hint_tail(style, self._hint, width)
        if not rows:
            return _fit([*head, style.fg("dim", "  Nothing here yet")], tail, height)
        selected = rows[self._index]
        help_lines = [style.fg("dim", "  " + line) for line in wrap(selected.help, width - 4)]
        extra = ["", *help_lines] if help_lines else []
        room = height - len(head) - len(tail)
        visible, extra, scrolled = _layout(len(rows), extra, room)
        self._page = max(1, visible)
        start, end = _window(self._index, len(rows), visible)
        labels = [_display_label(row) for row in rows]
        column = max(1, min(_LABEL_COLUMN, max(map(visible_width, labels)), width - 14))
        body = head + [
            self._row_line(style, rows[i], labels[i], i == self._index, column, width)
            for i in range(start, end)
        ]
        if scrolled:
            body.append(_scroll_info(style, self._index, len(rows)))
        return _fit(body + extra, tail, height)

    def handle(self, app: App, key: Key) -> None:
        rows = self._refresh()
        moved = _move(self._index, len(rows), key, self._page)
        if moved is not None:
            self._index, self._key = moved, _row_key(rows[moved])
        elif key.name == "enter" or _space(key):
            action = rows[self._index].action if rows else None
            if action is not None:
                action()
        elif _cancel(key):
            if self._on_back is not None:
                self._on_back()
            else:
                app.pop()
        else:
            handler = self._keys.get(key.name)
            if handler is None and key.name == "char":
                handler = self._keys.get(key.text)
            if handler is not None and rows:
                handler(rows[self._index])

    def _refresh(self) -> list[Row]:
        rows = list(self._rows())
        if not rows:
            self._index, self._key = 0, None
            return rows
        found = next((i for i, row in enumerate(rows) if _row_key(row) == self._key), None)
        self._index = min(self._index, len(rows) - 1) if found is None else found
        self._key = _row_key(rows[self._index])
        return rows

    @staticmethod
    def _row_line(
        style: Style, row: Row, label: str, selected: bool, column: int, width: int
    ) -> str:
        shown = truncate(label, column)
        padding = " " * (column - visible_width(shown))
        label_color: Token | None = "accent" if selected or row.tone == "add" else None
        value_color: Token = _VALUE_TONES.get(row.tone) or ("accent" if selected else "muted")
        if row.tone == "danger":
            label_color = "error"
        elif row.tone == "muted":
            label_color = value_color = "dim"
        line = _cursor(style, selected) + _paint(style, label_color, shown)
        value_width = width - 2 - column - 2
        if row.value and value_width > 0:
            line += padding + "  " + _paint(style, value_color, truncate(row.value, value_width))
        return line


def _display_label(row: Row) -> str:
    return "+ " + row.label if row.tone == "add" else row.label


# ── submenus ─────────────────────────────────────────────────────────────────


class SelectView:
    """pi's SelectSubmenu: Enter removes the view, then calls on_select(value)."""

    def __init__(
        self,
        title: str,
        description: str,
        options: Sequence[Option],
        current: str | None,
        on_select: Callable[[str], None],
    ) -> None:
        self._title = title
        self._description = description
        self._options = list(options)
        self._on_select = on_select
        values = [option.value for option in self._options]
        self._index = values.index(current) if current in values else 0
        self._page = _SUBMENU_ROWS

    def render(self, app: App, width: int, height: int) -> list[str]:
        style = app.style
        head = _head(style, self._title, self._description, width)
        tail = _hint_tail(style, "Enter to select · Esc to go back", width)
        options = self._options
        if not options:
            return _fit([*head, style.fg("muted", "  Nothing to choose from")], tail, height)
        room = height - len(head) - len(tail)
        visible, _, scrolled = _layout(len(options), [], room, _SUBMENU_ROWS)
        self._page = visible
        start, end = _window(self._index, len(options), visible)
        column = _primary_column([option.label or option.value for option in options])
        body = list(head)
        for i in range(start, end):
            option, selected = options[i], i == self._index
            line = _option_line(
                style,
                2,
                option.label or option.value,
                option.description,
                width,
                column,
                selected=selected,
            )
            body.append(_cursor(style, selected) + line)
        if scrolled:
            body.append(_scroll_info(style, self._index, len(options)))
        return _fit(body, tail, height)

    def handle(self, app: App, key: Key) -> None:
        moved = _move(self._index, len(self._options), key, self._page)
        if moved is not None:
            self._index = moved
        elif key.name == "enter" and self._options:
            app.remove(self)
            self._on_select(self._options[self._index].value)
        elif _cancel(key):
            app.remove(self)


class MultiSelectView:
    """Checklist: Space toggles, ctrl+a all, ctrl+x none, Enter confirms (removes the view, then
    on_confirm(values in options order)) unless fewer than min_selected are checked."""

    def __init__(
        self,
        title: str,
        description: str,
        options: Sequence[Option],
        selected: Collection[str],
        on_confirm: Callable[[list[str]], None],
        *,
        min_selected: int = 0,
    ) -> None:
        self._title = title
        self._description = description
        self._options = list(options)
        self._checked = {option.value for option in self._options if option.value in selected}
        self._on_confirm = on_confirm
        self._min = min_selected
        self._index = 0
        self._page = _SUBMENU_ROWS
        self._message = ""

    def render(self, app: App, width: int, height: int) -> list[str]:
        style = app.style
        head = _head(style, self._title, self._description, width)
        hint = "Space to toggle · ctrl+a all · ctrl+x none · Enter to confirm · Esc to cancel"
        tail = _hint_tail(style, hint, width)
        options = self._options
        message = ["", style.fg("error", truncate("  " + self._message, width))]
        extra = message if self._message else []
        if not options:
            return _fit(
                [*head, style.fg("muted", "  Nothing to choose from"), *extra], tail, height
            )
        room = height - len(head) - len(tail)
        visible, extra, scrolled = _layout(len(options), extra, room)
        self._page = visible
        start, end = _window(self._index, len(options), visible)
        column = _primary_column([option.label or option.value for option in options])
        body = list(head)
        for i in range(start, end):
            option, selected = options[i], i == self._index
            check = style.fg("accent", "✓") if option.value in self._checked else " "
            line = _option_line(
                style,
                4,
                option.label or option.value,
                option.description,
                width,
                column,
                selected=selected,
            )
            body.append(_cursor(style, selected) + check + " " + line)
        if scrolled:
            body.append(_scroll_info(style, self._index, len(options)))
        return _fit(body + extra, tail, height)

    def handle(self, app: App, key: Key) -> None:
        moved = _move(self._index, len(self._options), key, self._page)
        if moved is not None:
            self._index = moved
        elif _space(key) and self._options:
            value = self._options[self._index].value
            self._checked ^= {value}
            self._message = ""
        elif key.name == "ctrl+a":
            self._checked = {option.value for option in self._options}
            self._message = ""
        elif key.name == "ctrl+x":
            self._checked = set()
            self._message = ""
        elif key.name == "enter":
            if len(self._checked) < self._min:
                noun = "option" if self._min == 1 else "options"
                self._message = f"Select at least {self._min} {noun}, then press Enter"
                return
            app.remove(self)
            self._on_confirm([o.value for o in self._options if o.value in self._checked])
        elif _cancel(key):
            app.remove(self)


class ConfirmView:
    """A short list of choices: Enter removes the view, then runs the choice; Esc removes it."""

    def __init__(self, title: str, description: str, choices: Sequence[Choice]) -> None:
        self._title = title
        self._description = description
        self._choices = list(choices)
        self._index = 0
        self._page = _SUBMENU_ROWS

    def render(self, app: App, width: int, height: int) -> list[str]:
        style = app.style
        head = _head(style, self._title, self._description, width)
        tail = _hint_tail(style, "Enter to confirm · Esc to cancel", width)
        choices = self._choices
        room = height - len(head) - len(tail)
        visible, _, scrolled = _layout(len(choices), [], room)
        self._page = max(1, visible)
        start, end = _window(self._index, len(choices), visible)
        column = _primary_column([choice.label for choice in choices])
        body = list(head)
        for i in range(start, end):
            choice, selected = choices[i], i == self._index
            token: Token | None = "error" if choice.tone == "danger" else None
            line = _option_line(
                style,
                2,
                choice.label,
                choice.description,
                width,
                column,
                selected=selected,
                label_token=token,
            )
            body.append(_cursor(style, selected) + line)
        if scrolled:
            body.append(_scroll_info(style, self._index, len(choices)))
        return _fit(body, tail, height)

    def handle(self, app: App, key: Key) -> None:
        moved = _move(self._index, len(self._choices), key, self._page)
        if moved is not None:
            self._index = moved
        elif key.name == "enter" and self._choices:
            app.remove(self)
            self._choices[self._index].action()
        elif _cancel(key):
            app.remove(self)


# ── InputView ────────────────────────────────────────────────────────────────


class InputView:
    """pi's single-line Input under a title: Enter calls on_submit(text); a ValueError shows its
    message inline and keeps the view, success removes it. Secret text renders as •."""

    def __init__(
        self,
        title: str,
        description: str,
        initial: str,
        on_submit: Callable[[str], None],
        *,
        placeholder: str = "",
        secret: bool = False,
    ) -> None:
        self._title = title
        self._description = description
        self._on_submit = on_submit
        self._placeholder = placeholder
        self._secret = secret
        self._text = _printable(initial)
        self._cursor = len(self._text)
        self._error = ""

    def render(self, app: App, width: int, height: int) -> list[str]:
        style = app.style
        head = _head(style, self._title, self._description, width)
        body = [*head, self._input_line(style, width)]
        if self._error:
            body += [style.fg("error", line) for line in wrap(self._error, width)]
        tail = _hint_tail(style, "Enter to confirm · Esc to cancel", width)
        return _fit(body, tail, height)

    def handle(self, app: App, key: Key) -> None:
        text, cursor = self._text, self._cursor
        match key.name:
            case "enter":
                self._submit(app)
                return
            case "escape" | "ctrl+c":
                app.remove(self)
                return
            case "left":
                cursor = max(0, cursor - 1)
            case "right":
                cursor = min(len(text), cursor + 1)
            case "home" | "ctrl+a":
                cursor = 0
            case "end" | "ctrl+e":
                cursor = len(text)
            case "backspace":
                if cursor > 0:
                    text, cursor = text[: cursor - 1] + text[cursor:], cursor - 1
            case "delete":
                text = text[:cursor] + text[cursor + 1 :]
            case "ctrl+u":
                text, cursor = text[cursor:], 0
            case "ctrl+k":
                text = text[:cursor]
            case "ctrl+w":
                start = _word_start(text, cursor)
                text, cursor = text[:start] + text[cursor:], start
            case "char" | "paste":
                insert = _printable(key.text)
                text, cursor = text[:cursor] + insert + text[cursor:], cursor + len(insert)
            case _:
                return
        self._text, self._cursor = text, cursor
        self._error = ""

    def _submit(self, app: App) -> None:
        try:
            self._on_submit(self._text)
        except ValueError as exc:
            self._error = str(exc) or "That value is not valid; change it and press Enter"
            return
        app.remove(self)

    def _input_line(self, style: Style, width: int) -> str:
        prompt = "> "
        room = width - len(prompt)
        if room <= 0:
            return prompt[: max(width, 0)]
        if not self._text and self._placeholder:
            shown = truncate(self._placeholder, room)
            return prompt + style.inverse(shown[0]) + style.fg("dim", shown[1:])
        shown = "•" * len(self._text) if self._secret else self._text
        first, last = _visible_span(shown, self._cursor, room)
        at = shown[self._cursor] if self._cursor < len(shown) else " "
        before = shown[first : self._cursor]
        after = shown[self._cursor + 1 : last]
        return pad(prompt + before + style.inverse(at) + after, width)


def _printable(text: str) -> str:
    return "".join(ch if ch.isprintable() else " " for ch in text if ch not in "\r\n")


def _word_start(text: str, cursor: int) -> int:
    """Start of the word before `cursor` (ctrl+w): skip spaces, then the word itself."""
    start = cursor
    while start > 0 and text[start - 1].isspace():
        start -= 1
    while start > 0 and not text[start - 1].isspace():
        start -= 1
    return start


def _visible_span(text: str, cursor: int, room: int) -> tuple[int, int]:
    """Character range of `text` shown in `room` columns so the cursor stays visible (pi's
    horizontal scrolling: start, middle or end anchored, one column kept for an end cursor)."""
    total = visible_width(text)
    if total < room:
        return 0, len(text)
    span = room - 1 if cursor == len(text) else room
    cursor_col = visible_width(text[:cursor])
    half = span // 2
    if cursor_col < half:
        start_col = 0
    elif cursor_col > total - half:
        start_col = max(0, total - span)
    else:
        start_col = cursor_col - half
    first = col = 0
    while first < len(text) and col < start_col:
        col += char_width(text[first])
        first += 1
    last, used = first, 0
    while last < len(text) and used + char_width(text[last]) <= span:
        used += char_width(text[last])
        last += 1
    return first, last


# ── TextView ─────────────────────────────────────────────────────────────────


class TextView:
    """Scrollable text (diffs, logs, help). Enter calls on_enter (it decides whether the view
    closes); Esc removes the view."""

    def __init__(
        self,
        title: str,
        body: Callable[[int], list[str]],
        *,
        subtitle: str | Callable[[], str] = "",
        hint: str = "↑↓ scroll · Esc to go back",
        on_enter: Callable[[], None] | None = None,
    ) -> None:
        self._title = title
        self._body = body
        self._subtitle = subtitle
        self._hint = hint
        self._on_enter = on_enter
        self._offset = 0
        self._page = 1
        self._total = 0

    def render(self, app: App, width: int, height: int) -> list[str]:
        style = app.style
        head = [_title(style, self._title, width)]
        head += _muted_block(style, _resolve(self._subtitle), width)
        head.append("")
        tail = _hint_tail(style, self._hint, width)
        text = [clip(line, width) for line in self._body(width)]
        room = max(1, height - len(head) - len(tail))
        self._total = len(text)
        self._page = room if len(text) <= room else max(1, room - 1)
        self._offset = max(0, min(self._offset, len(text) - self._page))
        shown = text[self._offset : self._offset + self._page]
        if len(text) > room:
            end = self._offset + len(shown)
            shown.append(style.fg("dim", f"  ({self._offset + 1}-{end}/{len(text)})"))
        return _fit(head + shown, tail, height)

    def handle(self, app: App, key: Key) -> None:
        last = max(0, self._total - self._page)
        match key.name:
            case "up":
                self._offset = max(0, self._offset - 1)
            case "down":
                self._offset = min(last, self._offset + 1)
            case "pageup":
                self._offset = max(0, self._offset - self._page)
            case "pagedown":
                self._offset = min(last, self._offset + self._page)
            case "home":
                self._offset = 0
            case "end":
                self._offset = last
            case "enter":
                if self._on_enter is not None:
                    self._on_enter()
            case "escape" | "ctrl+c":
                app.remove(self)
