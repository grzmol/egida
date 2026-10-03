"""Egida's policy screens driven by keys over a copy of config/policy.yaml (no terminal/proxy)."""

from __future__ import annotations

import hashlib
import re
import shutil
from collections.abc import Sequence
from pathlib import Path

import pytest

from control_layer.egida.document import PolicyDocument
from control_layer.egida.keys import Key
from control_layer.egida.runner import Proxy, RunProfile
from control_layer.egida.schema import detector_params
from control_layer.egida.screens import build_app
from control_layer.egida.session import Session
from control_layer.egida.theme import ColorMode, Style, visible_width
from control_layer.egida.widgets import App, ConfirmView, InputView, ListView, TextView

REPO = Path(__file__).resolve().parents[3]
PLAIN = Style(ColorMode.NONE)
_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
_KEY = re.compile(r"sk-[A-Za-z0-9_-]{32}")


@pytest.fixture
def policy(tmp_path: Path) -> Path:
    target = tmp_path / "policy.yaml"
    shutil.copyfile(REPO / "config" / "policy.yaml", target)
    return target


@pytest.fixture
def session(tmp_path: Path, policy: Path, monkeypatch: pytest.MonkeyPatch) -> Session:
    monkeypatch.chdir(tmp_path)
    return Session(
        doc=PolicyDocument.open(policy),
        profile=RunProfile(policy=policy, port=1),
        profile_path=tmp_path / "egida.yaml",
        proxy=Proxy(log_path=tmp_path / "proxy.log"),
        param_models=detector_params(),
    )


@pytest.fixture
def app(session: Session) -> App:
    return build_app(session, style=PLAIN)


def press(app: App, *names: str) -> None:
    for name in names:
        app.handle(Key(name))


def type_text(app: App, text: str) -> None:
    for ch in text:
        app.handle(Key("char", ch))


def screen(app: App, width: int = 100, height: int = 40) -> str:
    return "\n".join(_ANSI.sub("", line) for line in app.render(width, height))


def open_row(app: App, row_id: str) -> None:
    view = app.top
    assert isinstance(view, ListView)
    view.select(row_id)
    selected = view.selected
    assert selected is not None and (selected.id or selected.label) == row_id
    press(app, "enter")


def has_row(app: App, row_id: str) -> bool:
    view = app.top
    assert isinstance(view, ListView)
    view.select(row_id)
    selected = view.selected
    return selected is not None and (selected.id or selected.label) == row_id


def replace_input(app: App, text: str) -> None:
    assert isinstance(app.top, InputView)
    press(app, "end", "ctrl+u")
    type_text(app, text)
    press(app, "enter")


def test_add_agent_reveals_a_key_whose_sha256_is_in_the_policy(app: App, session: Session) -> None:
    open_row(app, "agents")
    open_row(app, "add")
    replace_input(app, "new-agent")

    assert isinstance(app.top, TextView)
    keys = _KEY.findall(screen(app))
    assert len(keys) == 1
    digest = hashlib.sha256(keys[0].encode()).hexdigest()
    assert session.doc.get(("agents", "new-agent", "key_sha256")) == digest
    assert session.doc.get(("agents", "new-agent", "budget")) == "default"
    assert session.errors() == []

    press(app, "escape")  # the key is shown once: the entry view stays without it
    assert not _KEY.search(screen(app))
    assert isinstance(app.top, ListView)


def test_generated_key_replaces_digest_and_drops_stale_comment(app: App, session: Session) -> None:
    assert 'sha256("sk-demo-agent")' in session.doc.render()
    open_row(app, "agents")
    open_row(app, "entry:demo-agent")
    open_row(app, "key")
    assert isinstance(app.top, ConfirmView)
    press(app, "enter")  # Generate a new key

    key = _KEY.findall(screen(app))[0]
    digest = hashlib.sha256(key.encode()).hexdigest()
    assert session.doc.get(("agents", "demo-agent", "key_sha256")) == digest
    assert 'sha256("sk-demo-agent")' not in session.doc.render()
    assert 'sha256("sk-ci-agent")' in session.doc.render()


def test_set_key_and_paste_sha256_store_only_the_digest(app: App, session: Session) -> None:
    path = ("agents", "ci-agent", "key_sha256")
    open_row(app, "agents")
    open_row(app, "entry:ci-agent")

    open_row(app, "key")
    press(app, "down", "enter")  # Set a key
    replace_input(app, "sk-my-own-key")
    assert session.doc.get(path) == hashlib.sha256(b"sk-my-own-key").hexdigest()
    assert "sk-my-own-key" not in session.doc.render()

    open_row(app, "key")
    press(app, "down", "down", "enter")  # Paste a sha256
    replace_input(app, "not-a-digest")
    assert isinstance(app.top, InputView)  # refused inline, nothing written
    assert session.doc.get(path) == hashlib.sha256(b"sk-my-own-key").hexdigest()
    replace_input(app, "A" * 64)
    assert session.doc.get(path) == "a" * 64


def test_rename_budget_in_entry_view_updates_agents_and_keeps_following(
    app: App, session: Session
) -> None:
    open_row(app, "budgets")
    open_row(app, "entry:small")
    entry = app.top
    open_row(app, "rename")
    replace_input(app, "tiny")

    assert app.top is entry
    assert "tiny" in session.doc.names("budgets")
    assert "small" not in session.doc.names("budgets")
    assert session.doc.get(("agents", "ci-agent", "budget")) == "tiny"
    assert session.doc.get(("budgets", "tiny", "max_requests")) == 30
    assert "Budget tiny" in screen(app)
    assert session.errors() == []


