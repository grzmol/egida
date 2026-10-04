"""Codex harness: provider egida in config.toml plus the model catalog, on a temporary home."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest

from egida.console.harnesses.base import Endpoint, HarnessEnv, HarnessError
from egida.console.harnesses.codex import Codex
from egida.console.harnesses.files import Ledger

ENDPOINT = Endpoint("http://127.0.0.1:8080", "sk-egida-first", "llama3.2:3b")
HARNESS = Codex()

USER_CONFIG = """\
# my codex settings
model = "gpt-5-codex"  # favourite
approval_policy = "on-request"

[model_providers.work]
name = "Work"
base_url = "https://llm.example.com/v1"

[projects."/work/x"]
trust_level = "trusted"
"""


@pytest.fixture
def env(tmp_path: Path) -> HarnessEnv:
    home = tmp_path / "home"
    home.mkdir()
    return HarnessEnv(
        home=home, config_dir=tmp_path / "egida", environ={}, which=lambda _name: None
    )


def config(env: HarnessEnv) -> Path:
    return env.home / ".codex" / "config.toml"


def catalog(env: HarnessEnv) -> Path:
    return env.home / ".codex" / "egida-models.json"


def write_user_config(env: HarnessEnv) -> Path:
    path = config(env)
    path.parent.mkdir(parents=True)
    path.write_text(USER_CONFIG)
    return path


def test_apply_on_missing_file_writes_provider_and_catalog(env: HarnessEnv) -> None:
    changes = HARNESS.apply(env, ENDPOINT)
    assert [(c.path, c.action) for c in changes] == [
        (config(env), "create"),
        (catalog(env), "create"),
    ]
    data = tomllib.loads(config(env).read_text())
    assert data["model_provider"] == "egida"
    assert data["model"] == "llama3.2:3b"
    assert data["model_catalog_json"] == str(catalog(env))
    assert data["web_search"] == "disabled"
    assert data["model_providers"]["egida"] == {
        "name": "Egida",
        "base_url": "http://127.0.0.1:8080/v1",
        "wire_api": "responses",
        "experimental_bearer_token": "sk-egida-first",
    }
    entry = json.loads(catalog(env).read_text())["models"][0]
    assert entry["slug"] == entry["display_name"] == "llama3.2:3b"
    assert entry["context_window"] == 131072
    assert HARNESS.enabled(env)
    assert "sk-egida-first" not in Ledger(env).path.read_text()


def test_remove_after_create_deletes_both_files(env: HarnessEnv) -> None:
    HARNESS.apply(env, ENDPOINT)
    changes = HARNESS.remove(env)
    assert {(c.path, c.action) for c in changes} == {
        (config(env), "delete"),
        (catalog(env), "delete"),
    }
    assert not config(env).exists() and not catalog(env).exists()
    assert not HARNESS.enabled(env)


def test_apply_keeps_comments_and_remove_restores_the_file(env: HarnessEnv) -> None:
    path = write_user_config(env)
    planned = HARNESS.plan(env, ENDPOINT)
    assert path.read_text() == USER_CONFIG and not catalog(env).exists()
    applied = HARNESS.apply(env, ENDPOINT)
    assert planned == applied
    text = path.read_text()
    assert "# my codex settings" in text and "# favourite" in text
    data = tomllib.loads(text)
    assert data["model"] == "llama3.2:3b"
    assert data["approval_policy"] == "on-request"
    assert data["model_providers"]["work"]["name"] == "Work"
    assert data["projects"]["/work/x"]["trust_level"] == "trusted"
    assert HARNESS.enabled(env)

    HARNESS.remove(env)
    assert path.read_text() == USER_CONFIG
    assert not catalog(env).exists()
    assert not HARNESS.enabled(env)


def test_top_level_keys_land_before_tables(env: HarnessEnv) -> None:
    path = config(env)
    path.parent.mkdir(parents=True)
    path.write_text("[tui]\nnotifications = true\n")
    HARNESS.apply(env, ENDPOINT)
    data = tomllib.loads(path.read_text())
    assert data["model_provider"] == "egida"
    assert data["tui"] == {"notifications": True}
    HARNESS.remove(env)
    assert path.read_text() == "[tui]\nnotifications = true\n"


def test_backup_is_taken_before_writing(env: HarnessEnv) -> None:
    write_user_config(env)
    HARNESS.apply(env, ENDPOINT)
    copies = list((env.config_dir / "backups" / HARNESS.id).iterdir())
    assert [c.read_text() for c in copies] == [USER_CONFIG]


def test_reapply_updates_in_place(env: HarnessEnv) -> None:
    path = write_user_config(env)
    HARNESS.apply(env, ENDPOINT)
    second = Endpoint("http://127.0.0.1:9090", "sk-egida-second", "qwen3:8b")
    HARNESS.apply(env, second)
    data = tomllib.loads(path.read_text())
    assert data["model_providers"]["egida"]["experimental_bearer_token"] == second.key
    assert data["model_providers"]["egida"]["base_url"] == "http://127.0.0.1:9090/v1"
    assert json.loads(catalog(env).read_text())["models"][0]["slug"] == "qwen3:8b"
    assert path.read_text().count("[model_providers.egida]") == 1
    assert HARNESS.enabled(env)
    HARNESS.remove(env)
    assert path.read_text() == USER_CONFIG


def test_enabled_is_false_when_the_user_switches_provider(env: HarnessEnv) -> None:
    path = write_user_config(env)
    HARNESS.apply(env, ENDPOINT)
    path.write_text(path.read_text().replace('model_provider = "egida"', 'model_provider = "work"'))
    assert not HARNESS.enabled(env)


def test_invalid_toml_is_refused_and_untouched(env: HarnessEnv) -> None:
    path = config(env)
    path.parent.mkdir(parents=True)
    path.write_text("model = = 1\n")
    with pytest.raises(HarnessError, match="is not valid TOML"):
        HARNESS.apply(env, ENDPOINT)
    assert path.read_text() == "model = = 1\n"
    assert not catalog(env).exists()
    assert Ledger(env).get(HARNESS.id) is None


def test_codex_home_is_honoured(env: HarnessEnv, tmp_path: Path) -> None:
    custom = HarnessEnv(env.home, env.config_dir, {"CODEX_HOME": str(tmp_path / "cx")}, env.which)
    HARNESS.apply(custom, ENDPOINT)
    data = tomllib.loads((tmp_path / "cx" / "config.toml").read_text())
    assert data["model_catalog_json"] == str(tmp_path / "cx" / "egida-models.json")
