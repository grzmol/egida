"""Controls list and control view, driven by keys over a copy of config/policy.yaml."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from control_layer.egida.controls import controls_summary, controls_view
from control_layer.egida.document import PolicyDocument
from control_layer.egida.keys import Key
from control_layer.egida.runner import Proxy, RunProfile
from control_layer.egida.schema import detector_params, feed_rules
from control_layer.egida.session import Session
from control_layer.egida.theme import ColorMode, Style
from control_layer.egida.widgets import App, Header, ListView, MultiSelectView

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def session(tmp_path: Path) -> Session:
    policy = tmp_path / "policy.yaml"
    shutil.copy(ROOT / "config/policy.yaml", policy)
    feed = tmp_path / "feed.yaml"
    shutil.copy(ROOT / "signatures/feed.yaml", feed)
    s = Session(
        doc=PolicyDocument.open(policy),
        profile=RunProfile(policy=policy, feed=feed),
        profile_path=tmp_path / "egida.yaml",
        proxy=Proxy(tmp_path / "proxy.log"),
        param_models=detector_params(),
    )
    s.app = App(
        controls_view(s),
        style=Style(ColorMode.NONE),
        header=Header("egida", "0", "t", ()),
        footer=lambda width: ["", ""],
    )
    return s


def press(s: Session, *names: str) -> None:
    for name in names:
        s.ui.handle(Key(name))


def type_text(s: Session, text: str) -> None:
    for ch in text:
        s.ui.handle(Key("char", ch))


def ids(s: Session) -> list[str]:
    return [c["id"] for c in s.doc.get(("controls",))]


def top_list(s: Session) -> ListView:
    view = s.ui.top
    assert isinstance(view, ListView)
    return view


def go_to(s: Session, row_id: str) -> None:
    view = top_list(s)
    view.select(row_id)
    assert view.selected is not None and view.selected.id == row_id


def open_control(s: Session, cid: str) -> ListView:
    go_to(s, f"control:{cid}")
    press(s, "enter")
    return top_list(s)


def test_alt_down_moves_control_keeps_comment_and_selection(session: Session) -> None:
    go_to(session, "control:pii")
    press(session, "alt+down")
    assert ids(session)[1:3] == ["secrets", "pii"]
    assert top_list(session).selected.id == "control:pii"  # type: ignore[union-attr]
    text = session.doc.render()
    assert "- id: pii                    # C04" in text
    assert text.index("- id: secrets") < text.index("- id: pii")
    press(session, "shift+up")
    assert ids(session)[1:3] == ["pii", "secrets"]
    session.doc.save()
    assert session.errors() == []


def test_enter_on_enabled_disables_and_list_shows_off(session: Session) -> None:
    open_control(session, "pii")
    go_to(session, "controls.1.enabled")
    press(session, "enter")
    assert session.doc.get(("controls", 1, "enabled")) is False
    press(session, "escape")
    row = top_list(session).selected
    assert row is not None and row.value == "off" and row.tone == "muted"
    assert controls_summary(session).endswith("· 5 on")


def test_action_cycles(session: Session) -> None:
    open_control(session, "pii")
    go_to(session, "controls.1.action")
    seen = []
    for _ in range(3):
        press(session, "enter")
        seen.append(session.doc.get(("controls", 1, "action")))
    assert sorted(seen) == ["allow", "block", "redact"]


def test_add_pii_control_makes_valid_policy(session: Session) -> None:
    go_to(session, "add")
    press(session, "enter")  # kind picker
    kinds = sorted(session.param_models)
    for _ in range(kinds.index("pii")):
        press(session, "down")
    press(session, "enter")  # id input, prefilled "pii-2"
    press(session, "enter")
    assert ids(session)[-1] == "pii-2"
    assert session.errors() == []
    assert top_list(session).selected.id == "id"  # type: ignore[union-attr]


def test_add_rejects_taken_id(session: Session) -> None:
    go_to(session, "add")
    press(session, "enter", "enter")
    for _ in range(10):
        press(session, "backspace")
    type_text(session, "pii")
    before = ids(session)
    press(session, "enter")
    assert ids(session) == before


def test_kind_change_asks_then_drops_params(session: Session) -> None:
    open_control(session, "egress.tool")
    index = ids(session).index("egress.tool")
    go_to(session, "kind")
    press(session, "enter")  # SelectView, current = egress
    kinds = sorted(session.param_models)
    for _ in range(kinds.index("pii") - kinds.index("egress")):
        press(session, "down")
    press(session, "enter")  # confirm appears
    assert session.doc.get(("controls", index, "kind")) == "egress"
    press(session, "enter")
    assert session.doc.get(("controls", index, "kind")) == "pii"
    assert session.doc.get(("controls", index, "params")) is None
    assert session.errors() == []


def test_disabled_rules_picker_lists_feed_ids(session: Session) -> None:
    open_control(session, "signatures")
    go_to(session, "controls.0.params.disabled_rules")
    press(session, "enter")
    picker = session.ui.top
    assert isinstance(picker, MultiSelectView)
    session.ui.handle(Key("char", " "))
    press(session, "enter")
    chosen = session.doc.get(("controls", 0, "params", "disabled_rules"))
    rule_ids = [rule_id for rule_id, _ in feed_rules(session.profile.feed)]
    assert rule_ids and all(r.startswith("SIG-") for r in rule_ids)
    assert chosen == rule_ids[:1]


def test_rename_keeps_view_on_control(session: Session) -> None:
    view = open_control(session, "pii")
    go_to(session, "id")
    press(session, "enter")
    for _ in range(5):
        press(session, "backspace")
    type_text(session, "pii.main")
    press(session, "enter")
    assert "pii.main" in ids(session)
    assert top_list(session) is view
    go_to(session, "up")
    press(session, "enter")
    assert ids(session)[0] == "pii.main"
    row = top_list(session).selected
    assert row is not None and row.id == "up"


def test_delete_asks_and_removes(session: Session) -> None:
    go_to(session, "control:canary")
    press(session, "delete")
    assert "canary" in ids(session)
    press(session, "enter")
    assert "canary" not in ids(session)
