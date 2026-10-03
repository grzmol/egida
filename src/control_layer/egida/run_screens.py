"""Egida's Run screen: start, stop and watch the proxy, edit the run profile, read its log.

The proxy is probed from the app's ticks (never while rendering): every ~1.5 s while Egida's
proxy runs, every ~5 s otherwise (to notice another process on the configured address). One
probe blocks the UI for at most `_PROBE_TIMEOUT_S`.
"""

from __future__ import annotations

import hashlib
import re
import time
import weakref
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final
from urllib.parse import urlsplit

from control_layer.egida.document import DocumentError
from control_layer.egida.keys import Key
from control_layer.egida.runner import Health, ProxyError, RunProfile
from control_layer.egida.session import Session
from control_layer.egida.widgets import (
    App,
    Choice,
    ConfirmView,
    InputView,
    ListView,
    Option,
    Row,
    RowTone,
    SelectView,
    TextView,
    View,
)

__all__ = ["footer_badge", "install", "policy_picker", "run_summary", "run_view"]

_PROBE_TIMEOUT_S: Final = 0.3  # whole probe; Proxy.health makes two requests
_RUNNING_INTERVAL_S: Final = 1.5
_STOPPED_INTERVAL_S: Final = 5.0
_RELOAD_WINDOW_S: Final = 3.0  # the proxy checks the file about every second
_LOG_LINES: Final = 400
_POLICY_GLOB: Final = "config/policy*.yaml"
_OTHER_FILE: Final = "\x00other"  # option value that cannot be a path
_ESCAPES: Final = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


@dataclass
class _RunState:
    """What the ticks learned about the proxy; the screens only read it."""

    health: Health | None = None
    probed_at: float | None = None  # None: probe on the next tick
    answered: bool = False  # Egida's proxy answered /healthz since it was started
    watching: bool = False  # Egida's proxy was started and has not been stopped by Egida
    installed: bool = False


_STATES: dict[int, _RunState] = {}


def _state(session: Session) -> _RunState:
    key = id(session)
    state = _STATES.get(key)
    if state is None:
        state = _STATES[key] = _RunState()
        weakref.finalize(session, _STATES.pop, key, None)
    return state


# ── ticks ────────────────────────────────────────────────────────────────────


def install(session: Session) -> None:
    """Register the health probe and exit detection on the session's app (once)."""
    state = _state(session)
    if state.installed:
        return
    state.installed = True
    session.ui.ticks.append(lambda: _tick(session))


def _tick(session: Session) -> None:
    state, proxy = _state(session), session.proxy
    running = proxy.running
    if state.watching and not running:
        state.watching = False
        state.answered = False
        state.health = None
        state.probed_at = None
        code = proxy.exit_code
        if code is not None:
            session.ui.notify(
                "error",
                f"The proxy exited with code {code}",
                "Open Logs in Run to see why, then start it again.",
            )
    now = time.monotonic()
    interval = _RUNNING_INTERVAL_S if running else _STOPPED_INTERVAL_S
    if state.probed_at is not None and now - state.probed_at < interval:
        return
    state.probed_at = now
    target = proxy.profile or session.profile
    state.health = proxy.health(target, timeout=_PROBE_TIMEOUT_S / 2)
    if running and state.health is not None:
        state.answered = True


# ── status ───────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class _Status:
    kind: str  # running starting silent stopped exited foreign
    port: int
    code: int | None = None


def _status(session: Session) -> _Status:
    state, proxy = _state(session), session.proxy
    profile = proxy.profile
    if profile is not None:
        if state.health is not None:
            return _Status("running", profile.port)
        return _Status("silent" if state.answered else "starting", profile.port)
    code = proxy.exit_code
    if code is not None:
        return _Status("exited", session.profile.port, code)
    if state.health is not None:
        return _Status("foreign", session.profile.port)
    return _Status("stopped", session.profile.port)


def run_summary(session: Session) -> str:
    """One-line proxy state for the root list ("running · :8080", "stopped", …)."""
    status = _status(session)
    match status.kind:
        case "running":
            return f"running · :{status.port}"
        case "starting":
            return f"starting… · :{status.port}"
        case "silent":
            return f"not answering · :{status.port}"
        case "exited":
            return f"exited (code {status.code})"
        case "foreign":
            return f"other process on :{status.port}"
    return "stopped"


