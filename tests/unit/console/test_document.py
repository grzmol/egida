"""PolicyDocument: round-trip edits keep the file's layout, references follow renames, saving is
atomic and refuses to overwrite changes made on disk by someone else."""

from __future__ import annotations

import os
import shutil
import stat
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from egida.adapters.fake_model import FakeGuardModelClient
from egida.app import _build_detectors
from egida.console.document import (
    ConflictError,
    DocumentError,
    InUseError,
    PolicyDocument,
)
from egida.core.ports import DetectorDeps
from egida.core.signatures import SIGNATURE_KIND, SignatureParams

ROOT = Path(__file__).resolve().parents[3]
POLICIES = sorted((ROOT / "config").glob("policy*.yaml"))
ROOT_ORDER = (
    "version",
    "defaults",
    "limits",
    "upstreams",
    "models",
    "agents",
    "budgets",
    "controls",
)
BUDGET_ORDER = (
    "max_tokens",
    "max_cost",
    "max_requests",
    "window_s",
    "max_identical",
    "identical_window_s",
)


@pytest.fixture(scope="module")
def param_models() -> dict[str, type[BaseModel]]:
    detectors = _build_detectors(DetectorDeps(guard=FakeGuardModelClient()))
    return {kind: d.Params for kind, d in detectors.items()} | {SIGNATURE_KIND: SignatureParams}


def _copy(tmp_path: Path, name: str = "policy.yaml") -> Path:
    target = tmp_path / name
    shutil.copyfile(ROOT / "config" / name, target)
    return target


@pytest.fixture
def path(tmp_path: Path) -> Path:
    return _copy(tmp_path)


@pytest.fixture
def doc(path: Path) -> PolicyDocument:
    return PolicyDocument.open(path)


def _lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines(keepends=True)


def _without(lines: list[str], *spans: tuple[int, int]) -> str:
    """Text without the given 1-based inclusive line spans."""
    drop = {n for first, last in spans for n in range(first, last + 1)}
    return "".join(line for n, line in enumerate(lines, start=1) if n not in drop)


def _line_no(lines: list[str], start: str) -> int:
    return next(n for n, line in enumerate(lines, start=1) if line.startswith(start))


def _changes(doc: PolicyDocument) -> tuple[list[str], list[str]]:
    body = [line for line in doc.diff() if not line.startswith(("---", "+++", "@@"))]
    return (
        [line[1:] for line in body if line.startswith("-")],
        [line[1:] for line in body if line.startswith("+")],
    )


# ----------------------------------------------------------------- round trip


@pytest.mark.parametrize("source", POLICIES, ids=lambda p: p.name)
def test_every_shipped_policy_renders_byte_identically(tmp_path: Path, source: Path) -> None:
    doc = PolicyDocument.open(_copy(tmp_path, source.name))
    assert doc.render() == source.read_text(encoding="utf-8")
    assert not doc.dirty
    assert doc.diff() == []


@pytest.mark.parametrize("source", POLICIES, ids=lambda p: p.name)
def test_every_shipped_policy_is_valid(
    tmp_path: Path, source: Path, param_models: dict[str, type[BaseModel]]
) -> None:
    assert PolicyDocument.open(_copy(tmp_path, source.name)).validate(param_models) == []


# ----------------------------------------------------------------- set / unset / get


def test_scalar_change_touches_one_line_and_keeps_its_comment(doc: PolicyDocument) -> None:
    before = doc.revision
    doc.set(("limits", "max_tokens"), 2048)
    removed, added = _changes(doc)
    assert removed == ["  max_tokens: 1024       # requested max_tokens is clamped to this"]
    assert added == ["  max_tokens: 2048       # requested max_tokens is clamped to this"]
    assert doc.dirty
    assert doc.revision > before
    assert doc.diff()[:2] == ["--- policy.yaml (on disk)", "+++ policy.yaml (edited)"]


