"""The setup wizard: pick a model and the coding harnesses that should go through the proxy, then
Egida writes one policy agent per harness, rewrites the harness configs and starts the proxy.

Six steps in one view (Welcome, Model, Harnesses, Proxy address, Review, Result); Esc goes one
step back and closes the wizard on its first step.
"""

from __future__ import annotations

import difflib
import secrets
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from typing import Final, Literal

from pydantic import ValidationError

from egida.console import run_screens
from egida.console.document import DocumentError, PolicyDocument
from egida.console.harness_policy import apply_policy, plan_policy
from egida.console.harnesses import REGISTRY
from egida.console.harnesses.base import (
    Change,
    Endpoint,
    Harness,
    HarnessEnv,
    HarnessError,
    HarnessState,
    display_path,
)
from egida.console.keys import Key
from egida.console.runner import RunProfile
from egida.console.session import Session
from egida.console.widgets import App, InputView, ListView, Row, TextView, View, diff_lines

__all__ = ["new_key", "start_command", "wizard_view"]

_STEPS: Final = 6
_WELCOME, _MODEL, _HARNESSES, _ADDRESS, _REVIEW, _RESULT = range(1, 7)
_TITLES: Final = {
    _WELCOME: "Set up Egida",
    _MODEL: "Model",
    _HARNESSES: "Harnesses",
    _ADDRESS: "Proxy address",
    _REVIEW: "Review",
    _RESULT: "Done",
}
_ADD_MODEL: Final = "\x00add-model"  # row id that cannot be a model name
_CONTINUE: Final = "\x00continue"
# config harnesses that also start through `egd launch`
_START_HINTS: Final = {
    "gemini-cli": "gemini (in trusted folders) or egd launch gemini-cli",
}


def new_key() -> str:
    """A fresh API key for one harness agent."""
    return "sk-egida-" + secrets.token_urlsafe(24)


def start_command(harness: Harness) -> str:
    """How the user starts the harness once Egida configured it."""
    if harness.mode == "launch":
        return f"egd launch {harness.id}"
    if harness.id in _START_HINTS:
        return _START_HINTS[harness.id]
    if harness.binaries:
        return harness.binaries[0]
    return f"open {harness.name}"


@dataclass
class _Outcome:
    harness: Harness
    action: Literal["apply", "remove"]
    error: str | None = None
    changes: list[Change] = field(default_factory=list)


@dataclass
class _Preview:
    policy: list[str]
    files: list[tuple[str, str]]  # (label, help)
    problems: list[str]
    diff: list[str]


