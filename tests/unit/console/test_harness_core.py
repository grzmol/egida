"""Harness registry and the shared file helpers (atomic writes, backups, dotenv, ledger, merges)."""

from __future__ import annotations

import json
import stat
from collections.abc import Callable
from pathlib import Path

import pytest
import tomlkit

from egida.console.harnesses import REGISTRY, by_id
from egida.console.harnesses.base import Endpoint, HarnessEnv, HarnessError
from egida.console.harnesses.files import (
    KEEP_BACKUPS,
    Ledger,
    atomic_write,
    backup,
    dump_toml,
    load_json,
    load_toml,
    load_yaml,
    restore_entries,
    set_entries,
    update_dotenv,
)
from egida.console.harnesses.unavailable import AntigravityIde, Cursor

EXPECTED = [
    ("claude-code", "anthropic", "config"),
    ("codex", "openai-responses", "config"),
    ("antigravity-cli", "gemini", "launch"),
    ("antigravity", None, "unavailable"),
    ("gemini-cli", "gemini", "config"),
    ("opencode", "openai-chat", "config"),
    ("aider", "openai-chat", "config"),
    ("droid", "openai-chat", "config"),
    ("pi", "openai-chat", "config"),
    ("omp", "openai-chat", "config"),
    ("continue", "openai-chat", "config"),
    ("copilot-cli", "openai-chat", "launch"),
    ("cursor", None, "unavailable"),
]


@pytest.fixture
def env(tmp_path: Path) -> HarnessEnv:
    home = tmp_path / "home"
    home.mkdir()
    return HarnessEnv(
        home=home, config_dir=tmp_path / "egida", environ={}, which=lambda _name: None
    )


