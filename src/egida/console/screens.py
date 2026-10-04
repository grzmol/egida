"""Egida's policy screens: the app frame, the root menu, every policy section, review & save.

Every list recomputes its rows from `session.doc` on each render (the document may be replaced by
reload or by switching the policy file), and every edit goes through `session.change`, which turns
refused edits into an error box. Controls and the Run screens live in their own modules.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import re
import secrets
from collections.abc import Callable, Mapping
from functools import partial
from pathlib import Path
from typing import Any, Final, Literal

from egida.console import controls, run_screens
from egida.console.document import ConflictError, DocumentError, PathKey, PolicyDocument
from egida.console.fields import field_row, format_value
from egida.console.harnesses import REGISTRY
from egida.console.harnesses.base import HarnessError
from egida.console.schema import HELP, SECTION_MODELS, fields, help_for
from egida.console.session import Session
from egida.console.theme import Style, truncate, visible_width, wrap
from egida.console.widgets import (
    App,
    Choice,
    ConfirmView,
    Header,
    InputView,
    ListView,
    Row,
    RowTone,
    TextView,
    View,
    diff_lines,
)
from egida.console.wizard import wizard_view
from egida.core.policy import AgentSpec, Defaults, Limits, Policy

__all__ = ["build_app", "collection_view", "entry_view", "review_view"]

_THING: Final[Mapping[str, str]] = {
    "upstreams": "upstream",
    "models": "model",
    "agents": "agent",
    "budgets": "budget",
}
_ABOUT: Final[Mapping[str, str]] = {
    "upstreams": "Model servers the proxy forwards requests to: OpenAI-compatible APIs such as "
    "Ollama.",
    "models": "Models agents may call: the upstream that serves each one and its price per 1000 "
    "tokens.",
    "agents": "Clients of the proxy: each has its own API key, allowed models and tools, and a "
    "budget.",
    "budgets": "Usage limits per agent: tokens, cost and requests per time window, plus loop "
    "detection.",
}
_REFERENCES: Final[Mapping[tuple[str, str], str]] = {
    ("models", "upstream"): "upstreams",
    ("agents", "allowed_models"): "models",
    ("agents", "budget"): "budgets",
}
_UPSTREAM_TEMPLATE: Final[Mapping[str, Any]] = {
    "base_url": "http://127.0.0.1:11434/v1",
    "timeout_s": 60,
}
_BUDGET_TEMPLATE: Final[Mapping[str, Any]] = {  # budget `default` of config/policy.yaml
    "max_tokens": 50000,
    "max_cost": 1.0,
    "max_requests": 300,
    "window_s": 3600,
    "max_identical": 5,
    "identical_window_s": 10,
}
_SHA256: Final = re.compile(r"[0-9a-f]{64}")
_SHA_SHOWN: Final = 12
_HINTS: Final = (
    ("↑↓", "move"),
    ("enter", "change"),
    ("esc", "back"),
    ("ctrl+s", "save policy"),
    ("ctrl+c", "quit"),
)


def _noop() -> None:
    return None


# ── app ──────────────────────────────────────────────────────────────────────


def build_app(session: Session, *, style: Style) -> App:
    """The whole Egida UI over `session`; sets `session.app`."""
    try:
        version = importlib.metadata.version("egida")
    except importlib.metadata.PackageNotFoundError:
        version = "dev"
    header = Header(
        name="egida",
        version=version,
        tagline="configure and run the proxy",
        hints=_HINTS,
    )
    app = App(
        _root_view(session),
        style=style,
        header=header,
        footer=lambda width: _footer(session, width),
    )
    session.app = app
    app.shortcuts["ctrl+s"] = lambda: _save_shortcut(session)
    run_screens.install(session)
    return app


def _footer(session: Session, width: int) -> list[str]:
    style = session.ui.style
    doc = session.doc
    branch = _git_branch(Path.cwd())
    where = _display_path(doc.path) + (f" ({branch})" if branch else "")
    first = style.fg("dim", truncate(where, width))

    state = [run_screens.footer_badge(session)]
    if doc.dirty:
        state.append(style.fg("warning", "● unsaved"))
    problems = session.errors()
    if problems:
        state.append(style.fg("error", f"✗ {len(problems)} {_plural(len(problems), 'problem')}"))
    else:
        state.append(style.fg("success", "✓ valid"))
    right = "  ".join(part for part in state if part)
    room = width - visible_width(right) - 2
    left = truncate(_policy_stats(doc), room) if room > 0 else ""
    gap = max(1, width - visible_width(left) - visible_width(right))
    second = style.fg("dim", left) + " " * gap + right
    return [first, second]


def _policy_stats(doc: PolicyDocument) -> str:
    items = _controls(doc)
    enabled = sum(1 for item in items if item.get("enabled", True) is not False)
    return (
        f"policy v{format_value(doc.get(('version',), '?'))} · "
        f"{len(items)} controls, {enabled} on · "
        f"{len(doc.names('agents'))} agents · {len(doc.names('budgets'))} budgets"
    )


def _controls(doc: PolicyDocument) -> list[dict[str, Any]]:
    items = doc.get(("controls",), [])
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _git_branch(start: Path) -> str:
    """Branch of the repository in `start` from `.git/HEAD` (a worktree's `.git` file is
    followed); a detached HEAD gives the short sha; "" when there is no repository."""
    git = start / ".git"
    try:
        if git.is_file():
            pointer = git.read_text(encoding="utf-8").strip()
            if not pointer.startswith("gitdir:"):
                return ""
            git = (start / pointer.removeprefix("gitdir:").strip()).resolve()
        head = (git / "HEAD").read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return ""
    if head.startswith("ref:"):
        return head.removeprefix("ref:").strip().removeprefix("refs/heads/")
    return head[:7]


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path)


def _plural(count: int, word: str) -> str:
    return word if count == 1 else word + "s"


# ── root ─────────────────────────────────────────────────────────────────────


def _root_view(session: Session) -> ListView:
    def rows() -> list[Row]:
        doc = session.doc
        problems = session.errors()
        out = [
            Row(
                "General",
                f"v{format_value(doc.get(('version',), '?'))} · on_error "
                f"{format_value(doc.get(('defaults', 'on_error'), Defaults().on_error))} · "
                f"timeout {format_value(doc.get(('defaults', 'timeout_ms'), 1500))} ms",
                help="Policy version and what controls do when they fail or run too long.",
                action=lambda: session.ui.push(_general_view(session)),
            ),
            Row(
                "Limits",
                f"{_limit(doc, 'max_input_chars')} chars · "
                f"{_limit(doc, 'max_messages')} messages · {_limit(doc, 'max_tokens')} tokens",
                help="Size limits every request must fit before any control runs.",
                action=lambda: session.ui.push(_limits_view(session)),
            ),
        ]
        for section in ("upstreams", "models", "agents", "budgets"):
            names = doc.names(section)
            out.append(
                Row(
                    section.capitalize(),
                    f"{len(names)} · {', '.join(names)}" if names else "none",
                    help=_ABOUT[section],
                    action=partial(_push, session, partial(collection_view, session, section)),
                    id=section,
                )
            )
        out.append(
            Row(
                "Controls",
                controls.controls_summary(session),
                help="Detectors that scan requests and answers, in the order they run.",
                action=lambda: session.ui.push(controls.controls_view(session)),
            )
        )
        out += [
            Row(
                "Setup wizard",
                help="Pick a model and coding harnesses; Egida configures them and the proxy.",
                action=lambda: _open_wizard(session, "welcome"),
            ),
            Row(
                "Harnesses",
                _harness_summary(session),
                help="Coding harnesses that send their requests through the proxy.",
                action=lambda: _open_wizard(session, "harnesses"),
            ),
        ]
        if problems:
            out.append(
                Row(
                    "Problems",
                    f"{len(problems)} · cannot save",
                    help="The proxy would reject this policy. Open the list to see what to fix.",
                    action=lambda: session.ui.push(_problems_view(session)),
                    tone="error",
                )
            )
        changed = _changed_lines(doc)
        out += [
            Row(
                "Review & save",
                f"{changed} {_plural(changed, 'line')} changed" if changed else "no changes",
                help="See the changes as a diff and write them to the policy file (ctrl+s).",
                action=lambda: _open_review(session),
            ),
            Row(
                "Run",
                run_screens.run_summary(session),
                help="Start, stop and watch the proxy; address and file settings.",
                action=lambda: session.ui.push(run_screens.run_view(session)),
            ),
            Row(
                "Policy file",
                _display_path(doc.path),
                help="Edit another policy file; the proxy runs the one chosen here.",
                action=lambda: session.ui.push(run_screens.policy_picker(session)),
            ),
            Row(
                "Reload from disk",
                help="Read the policy file again and drop unsaved edits.",
                action=lambda: _reload(session),
            ),
            Row(
                "Quit",
                help="Leave Egida. A proxy started here stops too.",
                action=lambda: _quit(session),
            ),
        ]
        return out

    return ListView(
        "egida",
        rows,
        subtitle=lambda: _display_path(session.doc.path),
        on_back=lambda: _quit(session),
    )


def _harness_summary(session: Session) -> str:
    env = session.harness_env
    on = []
    for harness in REGISTRY:
        try:
            if harness.mode != "unavailable" and harness.enabled(env):
                on.append(harness.id)
        except (HarnessError, OSError):
            continue
    return f"{len(on)} on: {', '.join(on)}" if on else "none"


def _open_wizard(session: Session, start: Literal["welcome", "harnesses"]) -> None:
    session.ui.push(wizard_view(session, start=start, on_done=_noop))


def _limit(doc: PolicyDocument, name: str) -> str:
    return format_value(doc.get(("limits", name), Limits.model_fields[name].default))


def _changed_lines(doc: PolicyDocument) -> int:
    if not doc.dirty:
        return 0
    return sum(1 for line in doc.diff() if line[:1] in "+-" and not line.startswith(("+++", "---")))


def _general_view(session: Session) -> ListView:
    version = next(spec for spec in fields(Policy) if spec.name == "version")

    def rows() -> list[Row]:
        out = [
            field_row(
                session,
                ("version",),
                version,
                help_text=HELP["policy.version"],
                order=tuple(Policy.model_fields),
            )
        ]
        out += [
            field_row(
                session,
                ("defaults", spec.name),
                spec,
                help_text=help_for("defaults", spec),
                order=tuple(Defaults.model_fields),
            )
            for spec in fields(Defaults)
        ]
        return out

    return ListView("General", rows, subtitle="Policy version and defaults for every control.")


def _limits_view(session: Session) -> ListView:
    def rows() -> list[Row]:
        return [
            field_row(
                session,
                ("limits", spec.name),
                spec,
                help_text=help_for("limits", spec),
                order=tuple(Limits.model_fields),
            )
            for spec in fields(Limits)
        ]

    return ListView("Limits", rows, subtitle="Every request must fit these limits.")


def _problems_view(session: Session, title: str = "Problems") -> TextView:
    def body(width: int) -> list[str]:
        style = session.ui.style
        problems = session.errors()
        if not problems:
            return [style.fg("success", "✓ No problems: the policy can be saved.")]
        lines: list[str] = []
        for problem in problems:
            wrapped = wrap(problem, max(1, width - 2)) or [""]
            lines.append(style.fg("error", "✗ " + wrapped[0]))
            lines += [style.fg("error", "  " + rest) for rest in wrapped[1:]]
        return lines

    return TextView(
        title,
        body,
        subtitle="The proxy would reject this policy. Fix these, then save.",
    )


# ── named sections ───────────────────────────────────────────────────────────


def collection_view(session: Session, section: str) -> View:
    """List of one named section (upstreams, models, agents, budgets): open, add, delete."""
    thing = _THING[section]

    def rows() -> list[Row]:
        doc = session.doc
        out = []
        for name in doc.names(section):
            value, tone = _summary(section, doc.get((section, name)))
            users = doc.users(section, name)
            used = f"Used by {', '.join(users)}." if users else "Not used by other entries."
            out.append(
                Row(
                    name,
                    value,
                    help=f"{used} Enter to open, Del to delete.",
                    action=partial(_push, session, partial(entry_view, session, section, name)),
                    tone=tone,
                    id="entry:" + name,
                )
            )
        teach = (
            f"Add a {thing}." if out else f"No {section} yet. {_ABOUT[section]} Add the first one."
        )
        out.append(
            Row(
                f"Add {thing}",
                help=teach,
                action=lambda: _add_entry(session, section),
                tone="add",
                id="add",
            )
        )
        return out

    def delete(row: Row) -> None:
        if row.id.startswith("entry:"):
            _delete_entry(session, section, row.id.removeprefix("entry:"))

    return ListView(
        section.capitalize(),
        rows,
        subtitle=_ABOUT[section],
        hint="Enter to open · Del to delete · Esc to go back",
        keys={"delete": delete, "backspace": delete},
    )


def _summary(section: str, entry: Any) -> tuple[str, RowTone]:
    if not isinstance(entry, dict):
        return f"not a mapping: {format_value(entry)}", "error"
    get = entry.get
    if section == "upstreams":
        return format_value(get("base_url", "no base_url")), "normal"
    if section == "models":
        return (
            f"{format_value(get('upstream', 'no upstream'))} · "
            f"in ${format_value(get('price_in_per_1k', 0.0))} / "
            f"out ${format_value(get('price_out_per_1k', 0.0))} per 1k"
        ), "normal"
    if section == "agents":
        models = get("allowed_models") or []
        tools = get("allowed_tools") or []
        count = len(models) if isinstance(models, list) else 0
        if not isinstance(tools, list) or not tools:
            shown = "none"
        elif "*" in tools:
            shown = "*"
        else:
            shown = str(len(tools))
        budget = format_value(get("budget", "no budget"))
        return f"{budget} · {count} {_plural(count, 'model')} · tools: {shown}", "normal"
    return (
        f"{format_value(get('max_tokens', '?'))} tokens · "
        f"${format_value(get('max_cost', '?'))} · "
        f"{format_value(get('max_requests', '?'))} req / "
        f"{format_value(get('window_s', '?'))} s"
    ), "normal"


def _check_name(session: Session, section: str, text: str, current: str | None = None) -> str:
    """The entry name in `text`; ValueError(readable) when it can't be used."""
    if not text.strip():
        raise ValueError("Type a name, or press Esc to cancel.")
    if text != text.strip():
        raise ValueError("Remove the spaces around the name.")
    if text != current and text in session.doc.names(section):
        raise ValueError(f"A {_THING[section]} named '{text}' already exists; choose another name.")
    return text