def footer_badge(session: Session) -> str:
    """Styled proxy badge for the footer's right side."""
    style = session.ui.style
    status = _status(session)
    match status.kind:
        case "running":
            return style.fg("success", f"● proxy :{status.port}")
        case "starting" | "silent":
            return style.fg("warning", f"◐ proxy :{status.port}")
        case "foreign":
            return style.fg("warning", f"● :{status.port} (not Egida)")
    return style.fg("dim", "○ proxy off")


_STATUS_TONES: Final[dict[str, RowTone]] = {
    "running": "success",
    "starting": "warning",
    "silent": "warning",
    "exited": "error",
    "foreign": "warning",
    "stopped": "muted",
}


def _status_help(status: _Status) -> str:
    match status.kind:
        case "running":
            return "Enter stops the proxy. Egida also stops it when you quit."
        case "starting":
            return "Waiting for /healthz; detector models can take a few seconds to load."
        case "silent":
            return "The process runs but /healthz does not answer; open Logs to see why."
        case "exited":
            return "Open Logs to see why it stopped, then press Enter to start it again."
        case "foreign":
            return (
                f"Another process (make run, another Egida) answers on :{status.port}. "
                "Stop it there or change Port to start one here."
            )
    return "Enter starts the proxy with the settings below; its output goes to Logs."


# ── actions ──────────────────────────────────────────────────────────────────


def _start(session: Session) -> None:
    try:
        session.proxy.start(session.profile)
    except ProxyError as exc:
        session.ui.notify("error", "Cannot start the proxy", str(exc))
        return
    _started(session)


def _restart(session: Session) -> None:
    try:
        session.proxy.restart(session.profile)
    except ProxyError as exc:
        _stopped(session)
        session.ui.notify("error", "Cannot restart the proxy", str(exc))
        return
    _started(session)


def _stop(session: Session) -> None:
    session.proxy.stop()
    _stopped(session)


def _started(session: Session) -> None:
    state = _state(session)
    state.watching, state.answered, state.health, state.probed_at = True, False, None, None


def _stopped(session: Session) -> None:
    state = _state(session)
    state.watching, state.answered, state.health, state.probed_at = False, False, None, None


def _toggle(session: Session) -> None:
    if session.proxy.running:
        _stop(session)
    else:
        _start(session)


def _open_dashboard(session: Session) -> None:
    status = _status(session)
    if status.kind in ("stopped", "exited"):
        session.ui.notify(
            "error", "The proxy is not running", "Start it from Run, then open the dashboard."
        )
        return
    profile = session.proxy.profile or session.profile
    url = profile.base_url + "/dashboard"
    try:
        opened = webbrowser.open(url)
    except webbrowser.Error:
        opened = False
    if not opened:
        session.ui.notify("info", "Open the dashboard in a browser", url)


# ── active policy ────────────────────────────────────────────────────────────


def _same_path(a: Path, b: Path) -> bool:
    return a.expanduser().resolve() == b.expanduser().resolve()


def _active_policy(session: Session) -> tuple[str, RowTone, str]:
    """Value, tone and help of the "Active policy" row."""
    health = _state(session).health
    if health is None:
        return "-", "muted", "Shows the policy the running proxy enforces."
    source = Path(health.policy_source)
    switch = "" if _same_path(source, session.profile.policy) else " · restart to switch"
    head = f"v{health.policy_version} · {health.policy_sha256[:8]}"
    if health.policy_error is not None:
        return (
            f"rejected: {health.policy_error}",
            "error",
            f"The proxy rejected the last change to {source} and keeps {head}. "
            "Fix the problems on the main screen and save again.",
        )
    try:
        data = source.read_bytes()
        changed_at = source.stat().st_mtime
    except OSError:
        return (
            f"{head} · file unreadable{switch}",
            "warning",
            f"Egida cannot read {source} to compare it with what the proxy runs.",
        )
    other = f" It runs {source}; the profile points at {session.profile.policy}." if switch else ""
    if hashlib.sha256(data).hexdigest() == health.policy_sha256:
        return (
            f"{head} · same as the file{switch}",
            "warning" if switch else "success",
            f"The proxy enforces {source} as it is on disk.{other}",
        )
    if time.time() - changed_at < _RELOAD_WINDOW_S:
        return f"reloading…{switch}", "warning", "The proxy picks up a saved file within ~1 s."
    return (
        f"{head} · differs from the file{switch}",
        "warning",
        f"{source} changed but the proxy still runs {head}; open Logs to see why.{other}",
    )


