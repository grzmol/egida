"""pi widgets and the App frame, driven by keys without a terminal."""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence

import pytest

from control_layer.egida.keys import Key
from control_layer.egida.theme import ColorMode, Style, visible_width
from control_layer.egida.widgets import (
    App,
    Choice,
    ConfirmView,
    Header,
    InputView,
    ListView,
    MultiSelectView,
    Option,
    Row,
    SelectView,
    TextView,
    View,
)

PLAIN = Style(ColorMode.NONE)
COLOR = Style(ColorMode.TRUECOLOR)
_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
HEADER = Header("Egida", "0.1.0", "AI Control Layer", (("ctrl+s", "save"), ("ctrl+q", "quit")))


def make_app(root: View | None = None, style: Style = PLAIN) -> App:
    base = root or ListView("Root", lambda: [Row("root row")])
    return App(base, style=style, header=HEADER, footer=lambda width: ["footer one", "footer two"])


def press(app: App, *names: str) -> None:
    for name in names:
        app.handle(Key(name))


def type_text(app: App, text: str) -> None:
    for ch in text:
        app.handle(Key("char", ch))


def plain(lines: Sequence[str]) -> str:
    return "\n".join(_ANSI.sub("", line) for line in lines)


def selected_label(view: ListView) -> str:
    row = view.selected
    assert row is not None
    return row.label


def rows_of(labels: Sequence[str]) -> Callable[[], list[Row]]:
    return lambda: [Row(label) for label in labels]


# ── ListView ─────────────────────────────────────────────────────────────────


def test_list_up_and_down_wrap_around() -> None:
    view = ListView("Settings", rows_of(["a", "b", "c"]))
    app = make_app(view)
    press(app, "up")
    assert selected_label(view) == "c"
    press(app, "down")
    assert selected_label(view) == "a"
    press(app, "end", "pageup", "home")
    assert selected_label(view) == "a"


@pytest.mark.parametrize("key", [Key("enter"), Key("char", " ")])
def test_list_enter_and_space_run_the_selected_action(key: Key) -> None:
    ran: list[str] = []
    view = ListView(
        "Settings",
        lambda: [
            Row("a", action=lambda: ran.append("a")),
            Row("b", action=lambda: ran.append("b")),
        ],
    )
    app = make_app(view)
    press(app, "down")
    app.handle(key)
    assert ran == ["b"]


def test_list_row_without_action_ignores_enter() -> None:
    view = ListView("Settings", rows_of(["a"]))
    app = make_app(view)
    press(app, "enter")
    assert app.top is view


@pytest.mark.parametrize("name", ["escape", "ctrl+c"])
def test_list_back_calls_on_back_instead_of_popping(name: str) -> None:
    backs: list[bool] = []
    view = ListView("Child", rows_of(["a"]), on_back=lambda: backs.append(True))
    app = make_app()
    app.push(view)
    press(app, name)
    assert backs == [True]
    assert app.top is view


@pytest.mark.parametrize("name", ["escape", "ctrl+c"])
def test_list_back_without_handler_pops(name: str) -> None:
    view = ListView("Child", rows_of(["a"]))
    app = make_app()
    app.push(view)
    press(app, name)
    assert app.top is not view


def test_list_extra_keys_get_the_selected_row() -> None:
    seen: list[str] = []
    view = ListView(
        "Agents",
        rows_of(["a", "b"]),
        keys={
            "delete": lambda row: seen.append("del " + row.label),
            "r": lambda row: seen.append("r " + row.label),
        },
    )
    app = make_app(view)
    press(app, "down", "delete")
    app.handle(Key("char", "r"))
    assert seen == ["del b", "r b"]


def test_list_extra_keys_do_nothing_without_rows() -> None:
    seen: list[Row] = []
    app = make_app(ListView("Empty", lambda: [], keys={"delete": seen.append}))
    press(app, "delete", "down", "enter")
    assert seen == []


def test_list_selection_follows_id_when_rows_are_recomputed() -> None:
    order = ["x", "y", "z"]
    view = ListView("Agents", lambda: [Row(f"label {i}", id=i) for i in order])
    app = make_app(view)
    view.select("y")
    order.reverse()
    app.render(80, 24)
    row = view.selected
    assert row is not None and row.id == "y"
    order.remove("y")
    row = view.selected
    assert row is not None and row.id in order


def test_list_select_unknown_id_keeps_selection() -> None:
    view = ListView("Agents", rows_of(["a", "b"]))
    view.select("b")
    view.select("missing")
    assert selected_label(view) == "b"


