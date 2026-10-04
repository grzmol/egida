"""Run screen: start/stop a fake proxy, active policy state, run settings, policy picker."""

from __future__ import annotations

import os
import re
import shutil
import socket
import sys
import time
import webbrowser
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from egida.console import run_screens
from egida.console.document import PolicyDocument
from egida.console.keys import Key
from egida.console.runner import Proxy, RunProfile, load_profile
from egida.console.schema import detector_params
from egida.console.session import Session
from egida.console.theme import ColorMode, Style
from egida.console.widgets import App, Header, InputView, ListView

REPO = Path(__file__).resolve().parents[3]
ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")

# Answers like the proxy: the policy sha256 is taken once at start (like a loaded snapshot);
# argv: host port [last_error]
FAKE_PROXY = r"""
import hashlib, json, os, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
source = os.environ["EGIDA_POLICY"]
with open(source, "rb") as handle:
    sha = hashlib.sha256(handle.read()).hexdigest()
error = sys.argv[3] if len(sys.argv) > 3 else None
print("fake proxy up", flush=True)
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/healthz":
            body = {"status": "ok", "policy_version": 7, "policy_sha256": sha}
        elif self.path == "/api/policy":
            body = {"version": 7, "sha256": sha, "loaded_at": "now", "source": source,
                    "last_error": error}
        else:
            self.send_response(404)
            self.end_headers()
            return
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
    def log_message(self, *args):
        pass
ThreadingHTTPServer((sys.argv[1], int(sys.argv[2])), Handler).serve_forever()
"""


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _make_session(tmp_path: Path, policy: Path) -> Session:
    profile = RunProfile(
        port=_free_port(),
        policy=policy,
        audit=tmp_path / "audit.jsonl",
        feed=REPO / "signatures" / "feed.yaml",
    )
    session = Session(
        doc=PolicyDocument.open(policy),
        profile=profile,
        profile_path=tmp_path / "egida.yaml",
        proxy=Proxy(tmp_path / "logs" / "proxy.log"),
        param_models=detector_params(),
    )
    root = ListView("root", lambda: [])
    session.app = App(
        root,
        style=Style(ColorMode.NONE),
        header=Header("egida", "0", "test", ()),
        footer=lambda width: [],
    )
    run_screens.install(session)
    return session


@pytest.fixture
def session(tmp_path: Path) -> Iterator[Session]:
    policy = tmp_path / "policy.yaml"
    shutil.copy(REPO / "config" / "policy.yaml", policy)
    instance = _make_session(tmp_path, policy)
    yield instance
    instance.proxy.stop(timeout=1.0)


@pytest.fixture
def fake_proxy(monkeypatch: pytest.MonkeyPatch) -> Callable[..., None]:
    def use(*extra: str, code: str = FAKE_PROXY) -> None:
        def command(self: RunProfile) -> list[str]:
            return [sys.executable, "-c", code, self.host, str(self.port), *extra]

        monkeypatch.setattr(RunProfile, "command", command)

    use()
    return use