def test_quoted_string_keeps_its_quotes(doc: PolicyDocument) -> None:
    doc.set(("agents", "sig-probe-agent", "allowed_tools"), ["*", "lookup"])
    _, added = _changes(doc)
    assert added[0].startswith('    allowed_tools: ["*", lookup]')
    assert "# probes use unique tool names" in added[0]


def test_digit_only_string_stays_a_string(doc: PolicyDocument, path: Path) -> None:
    digits = "0" * 64
    doc.set(("agents", "demo-agent", "key_sha256"), digits)
    doc.save()
    assert PolicyDocument.open(path).get(("agents", "demo-agent", "key_sha256")) == digits


def test_missing_key_is_inserted_where_order_puts_it(doc: PolicyDocument) -> None:
    original = doc.render()
    doc.unset(("budgets", "small", "max_cost"))
    doc.set(("budgets", "small", "max_cost"), 0.05, order=BUDGET_ORDER)
    assert doc.render() == original
    doc.set(("budgets", "small", "note"), "x", order=BUDGET_ORDER)
    assert list(doc.get(("budgets", "small"))) == [*BUDGET_ORDER, "note"]


def test_missing_root_section_returns_between_its_neighbours(doc: PolicyDocument) -> None:
    original = doc.render()
    limits = doc.get(("limits",))
    doc.unset(("limits",))
    doc.set(("limits",), limits, order=ROOT_ORDER)
    # Same layout (blank lines around the section); only the comment of the old key is gone.
    assert doc.render() == original.replace("       # requested max_tokens is clamped to this", "")


def test_new_parents_are_created(doc: PolicyDocument) -> None:
    doc.set(("agents", "demo-agent", "extra", "deep"), 1)
    assert doc.get(("agents", "demo-agent", "extra")) == {"deep": 1}
    _, added = _changes(doc)
    assert added == ["    extra: {deep: 1}"]


def test_set_through_a_scalar_is_refused_without_changes(doc: PolicyDocument) -> None:
    original, revision = doc.render(), doc.revision
    with pytest.raises(DocumentError):
        doc.set(("version", "x"), 1)
    with pytest.raises(DocumentError):
        doc.set(("controls", 99), {})
    assert (doc.render(), doc.revision) == (original, revision)


def test_existing_mapping_is_updated_in_place(doc: PolicyDocument) -> None:
    budget = doc.get(("budgets", "default"))
    budget["max_requests"] = 10
    del budget["identical_window_s"]
    doc.set(("budgets", "default"), budget)
    removed, added = _changes(doc)
    assert removed == ["    max_requests: 300", "    identical_window_s: 10"]
    assert added == ["    max_requests: 10"]


def test_unset_of_a_missing_key_is_a_no_op(doc: PolicyDocument) -> None:
    revision = doc.revision
    doc.unset(("budgets", "nope", "max_cost"))
    assert doc.revision == revision
    assert not doc.dirty


def test_get_returns_plain_independent_copies(doc: PolicyDocument) -> None:
    agent = doc.get(("agents", "sig-probe-agent"))
    assert type(agent) is dict
    assert type(agent["allowed_tools"]) is list
    assert type(agent["allowed_tools"][0]) is str
    assert type(doc.get(("budgets", "default", "max_cost"))) is float
    agent["allowed_tools"].append("mutated")
    agent["budget"] = "mutated"
    assert doc.get(("agents", "sig-probe-agent", "allowed_tools")) == ["*"]
    assert not doc.dirty
    assert doc.get(("agents", "nobody"), "fallback") == "fallback"
    assert doc.get(("controls", 0, "id")) == "signatures"


# ----------------------------------------------------------------- comments


def test_set_comment_none_removes_only_that_comment(doc: PolicyDocument) -> None:
    doc.set_comment(("agents", "demo-agent", "key_sha256"), None)
    removed, added = _changes(doc)
    assert len(removed) == len(added) == 1
    assert added[0].rstrip().endswith("cbfd873b1c7ba0")
    assert "#" not in added[0]