def test_list_scrolls_rows_beyond_the_height_and_shows_position() -> None:
    labels = [f"row {i:02d}" for i in range(30)]
    view = ListView("Long", rows_of(labels))
    app = make_app(view)
    lines = view.render(app, 60, 12)
    text = plain(lines)
    assert len(lines) <= 12
    assert "(1/30)" in text and "row 00" in text and "row 29" not in text
    press(app, "end")
    text = plain(view.render(app, 60, 12))
    assert "(30/30)" in text and "row 29" in text and "row 00" not in text


def test_list_without_overflow_has_no_position() -> None:
    view = ListView("Short", rows_of(["a", "b"]))
    assert "(1/2)" not in plain(view.render(make_app(view), 60, 20))


def test_list_value_column_is_truncated_to_width() -> None:
    view = ListView("S", lambda: [Row("label", "v" * 200, help="h " * 100)])
    lines = view.render(make_app(view, COLOR), 40, 20)
    assert all(visible_width(line) <= 40 for line in lines)


# ── SelectView ───────────────────────────────────────────────────────────────


def test_select_preselects_current_and_removes_itself_before_on_select() -> None:
    app = make_app()
    calls: list[tuple[str, bool]] = []
    view = SelectView(
        "Action",
        "What to do",
        [Option("allow", "allow"), Option("redact", "redact"), Option("block", "block")],
        "redact",
        lambda value: calls.append((value, app.top is not view)),
    )
    app.push(view)
    press(app, "enter")
    assert calls == [("redact", True)]
    assert app.top is not view


def test_select_navigates_and_escape_cancels() -> None:
    app = make_app()
    chosen: list[str] = []
    view = SelectView("A", "", [Option("a", "A"), Option("b", "B")], None, chosen.append)
    app.push(view)
    press(app, "up", "enter")
    assert chosen == ["b"]
    view = SelectView("A", "", [Option("a", "A")], "a", chosen.append)
    app.push(view)
    press(app, "escape")
    assert chosen == ["b"] and app.top is not view


# ── MultiSelectView ──────────────────────────────────────────────────────────


def _options() -> list[Option]:
    return [Option("email", "email"), Option("phone", "phone"), Option("iban", "iban")]


def test_multi_space_toggles_and_values_keep_option_order() -> None:
    app = make_app()
    confirmed: list[list[str]] = []
    view = MultiSelectView("Entities", "", _options(), {"iban"}, confirmed.append)
    app.push(view)
    app.handle(Key("char", " "))  # email on
    press(app, "down", "down")
    app.handle(Key("char", " "))  # iban off
    press(app, "enter")
    assert confirmed == [["email"]]
    assert app.top is not view


def test_multi_select_all_and_none() -> None:
    app = make_app()
    confirmed: list[list[str]] = []
    app.push(MultiSelectView("E", "", _options(), (), confirmed.append))
    press(app, "ctrl+a", "enter")
    app.push(MultiSelectView("E", "", _options(), {"email", "phone"}, confirmed.append))
    press(app, "ctrl+x", "enter")
    assert confirmed == [["email", "phone", "iban"], []]


def test_multi_min_selected_blocks_with_an_inline_message() -> None:
    app = make_app()
    confirmed: list[list[str]] = []
    view = MultiSelectView("E", "", _options(), {"email"}, confirmed.append, min_selected=1)
    app.push(view)
    before = view.render(app, 60, 20)
    press(app, "ctrl+x", "enter")
    assert confirmed == [] and app.top is view
    assert len(view.render(app, 60, 20)) > len(before)
    app.handle(Key("char", " "))
    press(app, "enter")
    assert confirmed == [["email"]]


def test_multi_escape_cancels_without_confirming() -> None:
    app = make_app()
    confirmed: list[list[str]] = []
    view = MultiSelectView("E", "", _options(), (), confirmed.append)
    app.push(view)
    press(app, "ctrl+a", "escape")
    assert confirmed == [] and app.top is not view


# ── InputView ────────────────────────────────────────────────────────────────


def _submit_after(initial: str, keys: Sequence[Key]) -> str:
    app = make_app()
    submitted: list[str] = []
    app.push(InputView("Name", "", initial, submitted.append))
    for key in keys:
        app.handle(key)
    app.handle(Key("enter"))
    return submitted[0]


def _k(*names: str) -> list[Key]:
    return [Key(name) for name in names]


