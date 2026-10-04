"""The setup wizard driven by keys over a policy copy, a fake home and fake harnesses."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from collections.abc import Sequence
from pathlib import Path
from typing import ClassVar, Literal

import pytest

from egida.console import run_screens
from egida.console.document import PolicyDocument
from egida.console.harnesses.base import (
    Change,
    Endpoint,
    Harness,
    HarnessEnv,
    HarnessError,
    Mode,
)
from egida.console.harnesses.base import Protocol as HarnessProtocol
from egida.console.keys import Key
from egida.console.runner import Proxy, RunProfile, load_profile
from egida.console.schema import detector_params
from egida.console.session import Session
from egida.console.theme import ColorMode, Style
from egida.console.widgets import App, Header, InputView, ListView, TextView
from egida.console.wizard import wizard_view

REPO = Path(__file__).resolve().parents[3]
PLAIN = Style(ColorMode.NONE)
_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


class _FileHarness(Harness):
    """Writes `~/.<id>.json` with the endpoint; enabled while that file exists."""

    protocol: ClassVar[HarnessProtocol | None] = "openai-chat"
    mode: ClassVar[Mode] = "config"
    note = "fake harness"
    binaries = ("fake",)

    def _path(self, env: HarnessEnv) -> Path:
        return env.home / f".{self.id}.json"

    def config_paths(self, env: HarnessEnv) -> tuple[Path, ...]:
        return (self._path(env),)

    def enabled(self, env: HarnessEnv) -> bool:
        return self._path(env).exists()

    def plan(self, env: HarnessEnv, endpoint: Endpoint) -> list[Change]:
        action: Literal["create", "update"] = "update" if self._path(env).exists() else "create"
        return [Change(self._path(env), action, f"point {self.name} at {endpoint.base_url}")]

    def apply(self, env: HarnessEnv, endpoint: Endpoint) -> list[Change]:
        changes = self.plan(env, endpoint)
        data = {"base": endpoint.base_url, "key": endpoint.key, "model": endpoint.model}
        self._path(env).write_text(json.dumps(data))
        return changes

    def plan_remove(self, env: HarnessEnv) -> list[Change]:
        return [Change(self._path(env), "delete", "drop Egida's file")]

    def remove(self, env: HarnessEnv) -> list[Change]:
        changes = self.plan_remove(env)
        self._path(env).unlink()
        return changes


class Alpha(_FileHarness):
    id = "alpha"
    name = "Alpha Code"


class Broken(_FileHarness):
    id = "broken"
    name = "Broken CLI"

    def apply(self, env: HarnessEnv, endpoint: Endpoint) -> list[Change]:
        raise HarnessError("~/.broken.json is not valid JSON")


class Launcher(_FileHarness):
    id = "launcher"
    name = "Launcher CLI"
    mode = "launch"


class Nope(_FileHarness):
    id = "nope"
    name = "Nope IDE"
    mode = "unavailable"
    protocol = None
    note = "Nope IDE has no custom endpoint."


REGISTRY: Sequence[Harness] = (Alpha(), Broken(), Launcher(), Nope())


@pytest.fixture
def env(tmp_path: Path) -> HarnessEnv:
    home = tmp_path / "home"
    home.mkdir()
    return HarnessEnv(
        home=home,
        config_dir=home / ".config" / "egida",
        environ={},
        which=lambda name: f"/usr/bin/{name}",
    )


@pytest.fixture
def session(tmp_path: Path, env: HarnessEnv, monkeypatch: pytest.MonkeyPatch) -> Session:
    monkeypatch.chdir(tmp_path)
    policy = tmp_path / "policy.yaml"
    shutil.copyfile(REPO / "config" / "policy.yaml", policy)
    session = Session(
        doc=PolicyDocument.open(policy),
        profile=RunProfile(policy=policy, port=1),
        profile_path=tmp_path / "egida.yaml",
        proxy=Proxy(log_path=tmp_path / "proxy.log"),
        param_models=detector_params(),
        harness_env=env,
    )
    session.app = App(
        ListView("root", list),
        style=PLAIN,
        header=Header("egida", "test", "", ()),
        footer=lambda width: [],
    )
    return session


@pytest.fixture
def started(monkeypatch: pytest.MonkeyPatch) -> list[RunProfile]:
    calls: list[RunProfile] = []
    monkeypatch.setattr(run_screens, "_start", lambda s: calls.append(s.profile))
    monkeypatch.setattr(run_screens, "_restart", lambda s: calls.append(s.profile))
    return calls


def press(app: App, *names: str) -> None:
    for name in names:
        app.handle(Key(name))


def space(app: App) -> None:
    app.handle(Key("char", " "))


def type_text(app: App, text: str) -> None:
    for ch in text:
        app.handle(Key("char", ch))


def screen(app: App) -> str:
    return "\n".join(_ANSI.sub("", line) for line in app.render(110, 40))


def select(app: App, row_id: str) -> None:
    view = app.top
    inner = view._view() if hasattr(view, "_view") else view  # the wizard's current ListView
    assert isinstance(inner, ListView)
    inner.select(row_id)
    assert inner.selected is not None and (inner.selected.id or inner.selected.label) == row_id


def open_wizard(session: Session, **kwargs: object) -> list[str]:
    done: list[str] = []
    session.ui.push(
        wizard_view(session, on_done=lambda: done.append("done"), registry=REGISTRY, **kwargs)  # type: ignore[arg-type]
    )
    return done


def _sha(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def test_happy_path_writes_policy_harness_files_profile_and_starts_proxy(
    session: Session, env: HarnessEnv, started: list[RunProfile]
) -> None:
    app = session.ui
    done = open_wizard(session)
    assert "Step 1 of 6" in screen(app)

    press(app, "enter")  # welcome
    assert "Step 2 of 6" in screen(app) and "http://127.0.0.1:11434/v1" in screen(app)
    press(app, "enter")  # llama3.2:3b, the only model
    assert "Step 3 of 6" in screen(app)
    for harness_id in ("alpha", "broken", "launcher"):
        select(app, harness_id)
        space(app)
    press(app, "enter")
    assert "Step 4 of 6" in screen(app)
    select(app, "port")
    press(app, "enter")
    press(app, "backspace")
    type_text(app, "9131")
    press(app, "enter")
    select(app, "\x00continue")
    press(app, "enter")

    review = screen(app)
    assert "Step 5 of 6" in review
    assert "add agent alpha with a new key" in review
    assert "Alpha Code: create ~/.alpha.json" in review
    assert "start with egd launch launcher" in review
    assert not (env.home / ".alpha.json").exists()

    press(app, "enter")  # apply

    result = screen(app)
    assert "Step 6 of 6" in result
    assert "ok · start with: fake" in result
    assert "ok · start with: egd launch launcher" in result
    assert "failed" in result  # Broken: error collected, the rest went on
    written = json.loads((env.home / ".alpha.json").read_text())
    assert written["base"] == "http://127.0.0.1:9131"
    assert written["key"].startswith("sk-egida-")
    on_disk = PolicyDocument.open(session.doc.path)
    assert on_disk.get(("agents", "alpha", "key_sha256")) == _sha(written["key"])
    assert on_disk.get(("agents", "broken", "budget")) == "harness"
    assert on_disk.get(("budgets", "harness", "max_requests")) == 5000
    assert on_disk.get(("limits", "max_tokens")) == 32000
    assert load_profile(session.profile_path).port == 9131
    assert [profile.port for profile in started] == [9131]

    press(app, "enter")
    assert done == ["done"] and not isinstance(app.top, TextView)
    assert app.top is not None and len(app._stack) == 1


def test_unchecking_removes_agent_and_config(
    session: Session, env: HarnessEnv, started: list[RunProfile]
) -> None:
    app = session.ui
    open_wizard(session, start="harnesses")
    select(app, "alpha")
    space(app)
    press(app, "enter")
    press(app, "up", "enter")  # Continue is the last row
    press(app, "enter")
    assert (env.home / ".alpha.json").exists()
    press(app, "enter")  # close

    open_wizard(session, start="harnesses")
    assert "✓ Alpha Code" in screen(app)  # pre-checked: enabled now
    select(app, "alpha")
    space(app)
    press(app, "enter")
    press(app, "up", "enter")
    assert "Alpha Code: delete ~/.alpha.json" in screen(app)
    assert "remove agent alpha" in screen(app)
    press(app, "enter")

    assert "removed" in screen(app)
    assert not (env.home / ".alpha.json").exists()
    assert "alpha" not in PolicyDocument.open(session.doc.path).names("agents")


def test_unavailable_rows_cannot_be_toggled(session: Session) -> None:
    app = session.ui
    open_wizard(session, start="harnesses")
    select(app, "nope")
    space(app)

    text = screen(app)
    assert "✓" not in text
    assert "unavailable" in text and "Nope IDE has no custom endpoint." in text


def test_first_run_escape_saves_the_default_profile(session: Session) -> None:
    app = session.ui
    done = open_wizard(session, first_run=True)
    press(app, "escape")

    assert done == ["done"]
    assert session.profile_path.exists()
    assert load_profile(session.profile_path) == session.profile


def test_escape_goes_one_step_back(session: Session) -> None:
    app = session.ui
    done = open_wizard(session)
    press(app, "enter", "enter")
    assert "Step 3 of 6" in screen(app)
    press(app, "escape")
    assert "Step 2 of 6" in screen(app)
    press(app, "escape", "escape")
    assert done == ["done"]
    assert not session.profile_path.exists()  # not a first run: nothing saved


def test_add_model_then_review_shows_new_model_and_diff(
    session: Session, started: list[RunProfile]
) -> None:
    app = session.ui
    open_wizard(session)
    press(app, "enter")
    select(app, "\x00add-model")
    press(app, "enter")
    assert isinstance(app.top, InputView)
    type_text(app, "qwen3-coder:30b")
    press(app, "enter")
    select(app, "alpha")
    space(app)
    press(app, "enter")
    press(app, "up", "enter")

    assert "add model qwen3-coder:30b (upstream ollama, price 0)" in screen(app)
    app.handle(Key("char", "d"))
    assert isinstance(app.top, TextView)
    assert "+  alpha:" in screen(app)
    press(app, "escape")
    press(app, "enter")
    on_disk = PolicyDocument.open(session.doc.path)
    assert on_disk.get(("models", "qwen3-coder:30b", "upstream")) == "ollama"


def test_policy_conflict_stops_on_review(session: Session, env: HarnessEnv) -> None:
    app = session.ui
    open_wizard(session, start="harnesses")
    select(app, "alpha")
    space(app)
    press(app, "enter")
    press(app, "up", "enter")
    session.doc.path.write_text(session.doc.path.read_text() + "\n# edited elsewhere\n")

    press(app, "enter")

    text = screen(app)
    assert "Step 5 of 6" in text and "The policy was not saved" in text
    assert not (env.home / ".alpha.json").exists()


def test_real_claude_code_and_opencode(
    session: Session, env: HarnessEnv, started: list[RunProfile]
) -> None:
    app = session.ui
    session.ui.push(wizard_view(session, start="harnesses", on_done=lambda: None))
    for harness_id in ("claude-code", "opencode"):
        select(app, harness_id)
        space(app)
    press(app, "enter")
    press(app, "up", "enter")
    press(app, "enter")

    assert "ok · start with: claude" in screen(app)
    claude = json.loads((env.home / ".claude" / "settings.json").read_text())
    key = claude["env"]["ANTHROPIC_AUTH_TOKEN"]
    assert claude["env"]["ANTHROPIC_BASE_URL"] == "http://127.0.0.1:1"
    opencode = json.loads((env.home / ".config" / "opencode" / "opencode.json").read_text())
    assert opencode["model"] == "egida/llama3.2:3b"
    on_disk = PolicyDocument.open(session.doc.path)
    assert on_disk.get(("agents", "claude-code", "key_sha256")) == _sha(key)
    assert on_disk.get(("agents", "opencode", "allowed_tools")) == ["*"]
    assert on_disk.get(("limits", "max_input_chars")) == 2_000_000
    assert len(started) == 1