def _add_entry(session: Session, section: str) -> None:
    thing = _THING[section]

    def submit(text: str) -> None:
        name = _check_name(session, section, text)
        doc = session.doc
        key = ""
        value: dict[str, Any]
        if section == "upstreams":
            value = dict(_UPSTREAM_TEMPLATE)
        elif section == "models":
            upstreams = doc.names("upstreams")
            if not upstreams:
                raise ValueError("Add an upstream first: a model needs one to serve it.")
            value = {"upstream": upstreams[0], "price_in_per_1k": 0.0, "price_out_per_1k": 0.0}
        elif section == "budgets":
            first = doc.names("budgets")
            copied = doc.get(("budgets", first[0])) if first else None
            value = dict(copied) if isinstance(copied, dict) else dict(_BUDGET_TEMPLATE)
        else:
            budgets = doc.names("budgets")
            if not budgets:
                raise ValueError("Add a budget first: every agent needs one.")
            key = _new_key()
            value = {
                "key_sha256": _sha256(key),
                "allowed_models": [],
                "allowed_tools": [],
                "budget": budgets[0],
            }
        if not session.change(lambda d: d.add_entry(section, name, value)):
            return
        session.ui.push(entry_view(session, section, name))
        if key:
            session.ui.push(_key_reveal(session, name, key))

    session.ui.push(
        InputView(
            f"New {thing}",
            f"Name of the new {thing}. {_ABOUT[section]}",
            "",
            submit,
            placeholder=f"{thing} name",
        )
    )