@pytest.mark.parametrize(
    ("initial", "keys", "expected"),
    [
        ("hello", [*_k("left", "left"), Key("char", "X")], "helXlo"),
        ("hello", _k("home", "delete"), "ello"),
        ("hello", [*_k("ctrl+a", "right"), Key("char", "-")], "h-ello"),
        ("hello", [*_k("home", "ctrl+e"), Key("char", "!")], "hello!"),
        ("hello", _k("end", "right", "backspace"), "hell"),
        ("hello", _k("home", "backspace", "left"), "hello"),
        ("hello world", [*_k(*["left"] * 5), *_k("ctrl+u")], "world"),
        ("hello world", [*_k(*["left"] * 5), *_k("ctrl+k")], "hello "),
        ("foo bar  ", _k("ctrl+w"), "foo "),
        ("foo", _k("ctrl+w", "ctrl+w"), ""),
        ("ab", [Key("left"), Key("paste", "XY\tZ")], "aXY Zb"),
    ],
)
def test_input_editing_keys(initial: str, keys: list[Key], expected: str) -> None:
    assert _submit_after(initial, keys) == expected


def test_input_value_error_keeps_view_and_shows_message() -> None:
    app = make_app()

    def reject(text: str) -> None:
        raise ValueError(f"port {text} is out of range")

    view = InputView("Port", "", "99999", reject)
    app.push(view)
    press(app, "enter")
    assert app.top is view
    assert "port 99999 is out of range" in plain(view.render(app, 70, 20))


def test_input_success_removes_view() -> None:
    app = make_app()
    view = InputView("Port", "", "8080", lambda text: None)
    app.push(view)
    press(app, "enter")
    assert app.top is not view


def test_input_escape_cancels_without_submitting() -> None:
    app = make_app()
    submitted: list[str] = []
    view = InputView("Port", "", "8080", submitted.append)
    app.push(view)
    press(app, "escape")
    assert submitted == [] and app.top is not view


def test_input_secret_never_renders_the_text() -> None:
    view = InputView("Key", "", "sk-secret", lambda text: None, secret=True)
    app = make_app(view)
    for width in (10, 30, 80):
        text = plain(view.render(app, width, 20))
        assert "sk" not in text and "secret" not in text
    assert "•" in text


def test_input_long_text_scrolls_to_keep_the_cursor_visible() -> None:
    text = "".join(f"{i:03d}" for i in range(100))
    view = InputView("Long", "", text, lambda value: None)
    app = make_app(view, COLOR)
    lines = view.render(app, 30, 20)
    assert all(visible_width(line) <= 30 for line in lines)
    assert "099" in plain(lines) and "000" not in plain(lines)
    press(app, "home")
    lines = view.render(app, 30, 20)
    assert "000" in plain(lines) and "099" not in plain(lines)


# ── ConfirmView / TextView ───────────────────────────────────────────────────


def test_confirm_runs_choice_after_removing_itself() -> None:
    app = make_app()
    calls: list[tuple[str, bool]] = []
    view = ConfirmView(
        "Delete agent?",
        "ci-agent is not used.",
        [
            Choice("Cancel", lambda: calls.append(("cancel", app.top is not view))),
            Choice("Delete", lambda: calls.append(("delete", app.top is not view)), tone="danger"),
        ],
    )
    app.push(view)
    press(app, "down", "enter")
    assert calls == [("delete", True)]


def test_confirm_escape_runs_nothing() -> None:
    app = make_app()
    calls: list[str] = []
    view = ConfirmView("Quit?", "", [Choice("Quit", lambda: calls.append("quit"))])
    app.push(view)
    press(app, "escape")
    assert calls == [] and app.top is not view


def test_text_view_scrolls_and_escape_removes() -> None:
    app = make_app()
    view = TextView("Diff", lambda width: [f"line {i}" for i in range(100)])
    app.push(view)
    first = plain(view.render(app, 60, 20))
    assert "line 0\n" in first and "line 99" not in first
    press(app, "pagedown")
    assert "line 0\n" not in plain(view.render(app, 60, 20))
    press(app, "end")
    last = plain(view.render(app, 60, 20))
    assert "line 99" in last
    press(app, "home", "up")
    assert "line 0\n" in plain(view.render(app, 60, 20))
    press(app, "escape")
    assert app.top is not view


def test_text_view_enter_calls_on_enter() -> None:
    entered: list[bool] = []
    view = TextView("Diff", lambda width: ["x"], on_enter=lambda: entered.append(True))
    app = make_app()
    app.push(view)
    press(app, "enter")
    assert entered == [True] and app.top is view


# ── App ──────────────────────────────────────────────────────────────────────


def test_notify_box_is_shown_until_the_next_key_which_is_still_handled() -> None:
    view = ListView("Root", rows_of(["a", "b"]))
    app = make_app(view)
    app.notify("success", "Saved policy", "config/policy.yaml")
    shown = plain(app.render(80, 30))
    assert "Saved policy" in shown and "config/policy.yaml" in shown
    press(app, "down")
    assert "Saved policy" not in plain(app.render(80, 30))
    assert selected_label(view) == "b"