def test_rename_to_a_taken_name_is_refused_inline(app: App, session: Session) -> None:
    open_row(app, "budgets")
    open_row(app, "entry:small")
    open_row(app, "rename")
    replace_input(app, "default")

    assert isinstance(app.top, InputView)
    assert session.doc.names("budgets") == ["default", "small", "selftest", "bench"]
    assert not session.doc.dirty


def test_delete_used_budget_shows_error_and_deletes_nothing(app: App, session: Session) -> None:
    open_row(app, "budgets")
    view = app.top
    assert isinstance(view, ListView)
    view.select("entry:default")
    press(app, "delete")

    assert "agents.demo-agent" in screen(app)  # the error box names who uses it
    assert "default" in session.doc.names("budgets")
    assert not session.doc.dirty
    assert app.top is view


def test_delete_unused_entry_asks_then_removes_it(app: App, session: Session) -> None:
    open_row(app, "upstreams")
    open_row(app, "add")
    replace_input(app, "spare")
    assert "spare" in session.doc.names("upstreams")
    entry = app.top

    open_row(app, "delete")
    assert isinstance(app.top, ConfirmView)
    press(app, "enter")

    assert "spare" not in session.doc.names("upstreams")
    assert app.top is not entry


def test_empty_section_teaches_and_offers_add(session: Session, app: App) -> None:
    session.change(lambda doc: doc.set(("upstreams",), {}))
    open_row(app, "upstreams")
    assert has_row(app, "add")
    assert not has_row(app, "entry:ollama")
    assert "No upstreams yet" in screen(app)  # the selected Add row explains the section


def test_review_and_save_writes_file_and_clears_dirty(
    app: App, session: Session, policy: Path
) -> None:
    open_row(app, "General")
    open_row(app, "version")
    replace_input(app, "2")
    assert session.doc.dirty

    press(app, "ctrl+s")
    assert "+version: 2" in screen(app)
    press(app, "enter")

    text = policy.read_text(encoding="utf-8")
    assert "version: 2" in text
    assert "# AI Control Layer: policy v1" in text  # comments survive the save
    assert not session.doc.dirty
    assert not isinstance(app.top, TextView)


def test_save_without_changes_writes_nothing(app: App, session: Session, policy: Path) -> None:
    before = policy.stat().st_mtime_ns
    press(app, "ctrl+s")
    assert isinstance(app.top, ListView)
    assert policy.stat().st_mtime_ns == before


def test_invalid_change_shows_problems_and_refuses_save(
    app: App, session: Session, policy: Path
) -> None:
    original = policy.read_bytes()
    assert not has_row(app, "Problems")
    session.change(lambda doc: doc.set(("models", "llama3.2:3b", "upstream"), "nowhere"))

    assert has_row(app, "Problems")
    press(app, "ctrl+s")
    assert isinstance(app.top, TextView)
    assert "Cannot save" in screen(app)
    press(app, "enter")
    assert policy.read_bytes() == original
    assert session.doc.dirty


def test_conflict_on_save_offers_overwrite(app: App, session: Session, policy: Path) -> None:
    open_row(app, "General")
    open_row(app, "version")
    replace_input(app, "3")
    policy.write_text(policy.read_text(encoding="utf-8") + "# edited elsewhere\n", "utf-8")

    press(app, "ctrl+s", "enter")
    assert isinstance(app.top, ConfirmView)
    assert "edited elsewhere" in policy.read_text(encoding="utf-8")
    press(app, "enter")  # Overwrite with my version

    text = policy.read_text(encoding="utf-8")
    assert "version: 3" in text
    assert "edited elsewhere" not in text
    assert not session.doc.dirty


def test_reload_from_disk_drops_edits_after_confirm(app: App, session: Session) -> None:
    session.change(lambda doc: doc.set(("version",), 9))
    open_row(app, "Reload from disk")
    assert isinstance(app.top, ConfirmView)
    press(app, "enter")
    assert session.doc.get(("version",)) == 1
    assert not session.doc.dirty


def test_quit_without_changes_exits_at_once(app: App) -> None:
    press(app, "escape")
    assert not app.running


def test_quit_with_unsaved_changes_asks_first(app: App, session: Session) -> None:
    session.change(lambda doc: doc.set(("version",), 2))
    press(app, "escape")
    assert app.running
    assert isinstance(app.top, ConfirmView)

    press(app, "escape")  # cancel keeps the edits
    assert app.running and session.doc.dirty

    open_row(app, "Quit")
    press(app, "down", "enter")  # Review & save, then Quit
    assert not app.running


@pytest.mark.parametrize(("width", "height"), [(80, 24), (50, 16)])
@pytest.mark.parametrize("mode", [ColorMode.NONE, ColorMode.TRUECOLOR])
def test_root_render_fits_the_screen(
    session: Session, width: int, height: int, mode: ColorMode
) -> None:
    app = build_app(session, style=Style(mode))
    session.change(lambda doc: doc.set(("models", "llama3.2:3b", "upstream"), "nowhere"))
    lines: Sequence[str] = app.render(width, height)
    assert len(lines) == height
    assert all(visible_width(line) <= width for line in lines)
    assert "egida" in _ANSI.sub("", "\n".join(lines))