def test_set_comment_none_on_a_section_key_line(doc: PolicyDocument) -> None:
    doc.set_comment(("agents", "ci-agent"), None)
    removed, added = _changes(doc)
    assert removed[0].startswith("  ci-agent:") and "# second agent" in removed[0]
    assert added == ["  ci-agent:"]


def test_new_comment_lines_up_with_its_siblings(doc: PolicyDocument) -> None:
    doc.set_comment(("limits", "max_messages"), "hard cap")
    _, added = _changes(doc)
    assert added == ["  max_messages: 100      # hard cap"]
    with pytest.raises(DocumentError):
        doc.set_comment(("limits", "missing"), "x")


# ----------------------------------------------------------------- named entries


def test_delete_last_agent_and_its_budget_keep_surrounding_lines(
    doc: PolicyDocument, path: Path, param_models: dict[str, type[BaseModel]]
) -> None:
    lines = _lines(path)
    agent = _line_no(lines, "  bench-agent:")
    budget = _line_no(lines, "  bench:")
    doc.delete_entry("agents", "bench-agent")
    doc.delete_entry("budgets", "bench")
    # Blank line before `budgets:`, blank line and comment before `controls:` all stay.
    assert doc.render() == _without(lines, (agent, agent + 4), (budget, budget + 6))
    assert doc.validate(param_models) == []


def test_added_agent_goes_before_the_blank_line(
    doc: PolicyDocument, path: Path, param_models: dict[str, type[BaseModel]]
) -> None:
    lines = _lines(path)
    after = _line_no(lines, "budgets:") - 2  # last line of the last agent
    doc.add_entry(
        "agents",
        "new-agent",
        {
            "key_sha256": "0" * 64,
            "allowed_models": ["llama3.2:3b"],
            "allowed_tools": [],
            "budget": "default",
        },
    )
    new = [
        "  new-agent:\n",
        f"    key_sha256: '{'0' * 64}'\n",
        "    allowed_models: [llama3.2:3b]\n",
        "    allowed_tools: []\n",
        "    budget: default\n",
    ]
    assert doc.render() == "".join(lines[:after] + new + lines[after:])
    assert doc.names("agents")[-1] == "new-agent"
    assert doc.validate(param_models) == []


def test_add_entry_refuses_empty_and_taken_names(doc: PolicyDocument) -> None:
    revision = doc.revision
    with pytest.raises(DocumentError):
        doc.add_entry("budgets", " ", {})
    with pytest.raises(DocumentError):
        doc.add_entry("budgets", "small", {})
    with pytest.raises(DocumentError):
        doc.rename_entry("budgets", "small", "default")
    assert doc.revision == revision


@pytest.mark.parametrize(
    ("section", "old", "new", "reference"),
    [
        ("upstreams", "ollama", "local", ("models", "llama3.2:3b", "upstream")),
        ("budgets", "small", "tiny", ("agents", "ci-agent", "budget")),
    ],
)
def test_rename_updates_references_and_keeps_layout(
    doc: PolicyDocument,
    param_models: dict[str, type[BaseModel]],
    section: str,
    old: str,
    new: str,
    reference: tuple[str, ...],
) -> None:
    names = doc.names(section)
    doc.rename_entry(section, old, new)
    assert doc.names(section) == [new if n == old else n for n in names]
    assert doc.get(reference) == new
    removed, added = _changes(doc)
    assert len(removed) == len(added) == 2  # the key line and the one reference
    assert doc.validate(param_models) == []


def test_rename_model_updates_every_agent_and_keeps_comments(
    doc: PolicyDocument, param_models: dict[str, type[BaseModel]]
) -> None:
    doc.rename_entry("models", "llama3.2:3b", "qwen:7b")
    assert doc.names("models") == ["qwen:7b"]
    for agent in doc.names("agents"):
        assert doc.get(("agents", agent, "allowed_models")) == ["qwen:7b"]
    assert "price_in_per_1k: 0.0002    # local compute is priced too" in doc.render()
    assert doc.validate(param_models) == []