def _delete_entry(
    session: Session, section: str, name: str, after: Callable[[], None] = _noop
) -> None:
    def delete() -> None:
        if session.change(lambda d: d.delete_entry(section, name)):
            after()

    if session.doc.users(section, name):
        delete()  # refused with the referrers named (InUseError via session.change)
        return
    thing = _THING[section]
    session.ui.push(
        ConfirmView(
            f"Delete {thing} '{name}'?",
            "It is removed from the policy when you save.",
            [
                Choice(f"Delete {thing}", delete, tone="danger"),
                Choice("Cancel", _noop),
            ],
        )
    )


# ── entry ────────────────────────────────────────────────────────────────────


class _Tracked:
    """Name of the entry an entry view shows; follows renames made through that view."""

    __slots__ = ("name",)

    def __init__(self, name: str) -> None:
        self.name = name


def entry_view(session: Session, section: str, name: str) -> View:
    """Every field of one named entry, references as pickers, then rename and delete."""
    thing = _THING[section]
    model = SECTION_MODELS[section]
    order = tuple(model.model_fields)
    tracked = _Tracked(name)
    view: ListView

    def rows() -> list[Row]:
        doc = session.doc
        current = tracked.name
        if current not in doc.names(section):
            return [
                Row(
                    "Back",
                    help=f"{thing.capitalize()} '{current}' is no longer in the policy.",
                    action=lambda: session.ui.remove(view),
                )
            ]
        out: list[Row] = []
        for spec in fields(model):
            if section == "agents" and spec.name == "key_sha256":
                out.append(_key_row(session, current))
                continue
            referenced = _REFERENCES.get((section, spec.name))
            out.append(
                field_row(
                    session,
                    (section, current, spec.name),
                    spec,
                    help_text=help_for(section, spec),
                    order=order,
                    choices=doc.names(referenced) if referenced else None,
                )
            )
        out += [
            Row(
                "Rename…",
                current,
                help=f"Give this {thing} another name; references to it follow.",
                action=rename,
                id="rename",
            ),
            Row(
                "Delete…",
                help=f"Remove this {thing} from the policy.",
                action=lambda: _delete_entry(
                    session, section, tracked.name, lambda: session.ui.remove(view)
                ),
                tone="danger",
                id="delete",
            ),
        ]
        return out

    def subtitle() -> str:
        if tracked.name not in session.doc.names(section):
            return ""
        users = session.doc.users(section, tracked.name)
        return f"Used by {', '.join(users)}." if users else _ABOUT[section]

    def rename() -> None:
        def submit(text: str) -> None:
            new = _check_name(session, section, text, tracked.name)
            if new == tracked.name:
                return
            old = tracked.name
            if session.change(lambda d: d.rename_entry(section, old, new)):
                tracked.name = new

        session.ui.push(
            InputView(
                f"Rename {thing} '{tracked.name}'",
                "References in other sections follow the new name.",
                tracked.name,
                submit,
            )
        )

    view = ListView(lambda: f"{thing.capitalize()} {tracked.name}", rows, subtitle=subtitle)
    return view