def _tick_until(session: Session, condition: Callable[[], bool], timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for tick in list(session.ui.ticks):
            tick()
        if condition():
            return True
        time.sleep(0.05)
    return False


def _screen(session: Session) -> str:
    return ANSI.sub("", "\n".join(session.ui.render(120, 40)))


def _open_run(session: Session) -> ListView:
    view = run_screens.run_view(session)
    assert isinstance(view, ListView)
    session.ui.push(view)
    return view


def _press(session: Session, view: ListView, row_id: str) -> None:
    view.select(row_id)
    session.ui.handle(Key("enter"))


def _type(session: Session, text: str) -> None:
    session.ui.handle(Key("ctrl+u"))
    session.ui.handle(Key("ctrl+k"))
    session.ui.handle(Key("paste", text))
    session.ui.handle(Key("enter"))


def test_start_shows_running_and_same_policy_then_stop(
    session: Session, fake_proxy: Callable[..., None], monkeypatch: pytest.MonkeyPatch
) -> None:
    view = _open_run(session)
    port = session.profile.port
    assert run_screens.run_summary(session) == "stopped"

    _press(session, view, "status")
    assert session.proxy.running
    assert _tick_until(session, lambda: run_screens.run_summary(session) == f"running · :{port}")
    assert "same as the file" in _screen(session)
    assert f"proxy :{port}" in run_screens.footer_badge(session)

    opened: list[str] = []
    monkeypatch.setattr(webbrowser, "open", lambda url: opened.append(url) or False)
    _press(session, view, "Open dashboard")
    assert opened == [f"http://127.0.0.1:{port}/dashboard"]
    assert opened[0] in _screen(session)  # the browser did not open: the URL is shown

    _press(session, view, "status")
    assert not session.proxy.running
    assert run_screens.run_summary(session) == "stopped"
    assert "proxy off" in run_screens.footer_badge(session)


def test_active_policy_follows_the_file_on_disk(
    session: Session, fake_proxy: Callable[..., None]
) -> None:
    view = _open_run(session)
    _press(session, view, "status")
    assert _tick_until(session, lambda: "same as the file" in _screen(session))

    policy = session.profile.policy
    policy.write_text(policy.read_text(encoding="utf-8") + "# edited\n", encoding="utf-8")
    assert "reloading…" in _screen(session)

    old = time.time() - 60
    os.utime(policy, (old, old))
    screen = _screen(session)
    assert "differs from the file" in screen
    assert "same as the file" not in screen


def test_rejected_policy_shows_the_proxy_error(
    session: Session, fake_proxy: Callable[..., None]
) -> None:
    fake_proxy("controls.0.threshold: bad value")
    view = _open_run(session)
    _press(session, view, "status")
    assert _tick_until(session, lambda: "rejected: controls.0.threshold" in _screen(session))


def test_unexpected_exit_reports_once(session: Session, fake_proxy: Callable[..., None]) -> None:
    fake_proxy(code="import sys; print('boom', flush=True); sys.exit(3)")
    view = _open_run(session)
    _press(session, view, "status")
    assert _tick_until(session, lambda: "exited with code 3" in _screen(session))
    assert run_screens.run_summary(session) == "exited (code 3)"

    session.ui.handle(Key("down"))  # any key dismisses the box
    for tick in session.ui.ticks:
        tick()
    assert "exited with code 3" not in _screen(session)


def test_port_edit_persists_and_running_proxy_asks_for_restart(
    session: Session, fake_proxy: Callable[..., None]
) -> None:
    view = _open_run(session)
    _press(session, view, "status")
    assert _tick_until(session, lambda: run_screens.run_summary(session).startswith("running"))

    _press(session, view, "port")
    _type(session, "70000")
    assert isinstance(session.ui.top, InputView)  # refused inline, nothing saved
    assert not session.profile_path.exists()

    new_port = _free_port()
    _type(session, str(new_port))
    assert session.ui.top is view
    assert load_profile(session.profile_path).port == new_port
    assert session.profile.port == new_port
    assert "restart to apply" in _screen(session)

    _press(session, view, "restart-needed")
    assert session.proxy.profile == session.profile
    assert _tick_until(
        session, lambda: run_screens.run_summary(session) == f"running · :{new_port}"
    )
    assert "restart to apply" not in _screen(session)


def test_port_taken_by_another_socket_shows_error_box(
    session: Session, fake_proxy: Callable[..., None]
) -> None:
    view = _open_run(session)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", session.profile.port))
        listener.listen()
        _press(session, view, "status")
        screen = _screen(session)
    assert not session.proxy.running
    assert "Cannot start the proxy" in screen
    assert f"Port {session.profile.port}" in screen


def test_autostart_skips_an_invalid_policy_and_says_why(
    session: Session, fake_proxy: Callable[..., None]
) -> None:
    session.doc.set(("version",), "zero")
    problems = len(session.errors())
    assert problems > 0

    run_screens.autostart(session)

    assert not session.proxy.running
    screen = _screen(session)
    assert "Proxy not started" in screen
    assert f"The policy has {problems} problems" in screen


def test_autostart_starts_the_proxy_for_a_valid_policy(
    session: Session, fake_proxy: Callable[..., None]
) -> None:
    run_screens.autostart(session)

    assert session.proxy.profile == session.profile
    assert _tick_until(
        session, lambda: run_screens.run_summary(session) == f"running · :{session.profile.port}"
    )


def test_autostart_on_a_taken_port_shows_error_box(
    session: Session, fake_proxy: Callable[..., None]
) -> None:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", session.profile.port))
        listener.listen()
        run_screens.autostart(session)
        screen = _screen(session)
    assert not session.proxy.running
    assert "Cannot start the proxy" in screen
    assert f"Port {session.profile.port}" in screen


def test_logs_start_at_the_end_and_show_read_errors(session: Session) -> None:
    log = session.proxy.log_path
    log.parent.mkdir(parents=True)
    log.write_text("".join(f"line {i}\n" for i in range(1000)), encoding="utf-8")
    view = _open_run(session)
    _press(session, view, "Logs")
    screen = _screen(session)
    assert "line 999" in screen
    assert "line 600 " not in screen

    log.unlink()
    log.mkdir()  # unreadable as a file: the error is shown instead of crashing
    assert "Cannot read the log" in _screen(session)


@pytest.fixture
def repo_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    config = tmp_path / "config"
    config.mkdir()
    shutil.copy(REPO / "config" / "policy.yaml", config / "policy.yaml")
    shutil.copy(REPO / "config" / "policy.lenient.yaml", config / "policy.lenient.yaml")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_policy_picker_confirms_discarding_unsaved_edits(repo_dir: Path) -> None:
    session = _make_session(repo_dir, Path("config/policy.yaml"))
    session.doc.set(("version",), 99)
    assert session.doc.dirty

    def pick_lenient() -> None:
        session.ui.push(run_screens.policy_picker(session))
        session.ui.handle(Key("home"))  # options are sorted: policy.lenient.yaml first
        session.ui.handle(Key("enter"))

    pick_lenient()
    session.ui.handle(Key("escape"))  # cancel the discard question
    assert session.doc.path == Path("config/policy.yaml")
    assert session.doc.get(("version",)) == 99

    pick_lenient()
    session.ui.handle(Key("enter"))  # "Discard and open"
    assert session.doc.path == Path("config/policy.lenient.yaml")
    assert not session.doc.dirty
    assert session.profile.policy == Path("config/policy.lenient.yaml")
    assert load_profile(session.profile_path).policy == Path("config/policy.lenient.yaml")