# ── settings ─────────────────────────────────────────────────────────────────


def _update(session: Session, **changes: object) -> None:
    session.update_profile(**changes)  # ValueError → shown inline by the InputView
    _state(session).probed_at = None  # the address may have changed: probe on the next tick


def _parse_port(text: str) -> int:
    try:
        return int(text.strip())
    except ValueError:
        raise ValueError("Enter a whole number from 1 to 65535, for example 8080.") from None


def _parse_path(text: str) -> Path:
    if not text.strip():
        raise ValueError("Enter a path; relative paths start at the repository root.")
    return Path(text.strip())


def _parse_host(text: str) -> str:
    host = text.strip()
    if not host or any(ch.isspace() for ch in host):
        raise ValueError("Enter one host name or IP address, for example 127.0.0.1.")
    return host


def _parse_url(text: str) -> str:
    url = text.strip()
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise ValueError("Enter an http:// or https:// URL, for example http://127.0.0.1:11434.")
    return url


def _setting_row(
    session: Session,
    field: str,
    label: str,
    help_text: str,
    parse: Callable[[str], object],
    *,
    tone: RowTone = "normal",
) -> Row:
    current = str(getattr(session.profile, field))

    def edit() -> None:
        session.ui.push(
            InputView(
                label,
                help_text,
                current,
                lambda text: _update(session, **{field: parse(text)}),
            )
        )

    return Row(label, current, help_text, edit, tone=tone, id=field)


def _profile_changes(running: RunProfile, wanted: RunProfile) -> list[str]:
    old, new = running.model_dump(), wanted.model_dump()
    return [f"{name} {old[name]} → {new[name]}" for name in new if old[name] != new[name]]


# ── views ────────────────────────────────────────────────────────────────────


def run_view(session: Session) -> View:
    """The Run screen: proxy status and actions, active policy, run settings, logs."""

    def rows() -> list[Row]:
        proxy, profile = session.proxy, session.profile
        status = _status(session)
        out = [
            Row(
                "Proxy",
                run_summary(session),
                _status_help(status),
                lambda: _toggle(session),
                tone=_STATUS_TONES[status.kind],
                id="status",
            )
        ]
        if proxy.running:
            out.append(Row("Stop proxy", "", "Stops the proxy (SIGTERM).", lambda: _stop(session)))
            out.append(
                Row(
                    "Restart proxy",
                    "",
                    "Stops it and starts it again with the settings below.",
                    lambda: _restart(session),
                )
            )
        else:
            out.append(
                Row(
                    "Start proxy",
                    profile.base_url,
                    "Starts the proxy with the settings below; output goes to Logs.",
                    lambda: _start(session),
                )
            )
        value, tone, help_text = _active_policy(session)
        out.append(Row("Active policy", value, help_text, tone=tone, id="active"))
        loopback = profile.is_loopback()
        host_help = (
            "Address the proxy listens on. 127.0.0.1 keeps it on this machine."
            if loopback
            else "Reachable from the network, and the operator endpoints (/api/*, /dashboard) "
            "have no authentication. Use 127.0.0.1 unless you need remote access."
        )
        out += [
            _setting_row(
                session,
                "host",
                "Host",
                host_help,
                _parse_host,
                tone="normal" if loopback else "warning",
            ),
            _setting_row(
                session,
                "port",
                "Port",
                "TCP port of the proxy; agents call http://host:port/v1.",
                _parse_port,
            ),
            Row(
                "Policy file",
                str(profile.policy),
                "Policy the proxy loads (CONTROL_LAYER_POLICY); Egida edits the same file.",
                lambda: session.ui.push(policy_picker(session)),
                id="policy",
            ),
            _setting_row(
                session,
                "audit",
                "Audit log",
                "JSONL file with one line per decision (CONTROL_LAYER_AUDIT).",
                _parse_path,
            ),
            _setting_row(
                session,
                "feed",
                "Signature feed",
                "Rules of the signature control, hot-reloaded (CONTROL_LAYER_FEED).",
                _parse_path,
            ),
            _setting_row(
                session,
                "guard_url",
                "Guard URL",
                "Ollama server of the harmful_content guard model (CONTROL_LAYER_GUARD_URL).",
                _parse_url,
            ),
            _setting_row(
                session,
                "models_dir",
                "Models dir",
                "Directory with the prompt_guard ONNX model (CONTROL_LAYER_MODELS_DIR).",
                _parse_path,
            ),
        ]
        running_profile = proxy.profile
        if running_profile is not None and running_profile != profile:
            changes = "; ".join(_profile_changes(running_profile, profile))
            out.append(
                Row(
                    "Settings changed",
                    "restart to apply",
                    f"The proxy still runs with the old settings ({changes}). Enter restarts it.",
                    lambda: _restart(session),
                    tone="warning",
                    id="restart-needed",
                )
            )
        out += [
            Row(
                "Logs",
                str(proxy.log_path),
                "Output of the proxy started here, newest at the bottom.",
                lambda: session.ui.push(_LogView(session)),
            ),
            Row(
                "Open dashboard",
                (proxy.profile or profile).base_url + "/dashboard",
                "Opens the live dashboard in your browser.",
                lambda: _open_dashboard(session),
            ),
        ]
        return out

    return ListView("Run", rows, subtitle=lambda: session.profile.base_url)