def _key_row(session: Session, agent: str) -> Row:
    path: PathKey = ("agents", agent, "key_sha256")
    digest = session.doc.get(path)
    tone: RowTone = "normal"
    if isinstance(digest, str) and digest:
        value = f"sha256 {digest[:_SHA_SHOWN]}…"
    else:
        value, tone = "missing", "error"
    return Row(
        "API key",
        value,
        help=HELP["agents.key_sha256"] + " Enter to replace it.",
        action=lambda: _key_menu(session, agent),
        tone=tone,
        id="key",
    )


def _key_menu(session: Session, agent: str) -> None:
    def generate() -> None:
        key = _new_key()
        if _write_digest(session, agent, _sha256(key)):
            session.ui.push(_key_reveal(session, agent, key))

    def set_key(text: str) -> None:
        if not text:
            raise ValueError("Type or paste the key, or press Esc to keep the current one.")
        if text != text.strip():
            raise ValueError("Remove the spaces around the key.")
        _write_digest(session, agent, _sha256(text))

    def paste_sha(text: str) -> None:
        digest = text.strip().lower()
        if not _SHA256.fullmatch(digest):
            raise ValueError("A sha256 is 64 hex characters (0-9, a-f).")
        _write_digest(session, agent, digest)

    session.ui.push(
        ConfirmView(
            f"API key of agent '{agent}'",
            "Agents authenticate with this key. The policy stores only its sha256.",
            [
                Choice("Generate a new key", generate, "random key, shown once"),
                Choice(
                    "Set a key",
                    lambda: session.ui.push(
                        InputView(
                            f"API key of agent '{agent}'",
                            "Type or paste the key. Only its sha256 goes into the policy.",
                            "",
                            set_key,
                            secret=True,
                        )
                    ),
                    "a key you already use",
                ),
                Choice(
                    "Paste a sha256",
                    lambda: session.ui.push(
                        InputView(
                            f"sha256 of agent '{agent}' key",
                            "64 lowercase hex characters, e.g. from `printf %s <key> | shasum "
                            "-a 256`.",
                            "",
                            paste_sha,
                        )
                    ),
                    "digest of a key kept elsewhere",
                ),
            ],
        )
    )