def mode_of(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_registry_matches_the_table() -> None:
    assert [(h.id, h.protocol, h.mode) for h in REGISTRY] == EXPECTED
    assert len({h.id for h in REGISTRY}) == len(REGISTRY)
    assert by_id("codex") is REGISTRY[1]


def test_by_id_unknown_names_the_known_ids() -> None:
    with pytest.raises(KeyError, match="known harnesses: claude-code, codex"):
        by_id("windsurf")


@pytest.mark.parametrize("harness", [AntigravityIde(), Cursor()], ids=lambda h: h.id)
def test_unavailable_harnesses_refuse_changes(
    env: HarnessEnv, harness: AntigravityIde | Cursor
) -> None:
    endpoint = Endpoint("http://127.0.0.1:8080", "sk-egida-x", "llama3.2:3b")
    with pytest.raises(HarnessError, match="cannot use Egida"):
        harness.apply(env, endpoint)
    with pytest.raises(HarnessError):
        harness.plan(env, endpoint)
    with pytest.raises(HarnessError):
        harness.launch(env, [])
    assert harness.remove(env) == []
    assert not harness.state(env).enabled
    assert list(env.home.iterdir()) == []


def test_installed_detects_binary_on_path_or_config_dir(env: HarnessEnv) -> None:
    claude = by_id("claude-code")
    assert not claude.installed(env)
    assert claude.state(env).detail == "not found · ~/.claude/settings.json"
    found = HarnessEnv(
        env.home, env.config_dir, {}, lambda name: f"/usr/bin/{name}" if name == "claude" else None
    )
    assert claude.installed(found)
    assert claude.state(found).detail.startswith("found claude on PATH")
    (env.home / ".claude").mkdir()
    assert claude.installed(env)


def test_env_dir_variables_override_home(env: HarnessEnv, tmp_path: Path) -> None:
    custom = HarnessEnv(
        env.home, env.config_dir, {"CLAUDE_CONFIG_DIR": str(tmp_path / "cc")}, env.which
    )
    assert by_id("claude-code").config_paths(custom) == (tmp_path / "cc" / "settings.json",)
    tilde = HarnessEnv(env.home, env.config_dir, {"CODEX_HOME": "~/cx"}, env.which)
    assert by_id("codex").config_paths(tilde)[0] == env.home / "cx" / "config.toml"


def test_atomic_write_keeps_existing_mode_and_sets_new_mode(tmp_path: Path) -> None:
    target = tmp_path / "a" / "b.txt"
    atomic_write(target, "one")
    assert target.read_text() == "one" and mode_of(target) == 0o644
    target.chmod(0o640)
    atomic_write(target, "two")
    assert target.read_text() == "two" and mode_of(target) == 0o640
    secret = tmp_path / "s.env"
    atomic_write(secret, "k", mode=0o600)
    assert mode_of(secret) == 0o600
    assert sorted(p.name for p in target.parent.iterdir()) == ["b.txt"]


def test_backup_keeps_the_newest_five(env: HarnessEnv, tmp_path: Path) -> None:
    assert backup(env, "codex", tmp_path / "missing.toml") is None
    source = tmp_path / "config.toml"
    copies = []
    for n in range(KEEP_BACKUPS + 2):
        source.write_text(f"v{n}")
        copy = backup(env, "codex", source)
        assert copy is not None
        copies.append(copy)
    folder = env.config_dir / "backups" / "codex"
    kept = sorted(folder.iterdir())
    assert len(kept) == KEEP_BACKUPS
    assert set(kept) == set(copies[-KEEP_BACKUPS:])
    assert copies[-1].read_text() == f"v{KEEP_BACKUPS + 1}"
    assert mode_of(copies[-1]) == 0o600
    assert mode_of(env.config_dir) == 0o700


@pytest.mark.parametrize(
    ("loader", "text", "message"),
    [
        (load_json, "{nope", "is not valid JSON"),
        (load_json, "[1, 2]", "does not hold a JSON object"),
        (load_yaml, "a: [1, 2", "is not valid YAML"),
        (load_yaml, "- 1\n- 2\n", "does not hold a YAML mapping"),
        (load_toml, "a = = 1", "is not valid TOML"),
    ],
)
def test_loaders_name_the_broken_file(
    tmp_path: Path, loader: Callable[[Path], object], text: str, message: str
) -> None:
    path = tmp_path / "broken"
    path.write_text(text)
    with pytest.raises(HarnessError, match=message) as info:
        loader(path)
    assert str(path) in str(info.value)


def test_loaders_return_empty_for_missing_files(tmp_path: Path) -> None:
    assert load_json(tmp_path / "x.json") == {}
    assert dict(load_yaml(tmp_path / "x.yaml")) == {}
    assert dump_toml(load_toml(tmp_path / "x.toml")) == ""


def test_update_dotenv_keeps_comments_and_reports_previous(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text("# mine\nexport A=1\nB='two words'  \nC=3 # note\n")
    previous = update_dotenv(path, {"A": "new", "B": None, "D": "x y"})
    assert previous == {"A": "1", "B": "two words", "D": None}
    assert path.read_text() == '# mine\nA=new\nC=3 # note\nD="x y"\n'
    created = tmp_path / "new.env"
    update_dotenv(created, {"K": "v"})
    assert created.read_text() == "K=v\n" and mode_of(created) == 0o600


def test_set_and_restore_entries_round_trip_toml_with_comments() -> None:
    original = '# top\nmodel = "gpt-5"\n\n[profiles.x]\na = 2 # keep\n'
    doc = tomlkit.parse(original)
    values = {("model",): "llama3.2:3b", ("model_providers", "egida"): {"token": "sk-egida-secret"}}
    entries = set_entries(doc, values)
    assert 'model = "llama3.2:3b"' in dump_toml(doc)
    assert "[model_providers.egida]" in dump_toml(doc)
    assert "sk-" not in json.dumps(entries)
    restore_entries(doc, entries)
    assert dump_toml(doc) == original


def test_restore_keeps_values_the_user_changed_later() -> None:
    data: dict[str, object] = {"env": {"A": "user"}}
    entries = set_entries(data, {("env", "A"): "egida", ("env", "B"): "egida"})
    data["env"] = {"A": "edited by user", "B": "egida"}
    restore_entries(data, entries)
    assert data == {"env": {"A": "edited by user"}}


def test_second_apply_keeps_the_original_previous_value() -> None:
    data: dict[str, object] = {"model": "mine"}
    first = set_entries(data, {("model",): "a"})
    second = set_entries(data, {("model",): "b"}, first)
    restore_entries(data, second)
    assert data == {"model": "mine"}


def test_ledger_round_trip_is_private(env: HarnessEnv) -> None:
    ledger = Ledger(env)
    assert ledger.get("codex") is None
    ledger.put("codex", {"base_url": "http://h"})
    ledger.put("pi", {"base_url": "http://p"})
    assert ledger.get("codex") == {"base_url": "http://h"}
    assert mode_of(ledger.path) == 0o600
    assert ledger.pop("codex") == {"base_url": "http://h"}
    assert ledger.get("codex") is None and ledger.get("pi") is not None