def test_rename_agent_keeps_the_comment_of_its_line(doc: PolicyDocument) -> None:
    doc.rename_entry("agents", "ci-agent", "ci-bot")
    assert doc.names("agents")[1] == "ci-bot"
    _, added = _changes(doc)
    assert added == [
        "  ci-bot:                      # second agent: own key and a much smaller budget "
        "(limits per agent)"
    ]


@pytest.mark.parametrize(
    ("section", "name", "users"),
    [
        ("budgets", "small", ("agents.ci-agent",)),
        ("upstreams", "ollama", ("models.llama3.2:3b",)),
        (
            "budgets",
            "default",
            ("agents.demo-agent", "agents.tools-agent", "agents.sig-probe-agent"),
        ),
    ],
)
def test_delete_of_a_referenced_entry_is_refused(
    doc: PolicyDocument, section: str, name: str, users: tuple[str, ...]
) -> None:
    revision = doc.revision
    with pytest.raises(InUseError) as caught:
        doc.delete_entry(section, name)
    assert caught.value.users == users
    assert all(user in str(caught.value) for user in users)
    assert doc.revision == revision
    assert name in doc.names(section)


def test_users_of_a_model(doc: PolicyDocument) -> None:
    assert len(doc.users("models", "llama3.2:3b")) == len(doc.names("agents"))
    assert doc.users("models", "other") == []
    assert doc.users("agents", "demo-agent") == []


# ----------------------------------------------------------------- controls


def _ids(doc: PolicyDocument) -> list[str]:
    return [control["id"] for control in doc.get(("controls",))]


def test_add_control_appends_a_block_item(
    doc: PolicyDocument, path: Path, param_models: dict[str, type[BaseModel]]
) -> None:
    lines = _lines(path)
    index = doc.add_control(
        {"id": "pii.strict", "kind": "pii", "sides": ["input"], "action": "block", "threshold": 0.9}
    )
    assert index == len(_ids(doc)) - 1 and _ids(doc)[index] == "pii.strict"
    assert doc.render() == "".join(lines) + (
        "  - id: pii.strict\n"
        "    kind: pii\n"
        "    sides: [input]\n"
        "    action: block\n"
        "    threshold: 0.9\n"
    )
    assert doc.validate(param_models) == []
    with pytest.raises(DocumentError):
        doc.add_control({"id": "pii", "kind": "pii"})


def test_delete_first_control_keeps_the_section_comment(
    doc: PolicyDocument, path: Path, param_models: dict[str, type[BaseModel]]
) -> None:
    lines = _lines(path)
    first = _line_no(lines, "  - id: signatures")
    doc.delete_control(0)
    assert doc.render() == _without(lines, (first, first + 7))
    assert doc.validate(param_models) == []
    with pytest.raises(DocumentError):
        doc.delete_control(len(_ids(doc)))


def test_move_control_carries_its_comments(
    doc: PolicyDocument, path: Path, param_models: dict[str, type[BaseModel]]
) -> None:
    lines = _lines(path)
    first = _line_no(lines, "  - id: signatures")
    second = _line_no(lines, "  - id: pii")
    third = _line_no(lines, "  - id: secrets")
    assert doc.move_control(1, -1) == 0
    assert _ids(doc)[:2] == ["pii", "signatures"]
    swapped = lines[: first - 1] + lines[second - 1 : third - 1] + lines[first - 1 : second - 1]
    assert doc.render() == "".join(swapped + lines[third - 1 :])
    assert doc.validate(param_models) == []


def test_move_control_is_clamped(doc: PolicyDocument) -> None:
    ids = _ids(doc)
    assert doc.move_control(len(ids) - 1, -100) == 0
    assert _ids(doc) == [ids[-1], *ids[:-1]]
    revision = doc.revision
    assert doc.move_control(len(ids) - 1, 5) == len(ids) - 1
    assert doc.revision == revision