def test_notify_from_a_key_survives_that_key() -> None:
    app = make_app()
    app.shortcuts["ctrl+s"] = lambda: app.notify("error", "Not saved", ["policy invalid"])
    press(app, "ctrl+s")
    assert "Not saved" in plain(app.render(80, 30))


def test_shortcuts_run_before_the_top_view() -> None:
    seen: list[str] = []
    view = ListView("Root", rows_of(["a"]), keys={"ctrl+s": lambda row: seen.append("view")})
    app = make_app(view)
    app.shortcuts["ctrl+s"] = lambda: seen.append("shortcut")
    press(app, "ctrl+s")
    assert seen == ["shortcut"]


def test_pop_and_remove_never_drop_the_root() -> None:
    root = ListView("Root", rows_of(["a"]))
    app = make_app(root)
    child = ListView("Child", rows_of(["b"]))
    app.push(child)
    app.pop()
    app.pop()
    assert app.top is root
    app.remove(root)
    assert app.top is root


def test_remove_takes_a_view_from_the_middle_and_reset_replaces_the_stack() -> None:
    app = make_app()
    middle, top = ListView("M", rows_of(["m"])), ListView("T", rows_of(["t"]))
    app.push(middle)
    app.push(top)
    app.remove(middle)
    app.pop()
    assert app.top is not middle and app.top is not top
    new_root = ListView("New", rows_of(["n"]))
    app.reset(new_root)
    app.pop()
    assert app.top is new_root


def _busy_app(top: View) -> App:
    rows = [Row(f"setting {i}", "value " * 20, help="help text " * 30) for i in range(40)]
    app = make_app(ListView("Root", lambda: rows), COLOR)
    app.push(top)
    app.notify("error", "The policy is now invalid and cannot be saved", ["problem " * 40] * 6)
    return app


def _ignore(*_: object) -> None:
    return None


def _long_list() -> View:
    return ListView("Settings", lambda: [Row(f"setting {i}", "v" * 300) for i in range(60)])


def _long_select() -> View:
    options = [Option(str(i), f"o{i}", "x " * 60) for i in range(30)]
    return SelectView("Pick", "d " * 80, options, "29", _ignore)


def _blocked_multi() -> View:
    options = [Option(str(i), f"o{i}") for i in range(30)]
    return MultiSelectView("Many", "", options, (), _ignore, min_selected=40)


def _long_input() -> View:
    return InputView("Value", "desc " * 40, "y" * 400, _ignore)


def _long_text() -> View:
    return TextView("Diff", lambda width: ["+" + "z" * 500] * 200)


@pytest.mark.parametrize("size", [(50, 16), (64, 20), (80, 24), (120, 40), (200, 60)])
@pytest.mark.parametrize("top", [_long_list, _long_select, _blocked_multi, _long_input, _long_text])
def test_render_fills_the_screen_exactly(size: tuple[int, int], top: Callable[[], View]) -> None:
    width, height = size
    view = top()
    app = _busy_app(view)
    if isinstance(view, MultiSelectView):
        app.handle(Key("enter"))  # min_selected not met: the inline message is shown
    app.notify("info", "Proxy started", "pid 123")
    lines = app.render(width, height)
    assert len(lines) == height
    assert all(visible_width(line) <= width for line in lines)
    assert plain(lines[-2:]) == " footer one\n footer two"


@pytest.mark.parametrize("size", [(49, 16), (80, 15), (10, 3)])
def test_render_below_minimum_shows_only_the_too_small_line(size: tuple[int, int]) -> None:
    width, height = size
    lines = make_app().render(width, height)
    assert len(lines) == height
    assert lines[0] and all(line == "" for line in lines[1:])
    assert visible_width(lines[0]) <= width


class _FakeTerminal:
    def __init__(self, batches: list[list[Key]]) -> None:
        self.batches = batches
        self.frames: list[list[str]] = []

    def size(self) -> tuple[int, int]:
        return (80, 24)

    def draw(self, lines: Sequence[str]) -> None:
        self.frames.append(list(lines))

    def read_keys(self, timeout: float) -> list[Key]:
        return self.batches.pop(0) if self.batches else []


def test_run_draws_handles_keys_and_stops_on_quit() -> None:
    view = ListView("Root", rows_of(["a", "b"]))
    app = make_app(view)
    app.shortcuts["ctrl+q"] = app.quit
    terminal = _FakeTerminal([[Key("down")], [Key("ctrl+q"), Key("down")]])
    app.run(terminal)  # type: ignore[arg-type]
    assert not app.running
    assert len(terminal.frames) == 2
    assert selected_label(view) == "b"