class _LogView:
    """The proxy log in a TextView, re-read on every render. It follows the end until the user
    scrolls up; End follows again."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._lines: list[str] = []
        self._follow = True
        log_path = session.proxy.log_path
        self._text = TextView(
            "Proxy log",
            lambda width: self._lines,
            subtitle=lambda: run_summary(session),
            hint=f"{log_path} · ↑↓ scroll · End to follow · Esc to go back",
        )

    def render(self, app: App, width: int, height: int) -> list[str]:
        self._lines = self._read(app)
        lines = self._text.render(app, width, height)
        if self._follow:
            self._text.handle(app, Key("end"))
            lines = self._text.render(app, width, height)
        return lines

    def handle(self, app: App, key: Key) -> None:
        if key.name in ("escape", "ctrl+c"):
            app.remove(self)
            return
        if key.name in ("up", "pageup", "home"):
            self._follow = False
        elif key.name == "end":
            self._follow = True
        self._text.handle(app, key)

    def _read(self, app: App) -> list[str]:
        style = app.style
        try:
            lines = self._session.proxy.log_tail(_LOG_LINES)
        except ProxyError as exc:
            return [style.fg("error", str(exc))]
        if not lines:
            return [style.fg("dim", "No output yet. Start the proxy to see its log here.")]
        return [_printable(line) for line in lines]


def _printable(line: str) -> str:
    text = _ESCAPES.sub("", line).expandtabs(4)
    return "".join(ch if ch.isprintable() else " " for ch in text)


# ── policy picker ────────────────────────────────────────────────────────────


def policy_picker(session: Session) -> View:
    """Choose the policy file to edit and run: config/policy*.yaml, the open file, or a path."""
    current = session.doc.path
    paths = sorted(Path().glob(_POLICY_GLOB))
    if not any(_same_path(path, current) for path in paths):
        paths.insert(0, current)
    options = [
        Option(str(path), str(path), "open now" if _same_path(path, current) else "")
        for path in paths
    ]
    options.append(Option(_OTHER_FILE, "Other file…", "type a path"))

    def chosen(value: str) -> None:
        if value == _OTHER_FILE:
            session.ui.push(
                InputView(
                    "Policy file",
                    "Path of a policy YAML file; relative paths start at the repository root.",
                    str(current),
                    lambda text: _switch(session, _parse_path(text)),
                )
            )
        else:
            _switch(session, Path(value))

    return SelectView(
        "Policy file",
        "Egida edits this file and the proxy loads it (CONTROL_LAYER_POLICY).",
        options,
        str(current),
        chosen,
    )


def _switch(session: Session, path: Path) -> None:
    if _same_path(path, session.doc.path):
        return
    if not session.doc.dirty:
        _open(session, path)
        return
    session.ui.push(
        ConfirmView(
            "Discard unsaved changes?",
            f"Your edits to {session.doc.path} are lost when {path} opens.",
            [
                Choice(
                    f"Discard and open {path}",
                    lambda: _open(session, path),
                    tone="danger",
                ),
                Choice("Cancel", lambda: None, "keep editing the current file"),
            ],
        )
    )


def _open(session: Session, path: Path) -> None:
    try:
        session.open_policy(path)
    except (DocumentError, ValueError) as exc:
        session.ui.notify("error", f"Cannot open {path}", str(exc))
        return
    _state(session).probed_at = None
    body = (
        "Restart the proxy from Run to use it."
        if session.proxy.running
        else "Start the proxy from Run to use it."
    )
    session.ui.notify("success", f"Opened {path}", body)