def test_moved_controls_leave_blank_lines_at_their_positions(tmp_path: Path) -> None:
    path = tmp_path / "p.yaml"
    path.write_text(
        "controls:\n"
        "  - id: a   # first\n"
        "    kind: pii\n"
        "\n"
        "  # second block\n"
        "  - id: b\n"
        "    kind: secrets\n",
        encoding="utf-8",
    )
    doc = PolicyDocument.open(path)
    doc.move_control(0, 1)
    assert doc.render() == (
        "controls:\n"
        "  - id: b\n"
        "    kind: secrets\n"
        "\n"
        "  # second block\n"
        "  - id: a   # first\n"
        "    kind: pii\n"
    )


# ----------------------------------------------------------------- validation


def test_validate_reports_the_proxy_errors(
    doc: PolicyDocument, param_models: dict[str, type[BaseModel]]
) -> None:
    doc.set(("controls", 1, "threshold"), 1.5)
    errors = doc.validate(param_models)
    assert errors and all(isinstance(e, str) for e in errors)
    assert any(e.startswith("controls.1.threshold") for e in errors)
    doc.set(("controls", 1, "threshold"), 0.5)
    assert doc.validate(param_models) == []


# ----------------------------------------------------------------- disk


def test_save_writes_atomically_and_keeps_the_mode(doc: PolicyDocument, path: Path) -> None:
    os.chmod(path, 0o640)
    doc.set(("limits", "max_tokens"), 2048)
    doc.save()
    assert path.read_text(encoding="utf-8") == doc.render()
    assert stat.S_IMODE(path.stat().st_mode) == 0o640
    assert sorted(p.name for p in path.parent.iterdir()) == ["policy.yaml"]
    assert not doc.dirty and doc.diff() == []


def test_failed_save_leaves_the_file_and_no_temp_file(
    doc: PolicyDocument, path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = path.read_bytes()
    doc.set(("limits", "max_tokens"), 2048)

    def refuse(*_: Any) -> None:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(os, "replace", refuse)
    with pytest.raises(DocumentError):
        doc.save()
    assert path.read_bytes() == original
    assert sorted(p.name for p in path.parent.iterdir()) == ["policy.yaml"]
    assert doc.dirty


def test_save_refuses_to_overwrite_an_external_change(doc: PolicyDocument, path: Path) -> None:
    external = path.read_text(encoding="utf-8").replace("max_messages: 100", "max_messages: 7")
    path.write_text(external, encoding="utf-8")
    doc.set(("limits", "max_tokens"), 2048)
    with pytest.raises(ConflictError):
        doc.save()
    assert path.read_text(encoding="utf-8") == external
    doc.save(force=True)
    assert path.read_text(encoding="utf-8") == doc.render()
    assert not doc.dirty
    doc.set(("limits", "max_tokens"), 4096)
    doc.save()  # the forced write is the new baseline


def test_reload_drops_edits(doc: PolicyDocument, path: Path) -> None:
    doc.set(("limits", "max_tokens"), 2048)
    revision = doc.revision
    doc.reload()
    assert doc.revision > revision
    assert not doc.dirty
    assert doc.get(("limits", "max_tokens")) == 1024
    path.write_text("version: 2\n", encoding="utf-8")
    doc.reload()
    assert doc.get(("version",)) == 2


@pytest.mark.parametrize(
    ("content", "location"),
    [
        (b"version: 1\nlimits: [a\n", "line 3:"),
        (b"version: 1\n  bad: indent\n", "line 2:"),
        (b"- a\n- b\n", None),
        (b"", None),
        (b"version: \xff\n", None),
    ],
)
def test_open_refuses_unusable_files(tmp_path: Path, content: bytes, location: str | None) -> None:
    path = tmp_path / "broken.yaml"
    path.write_bytes(content)
    with pytest.raises(DocumentError) as caught:
        PolicyDocument.open(path)
    assert str(path) in str(caught.value)
    if location is not None:
        assert location in str(caught.value)


def test_open_of_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(DocumentError):
        PolicyDocument.open(tmp_path / "missing.yaml")
