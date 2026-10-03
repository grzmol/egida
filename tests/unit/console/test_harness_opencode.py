from __future__ import annotations

import json
from pathlib import Path

import pytest

from egida.console.harnesses.base import Endpoint, HarnessEnv, HarnessError
from egida.console.harnesses.files import Ledger
from egida.console.harnesses.opencode import Opencode

ENDPOINT = Endpoint(base_url="http://127.0.0.1:8080", key="sk-egida-one", model="llama3.2:3b")


@pytest.fixture
def env(tmp_path: Path) -> HarnessEnv:
    home = tmp_path / "home"
    home.mkdir()
    return HarnessEnv(
        home=home, config_dir=tmp_path / "egida", environ={}, which=lambda _name: None
    )


def backups(env: HarnessEnv, harness_id: str) -> list[Path]:
    folder = env.config_dir / "backups" / harness_id
    return sorted(folder.iterdir()) if folder.is_dir() else []


def test_plan_matches_apply_and_writes_missing_file(env: HarnessEnv) -> None:
    harness = Opencode()
    planned = harness.plan(env, ENDPOINT)
    assert not harness.enabled(env)
    changes = harness.apply(env, ENDPOINT)
    assert planned == changes
    assert [c.action for c in changes] == ["create"] * len(changes)
    assert harness.enabled(env)
    assert harness.plan(env, ENDPOINT) == []


def test_remove_deletes_files_egida_created(env: HarnessEnv) -> None:
    harness = Opencode()
    harness.apply(env, ENDPOINT)
    harness.remove(env)
    for path in harness.config_paths(env):
        assert not path.exists()
    assert not harness.enabled(env)
    assert Ledger(env).get(harness.id) is None


def test_invalid_file_is_refused_and_untouched(env: HarnessEnv) -> None:
    harness = Opencode()
    path = harness.config_paths(env)[0]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{bad}", encoding="utf-8")
    with pytest.raises(HarnessError):
        harness.apply(env, ENDPOINT)
    assert path.read_text(encoding="utf-8") == "{bad}"
    assert Ledger(env).get(harness.id) is None


def test_apply_over_user_file_backs_up_and_remove_restores_exactly(env: HarnessEnv) -> None:
    harness = Opencode()
    originals = write_user_files(env)
    harness.apply(env, ENDPOINT)
    assert backups(env, harness.id)
    check_user_keys_kept(env)
    harness.remove(env)
    for path, text in originals.items():
        assert path.read_text(encoding="utf-8") == text
    assert not harness.enabled(env)


def test_reapply_replaces_key_in_place(env: HarnessEnv) -> None:
    harness = Opencode()
    originals = write_user_files(env)
    harness.apply(env, ENDPOINT)
    harness.apply(env, Endpoint(ENDPOINT.base_url, "sk-egida-two", ENDPOINT.model))
    texts = "".join(
        path.read_text(encoding="utf-8") for path in harness.config_paths(env) if path.exists()
    )
    assert "sk-egida-two" in texts
    assert "sk-egida-one" not in texts
    harness.remove(env)
    for path, text in originals.items():
        assert path.read_text(encoding="utf-8") == text


def test_not_enabled_when_config_no_longer_points_at_egida(env: HarnessEnv) -> None:
    harness = Opencode()
    harness.apply(env, ENDPOINT)
    for path in harness.config_paths(env):
        path.write_text(
            path.read_text(encoding="utf-8").replace("127.0.0.1:8080", "example.test"),
            encoding="utf-8",
        )
    assert not harness.enabled(env)


def write_user_files(env: HarnessEnv) -> dict[Path, str]:
    path = Opencode().config_paths(env)[0]
    path.parent.mkdir(parents=True)
    data = {
        "$schema": "https://opencode.ai/config.json",
        "model": "anthropic/claude",
        "provider": {"mine": {"name": "Mine"}},
    }
    text = json.dumps(data, indent=2) + "\n"
    path.write_text(text, encoding="utf-8")
    return {path: text}


def check_user_keys_kept(env: HarnessEnv) -> None:
    data = json.loads(Opencode().config_paths(env)[0].read_text(encoding="utf-8"))
    assert data["provider"]["mine"] == {"name": "Mine"}
    assert data["$schema"] == "https://opencode.ai/config.json"


def test_provider_shape(env: HarnessEnv) -> None:
    Opencode().apply(env, ENDPOINT)
    data = json.loads(
        (env.home / ".config" / "opencode" / "opencode.json").read_text(encoding="utf-8")
    )
    assert data["model"] == "egida/llama3.2:3b"
    assert data["provider"]["egida"] == {
        "npm": "@ai-sdk/openai-compatible",
        "name": "Egida",
        "options": {"baseURL": "http://127.0.0.1:8080/v1", "apiKey": "sk-egida-one"},
        "models": {"llama3.2:3b": {"name": "llama3.2:3b (Egida)"}},
    }


def test_xdg_config_home_is_honoured(tmp_path: Path) -> None:
    env = HarnessEnv(
        home=tmp_path,
        config_dir=tmp_path / "egida",
        environ={"XDG_CONFIG_HOME": str(tmp_path / "xdg")},
        which=lambda _n: None,
    )
    assert Opencode().config_paths(env) == (tmp_path / "xdg" / "opencode" / "opencode.json",)


def test_user_edit_after_apply_is_kept_on_remove(env: HarnessEnv) -> None:
    write_user_files(env)
    harness = Opencode()
    harness.apply(env, ENDPOINT)
    path = harness.config_paths(env)[0]
    data = json.loads(path.read_text(encoding="utf-8"))
    data["model"] = "mine/other"
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    harness.remove(env)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["model"] == "mine/other"
    assert "egida" not in data["provider"]