class _Wizard:
    """One View that renders the ListView of the current step."""

    def __init__(
        self,
        session: Session,
        *,
        start: Literal["welcome", "harnesses"],
        first_run: bool,
        on_done: Callable[[], None],
        registry: Sequence[Harness],
    ) -> None:
        self._session = session
        self._first = _WELCOME if start == "welcome" else _HARNESSES
        self._first_run = first_run
        self._on_done = on_done
        self._registry = tuple(registry)
        self._step = self._first
        self._states = self._read_states()
        self._enabled = {h.id for h in self._registry if self._states[h.id].enabled}
        self._checked = set(self._enabled)
        self._model = self._initial_model()
        self._host = session.profile.host
        self._port = session.profile.port
        self._keys: dict[str, str] = {}
        self._preview: _Preview | None = None
        self._outcomes: list[_Outcome] = []
        self._proxy_note = ""
        self._views: dict[int, ListView] = {}

    # ── state ────────────────────────────────────────────────────────────────

    def _read_states(self) -> dict[str, HarnessState]:
        env = self._session.harness_env
        states: dict[str, HarnessState] = {}
        for harness in self._registry:
            try:
                states[harness.id] = harness.state(env)
            except (HarnessError, OSError) as exc:
                states[harness.id] = HarnessState(installed=False, enabled=False, detail=str(exc))
        return states

    def _initial_model(self) -> str:
        doc = self._session.doc
        models = doc.names("models")
        for harness in self._registry:
            allowed = doc.get(("agents", harness.id, "allowed_models"))
            if isinstance(allowed, list) and allowed and str(allowed[0]) in models:
                return str(allowed[0])
        return models[0] if models else ""

    def _selected(self) -> list[Harness]:
        return [h for h in self._registry if h.id in self._checked and h.mode != "unavailable"]

    def _removed(self) -> list[Harness]:
        return [h for h in self._registry if h.id in self._enabled and h.id not in self._checked]

    def _upstream_url(self, model: str) -> str:
        doc = self._session.doc
        upstream = doc.get(("models", model, "upstream"))
        if upstream is None:
            names = doc.names("upstreams")
            upstream = names[0] if names else None
        if upstream is None:
            return "no upstream"
        url = doc.get(("upstreams", str(upstream), "base_url"), "")
        return f"{upstream} · {url}" if url else str(upstream)

    # ── View ─────────────────────────────────────────────────────────────────

    @property
    def step(self) -> int:
        return self._step

    def render(self, app: App, width: int, height: int) -> list[str]:
        return self._view().render(app, width, height)

    def handle(self, app: App, key: Key) -> None:
        if key.name == "enter" and self._step == _HARNESSES:
            self._go(_ADDRESS)
            return
        if key.name == "enter" and self._step == _REVIEW:
            self._apply()
            return
        if self._step == _RESULT and key.name in ("enter", "escape", "ctrl+c"):
            self._close(save_profile=False)
            return
        self._view().handle(app, key)

    def _view(self) -> ListView:
        view = self._views.get(self._step)
        if view is None:
            view = self._views[self._step] = self._build(self._step)
        return view

    def _subtitle(self, text: str) -> str:
        return f"Step {self._step} of {_STEPS} · {text}"

    def _go(self, step: int) -> None:
        if step == _REVIEW:
            self._prepare_review()
        self._views.pop(step, None)
        self._step = step

    def _back(self) -> None:
        if self._step == self._first:
            self._close(save_profile=self._first_run)
        else:
            self._go(self._step - 1)

    def _close(self, *, save_profile: bool) -> None:
        ui = self._session.ui
        ui.remove(self)
        if save_profile:  # the default profile file marks the first run as done
            try:
                self._session.update_profile()
            except ValueError as exc:
                ui.notify("error", "Cannot save the run profile", str(exc))
        self._on_done()

    def _build(self, step: int) -> ListView:
        title = _TITLES[step]
        match step:
            case 1:
                return ListView(
                    title,
                    self._welcome_rows,
                    subtitle=lambda: self._subtitle(
                        "Route coding harnesses (Claude Code, Codex, Gemini CLI, ...) through "
                        "the Egida proxy so every request passes the policy."
                    ),
                    hint="Enter to start · Esc to close",
                    on_back=self._back,
                )
            case 2:
                view = ListView(
                    title,
                    self._model_rows,
                    subtitle=lambda: self._subtitle(
                        "The model every selected harness uses through the proxy."
                    ),
                    hint="Enter to choose · Esc to go back",
                    on_back=self._back,
                )
                if self._model:
                    view.select(self._model)
                return view
            case 3:
                return ListView(
                    title,
                    self._harness_rows,
                    subtitle=lambda: self._subtitle(
                        "Checked harnesses get their own policy agent and key, and their "
                        "config points at the proxy."
                    ),
                    hint="Space to toggle · Enter to continue · Esc to go back",
                    on_back=self._back,
                )
            case 4:
                return ListView(
                    title,
                    self._address_rows,
                    subtitle=lambda: self._subtitle(
                        "Where the proxy listens; harnesses call it here."
                    ),
                    hint="Enter to edit or continue · Esc to go back",
                    on_back=self._back,
                )
            case 5:
                return ListView(
                    title,
                    self._review_rows,
                    subtitle=lambda: self._subtitle(
                        "Nothing is written yet. Unsaved policy edits are saved too."
                    ),
                    hint="Enter to apply · d policy diff · Esc to go back",
                    keys={"d": lambda _row: self._open_diff()},
                    on_back=self._back,
                )
        return ListView(
            title,
            self._result_rows,
            subtitle=lambda: self._subtitle("Egida applied the setup."),
            hint="Enter or Esc to close",
            on_back=self._back,
        )

    # ── steps ────────────────────────────────────────────────────────────────

    def _welcome_rows(self) -> list[Row]:
        return [
            Row(
                "Start setup",
                "5 steps",
                "Pick a model and the harnesses, check the proxy address, review the changes, "
                "then Egida writes the policy, the harness configs and starts the proxy.",
                lambda: self._go(_MODEL),
                id="start",
            )
        ]

    def _model_rows(self) -> list[Row]:
        help_text = (
            "Small local models handle coding tools poorly; pick the largest model "
            "your upstream serves."
        )
        rows = [
            Row(
                name,
                ("current · " if name == self._model else "") + self._upstream_url(name),
                help_text,
                partial(self._choose_model, name),
                tone="success" if name == self._model else "normal",
                id=name,
            )
            for name in self._session.doc.names("models")
        ]
        if self._model and self._model not in self._session.doc.names("models"):
            rows.append(
                Row(
                    self._model,
                    "new · " + self._upstream_url(self._model),
                    "Added to the policy when you apply. " + help_text,
                    lambda: self._choose_model(self._model),
                    tone="success",
                    id=self._model,
                )
            )
        rows.append(
            Row(
                "Add a model...",
                "",
                "A model name the first upstream serves, for example qwen3-coder:30b.",
                self._add_model,
                tone="add",
                id=_ADD_MODEL,
            )
        )
        return rows

    def _choose_model(self, name: str) -> None:
        self._model = name
        self._go(_HARNESSES)

    def _add_model(self) -> None:
        def submit(text: str) -> None:
            name = text.strip()
            if not name or any(ch.isspace() for ch in name):
                raise ValueError("Enter one model name without spaces, for example qwen3:8b.")
            if not self._session.doc.names("upstreams"):
                raise ValueError("The policy has no upstream; add one under Upstreams first.")
            self._choose_model(name)

        self._session.ui.push(
            InputView(
                "Add a model",
                "Name of the model on the upstream ("
                + self._upstream_url("")
                + "). It is added to the policy with price 0.",
                "",
                submit,
                placeholder="qwen3-coder:30b",
            )
        )

    def _harness_rows(self) -> list[Row]:
        rows = []
        for harness in self._registry:
            state = self._states[harness.id]
            if harness.mode == "unavailable":
                rows.append(
                    Row(
                        "  " + harness.name,
                        "unavailable",
                        harness.note,
                        tone="muted",
                        id=harness.id,
                    )
                )
                continue
            mark = "✓ " if harness.id in self._checked else "  "
            found = state.detail if state.installed else "not found"
            value = f"{found} · {harness.protocol} · {harness.mode}"
            help_text = harness.note
            if harness.mode == "launch":
                help_text += f" Start it with `egd launch {harness.id}`."
            if state.enabled:
                help_text += " Egida's settings are in place now."
            rows.append(
                Row(
                    mark + harness.name,
                    value,
                    help_text,
                    partial(self._toggle, harness),
                    tone="normal" if state.installed else "muted",
                    id=harness.id,
                )
            )
        return rows

    def _toggle(self, harness: Harness) -> None:
        self._checked ^= {harness.id}

    def _address_rows(self) -> list[Row]:
        return [
            Row(
                "Host",
                self._host,
                "Address the proxy listens on. 127.0.0.1 keeps it on this machine.",
                lambda: self._edit("host"),
                id="host",
            ),
            Row(
                "Port",
                str(self._port),
                "TCP port of the proxy; harnesses call http://host:port.",
                lambda: self._edit("port"),
                id="port",
            ),
            Row(
                "Continue",
                f"{self._profile().base_url}",
                "Review the changes before anything is written.",
                lambda: self._go(_REVIEW),
                id=_CONTINUE,
            ),
        ]

    def _profile(self, **changes: object) -> RunProfile:
        values = self._session.profile.model_dump() | {"host": self._host, "port": self._port}
        try:
            return RunProfile.model_validate(values | changes)
        except ValidationError as exc:
            raise ValueError("; ".join(str(err["msg"]) for err in exc.errors())) from None

    def _edit(self, name: Literal["host", "port"]) -> None:
        def submit(text: str) -> None:
            value = text.strip()
            if not value or any(ch.isspace() for ch in value):
                raise ValueError("Enter one value without spaces.")
            profile = self._profile(**{name: value})
            self._host, self._port = profile.host, profile.port

        current = self._host if name == "host" else str(self._port)
        description = (
            "Host name or IP address, for example 127.0.0.1."
            if name == "host"
            else "Whole number from 1 to 65535, for example 8080."
        )
        self._session.ui.push(InputView(name.capitalize(), description, current, submit))

    # ── review ───────────────────────────────────────────────────────────────

    def _endpoint(self, harness: Harness, base_url: str) -> Endpoint:
        return Endpoint(base_url=base_url, key=self._keys[harness.id], model=self._model)

    def _prepare_review(self) -> None:
        session = self._session
        selected = self._selected()
        self._keys = {harness.id: new_key() for harness in selected}
        policy, problems, diff = self._policy_preview(selected)
        files: list[tuple[str, str]] = []
        env = session.harness_env
        base_url = self._profile().base_url
        for harness in selected:
            try:
                changes = harness.plan(env, self._endpoint(harness, base_url))
            except (HarnessError, OSError) as exc:
                problems.append(f"{harness.name}: {exc}")
                continue
            files += [_change_row(env, harness, change) for change in changes]
            if harness.mode == "launch":
                files.append((f"{harness.name}: start with egd launch {harness.id}", harness.note))
        for harness in self._removed():
            try:
                changes = harness.plan_remove(env)
            except (HarnessError, OSError) as exc:
                problems.append(f"{harness.name}: {exc}")
                continue
            files += [_change_row(env, harness, change) for change in changes]
            if not changes:
                files.append((f"{harness.name}: remove Egida's settings", harness.note))
        if (self._host, self._port) != (session.profile.host, session.profile.port):
            files.append((f"run profile: proxy at {base_url}", f"Saved in {session.profile_path}."))
        self._preview = _Preview(policy=policy, files=files, problems=problems, diff=diff)

    def _policy_preview(self, selected: list[Harness]) -> tuple[list[str], list[str], list[str]]:
        """Summary, problems and diff of the policy after apply_policy, on a copy of the open
        document (unsaved edits included); the open document is not touched."""
        session = self._session
        doc = session.doc
        before = doc.render()
        try:
            lines = plan_policy(doc, selected, self._model, self._keys, registry=self._registry)
            with tempfile.TemporaryDirectory(prefix="egida-wizard-") as tmp:
                copy_path = Path(tmp) / doc.path.name
                copy_path.write_text(before, encoding="utf-8")
                copy = PolicyDocument.open(copy_path)
                apply_policy(copy, selected, self._model, self._keys, registry=self._registry)
                after = copy.render()
                problems = copy.validate(session.param_models)
        except (DocumentError, OSError) as exc:
            return [], [str(exc)], []
        diff = list(
            difflib.unified_diff(
                before.splitlines(),
                after.splitlines(),
                fromfile=f"{doc.path.name} (now)",
                tofile=f"{doc.path.name} (after setup)",
                n=2,
                lineterm="",
            )
        )
        return lines, problems, diff

    def _review_rows(self) -> list[Row]:
        preview = self._preview
        if preview is None:
            return []
        rows = [
            Row(
                "Problem",
                text,
                "Fix this before applying; Esc goes back.",
                tone="error",
                id=f"p{i}",
            )
            for i, text in enumerate(preview.problems)
        ]
        rows += [
            Row(
                "Policy",
                text,
                f"Change to {self._session.doc.path}; press d to see the diff.",
                id=f"policy{i}",
            )
            for i, text in enumerate(preview.policy)
        ]
        rows += [
            Row("File", label, help_text, id=f"file{i}")
            for i, (label, help_text) in enumerate(preview.files)
        ]
        if not preview.policy and not preview.files and not preview.problems:
            rows.append(Row("Nothing to change", "", "Esc goes back to pick harnesses.", id="none"))
        return rows

    def _open_diff(self) -> None:
        preview = self._preview
        lines = preview.diff if preview is not None else []
        ui = self._session.ui
        ui.push(
            TextView(
                "Policy diff",
                lambda width: diff_lines(ui.style, lines) or ["No policy changes."],
                subtitle=str(self._session.doc.path),
            )
        )

    # ── apply ────────────────────────────────────────────────────────────────

    def _apply(self) -> None:
        session, ui = self._session, self._session.ui
        preview = self._preview
        if preview is None:
            return
        if preview.problems:
            ui.notify("error", "Cannot apply", preview.problems[:3])
            return
        selected = self._selected()
        try:
            apply_policy(session.doc, selected, self._model, self._keys, registry=self._registry)
            session.doc.save()
        except DocumentError as exc:  # ConflictError included
            ui.notify("error", "The policy was not saved", str(exc))
            return
        try:
            session.update_profile(host=self._host, port=self._port)
        except ValueError as exc:
            ui.notify("error", "The run profile was not saved", str(exc))
            return
        env, base_url = session.harness_env, session.profile.base_url
        outcomes: list[_Outcome] = []
        for harness in selected:
            outcome = _Outcome(harness, "apply")
            try:
                outcome.changes = harness.apply(env, self._endpoint(harness, base_url))
            except (HarnessError, OSError) as exc:
                outcome.error = str(exc)
            outcomes.append(outcome)
        for harness in self._removed():
            outcome = _Outcome(harness, "remove")
            try:
                outcome.changes = harness.remove(env)
            except (HarnessError, OSError) as exc:
                outcome.error = str(exc)
            outcomes.append(outcome)
        self._outcomes = outcomes
        self._start_proxy()
        self._enabled = {o.harness.id for o in outcomes if o.action == "apply" and o.error is None}
        self._go(_RESULT)

    def _start_proxy(self) -> None:
        session = self._session
        proxy = session.proxy
        if session.errors():
            self._proxy_note = "not started: the policy has problems"
            return
        if proxy.running and proxy.profile != session.profile:
            run_screens._restart(session)
            self._proxy_note = "restarted with the new address"
        elif not proxy.running:
            run_screens._start(session)
            self._proxy_note = "started"
        else:
            self._proxy_note = "running; it reloads the saved policy by itself"

    def _result_rows(self) -> list[Row]:
        rows = []
        for outcome in self._outcomes:
            harness = outcome.harness
            if outcome.error is not None:
                rows.append(Row(harness.name, "failed", outcome.error, tone="error", id=harness.id))
            elif outcome.action == "remove":
                rows.append(
                    Row(harness.name, "removed", "Egida's settings are gone.", id=harness.id)
                )
            else:
                rows.append(
                    Row(
                        harness.name,
                        f"ok · start with: {start_command(harness)}",
                        harness.note,
                        tone="success",
                        id=harness.id,
                    )
                )
        rows.append(
            Row(
                "Proxy",
                run_screens.run_summary(self._session),
                f"{self._proxy_note.capitalize()}. Open Run on the main screen to watch it.",
                id="proxy",
            )
        )
        return rows


def _change_row(env: HarnessEnv, harness: Harness, change: Change) -> tuple[str, str]:
    return f"{harness.name}: {change.action} {display_path(env, change.path)}", change.summary


def wizard_view(
    session: Session,
    *,
    start: Literal["welcome", "harnesses"] = "welcome",
    first_run: bool = False,
    on_done: Callable[[], None],
    registry: Sequence[Harness] | None = None,
) -> View:
    """The setup wizard over `session`; push it on the app. It removes itself when it closes,
    then calls `on_done`. `registry` defaults to every known harness."""
    return _Wizard(
        session,
        start=start,
        first_run=first_run,
        on_done=on_done,
        registry=REGISTRY if registry is None else registry,
    )