def _write_digest(session: Session, agent: str, digest: str) -> bool:
    """New key digest; the old end-of-line comment (often "sha256 of sk-…") would be stale."""
    path: PathKey = ("agents", agent, "key_sha256")

    def mutate(doc: PolicyDocument) -> None:
        doc.set(path, digest, tuple(AgentSpec.model_fields))
        doc.set_comment(path, None)

    return session.change(mutate)


def _new_key() -> str:
    return "sk-" + secrets.token_urlsafe(24)


def _sha256(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _key_reveal(session: Session, agent: str, key: str) -> TextView:
    def body(width: int) -> list[str]:
        style = session.ui.style
        note = (
            "Shown once: copy it now. Only its sha256 goes into the policy. Agents send it as "
            "`Authorization: Bearer <key>`. Save the policy (ctrl+s) to activate it."
        )
        return [
            style.bold(style.fg("accent", key)),
            "",
            *(style.fg("muted", line) for line in wrap(note, max(1, width))),
        ]

    view = TextView(
        f"API key of agent '{agent}'",
        body,
        hint="Enter or Esc to close",
        on_enter=lambda: session.ui.remove(view),
    )
    return view


# ── review & save ────────────────────────────────────────────────────────────


class _Review(TextView):
    """The diff of unsaved edits; Enter (or ctrl+s again) saves."""

    def __init__(self, session: Session) -> None:
        self._session = session
        super().__init__(
            "Review changes",
            self._diff,
            subtitle=self._counts,
            hint="Enter to save · Esc to go back",
            on_enter=self.save,
        )

    def _diff(self, width: int) -> list[str]:
        return diff_lines(self._session.ui.style, self._session.doc.diff())

    def _counts(self) -> str:
        lines = self._session.doc.diff()[2:]
        added = sum(1 for line in lines if line.startswith("+"))
        removed = sum(1 for line in lines if line.startswith("-"))
        return f"{_display_path(self._session.doc.path)} · +{added} -{removed}"

    def save(self, *, force: bool = False) -> None:
        session = self._session
        app = session.ui
        problems = session.errors()
        if problems:
            app.remove(self)
            app.push(_cannot_save_view(session))
            return
        try:
            session.doc.save(force=force)
        except ConflictError as exc:
            app.push(
                ConfirmView(
                    "The file changed on disk",
                    str(exc),
                    [
                        Choice(
                            "Overwrite with my version",
                            lambda: self.save(force=True),
                            tone="danger",
                        ),
                        Choice(
                            "Reload from disk (drop my changes)",
                            lambda: _do_reload(session, after=lambda: app.remove(self)),
                        ),
                        Choice("Cancel", _noop),
                    ],
                )
            )
            return
        except DocumentError as exc:
            app.notify("error", "Not saved", str(exc))
            return
        app.remove(self)
        app.notify(
            "success",
            f"Saved {_display_path(session.doc.path)}",
            "The running proxy reloads it within about 1 s."
            if session.proxy.running
            else "Start the proxy from Run to use it.",
        )


def _cannot_save_view(session: Session) -> TextView:
    count = len(session.errors())
    return _problems_view(session, f"Cannot save: {count} {_plural(count, 'problem')}")


def review_view(session: Session) -> View:
    """Problems that block saving, or the diff of unsaved edits (Enter saves)."""
    if session.errors():
        return _cannot_save_view(session)
    if not session.doc.dirty:
        return TextView(
            "Review changes",
            lambda width: [
                session.ui.style.fg("muted", "No changes: the file matches the policy.")
            ],
        )
    return _Review(session)


def _open_review(session: Session) -> None:
    if not session.errors() and not session.doc.dirty:
        session.ui.notify("info", "No changes to save")
        return
    session.ui.push(review_view(session))


def _save_shortcut(session: Session) -> None:
    top = session.ui.top
    if isinstance(top, _Review):
        top.save()
    else:
        _open_review(session)


# ── reload and quit ──────────────────────────────────────────────────────────


def _reload(session: Session) -> None:
    changed = _changed_lines(session.doc)
    if not changed:
        _do_reload(session)
        return
    session.ui.push(
        ConfirmView(
            "Reload from disk?",
            _lost_lines(changed),
            [
                Choice("Reload (drop my changes)", lambda: _do_reload(session), tone="danger"),
                Choice("Cancel", _noop),
            ],
        )
    )


def _do_reload(session: Session, after: Callable[[], None] = _noop) -> None:
    try:
        session.doc.reload()
    except DocumentError as exc:
        session.ui.notify("error", "Not reloaded", str(exc))
        return
    after()
    session.ui.notify("info", f"Reloaded {_display_path(session.doc.path)}")


def _quit(session: Session) -> None:
    app = session.ui
    changed = _changed_lines(session.doc)
    running = session.proxy.running
    if not changed and not running:
        app.quit()
        return
    lost = [_lost_lines(changed)] if changed else []
    if running:
        lost.append("The proxy started by Egida stops.")
    choices = [Choice("Review & save", lambda: _open_review(session))] if changed else []
    choices += [Choice("Quit", app.quit, tone="danger"), Choice("Cancel", _noop)]
    app.push(ConfirmView("Quit Egida?", " ".join(lost), choices))


def _lost_lines(changed: int) -> str:
    return f"{changed} unsaved {_plural(changed, 'line')} {'is' if changed == 1 else 'are'} lost."


def _push(session: Session, make: Callable[[], View]) -> None:
    session.ui.push(make())
