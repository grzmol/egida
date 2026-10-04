"""Claude Code harness: the env block of settings.json, on a temporary home."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from egida.console.harnesses.base import Endpoint, HarnessEnv, HarnessError
from egida.console.harnesses.claude import ClaudeCode
from egida.console.harnesses.files import Ledger

ENDPOINT = Endpoint("http://127.0.0.1:8080", "sk-egida-first", "llama3.2:3b")
HARNESS = ClaudeCode()

USER_SETTINGS = {
    "permissions": {"allow": ["Bash(ls:*)"]},
    "env": {"ANTHROPIC_MODEL": "claude-opus-4", "MY_VAR": "keep"},
    "theme": "dark",
}


@pytest.fixture
def env(tmp_path: Path) -> HarnessEnv:
    home = tmp_path / "home"
    home.mkdir()
    return HarnessEnv(
        home=home, config_dir=tmp_path / "egida", environ={}, which=lambda _name: None
    )


def settings(env: HarnessEnv) -> Path:
    return env.home / ".claude" / "settings.json"


def write_user_settings(env: HarnessEnv) -> Path:
    path = settings(env)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(USER_SETTINGS, indent=2) + "\n")
    return path


def test_apply_on_missing_file_creates_env_block(env: HarnessEnv) -> None:
    changes = HARNESS.apply(env, ENDPOINT)
    assert [(c.path, c.action) for c in changes] == [(settings(env), "create")]
    block = json.loads(settings(env).read_text())["env"]
    assert block["ANTHROPIC_BASE_URL"] == "http://127.0.0.1:8080"
    assert block["ANTHROPIC_AUTH_TOKEN"] == ENDPOINT.key
    for name in (
        "ANTHROPIC_MODEL",
        "ANTHROPIC_DEFAULT_OPUS_MODEL",
        "ANTHROPIC_DEFAULT_SONNET_MODEL",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL",
        "CLAUDE_CODE_SUBAGENT_MODEL",
    ):
        assert block[name] == "llama3.2:3b"
    assert block["CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS"] == "1"
    assert block["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] == "1"
    assert HARNESS.enabled(env)
    assert "sk-egida-first" not in Ledger(env).path.read_text()


def test_remove_after_create_deletes_the_file(env: HarnessEnv) -> None:
    HARNESS.apply(env, ENDPOINT)
    changes = HARNESS.remove(env)
    assert [(c.path, c.action) for c in changes] == [(settings(env), "delete")]
    assert not settings(env).exists()
    assert not HARNESS.enabled(env)
    assert Ledger(env).get(HARNESS.id) is None


def test_apply_keeps_user_keys_and_remove_restores_exactly(env: HarnessEnv) -> None:
    path = write_user_settings(env)
    planned = HARNESS.plan(env, ENDPOINT)
    assert path.read_text() == json.dumps(USER_SETTINGS, indent=2) + "\n"
    applied = HARNESS.apply(env, ENDPOINT)
    assert planned == applied
    assert [c.action for c in applied] == ["update"]
    data = json.loads(path.read_text())
    assert data["permissions"] == USER_SETTINGS["permissions"] and data["theme"] == "dark"
    assert data["env"]["MY_VAR"] == "keep"
    assert data["env"]["ANTHROPIC_MODEL"] == "llama3.2:3b"
    assert HARNESS.state(env).enabled

    HARNESS.remove(env)
    assert json.loads(path.read_text()) == USER_SETTINGS
    assert not HARNESS.enabled(env)


def test_backup_is_taken_before_writing(env: HarnessEnv) -> None:
    path = write_user_settings(env)
    original = path.read_text()
    HARNESS.apply(env, ENDPOINT)
    copies = list((env.config_dir / "backups" / HARNESS.id).iterdir())
    assert len(copies) == 1 and copies[0].read_text() == original


def test_reapply_replaces_key_and_remove_still_restores_original(env: HarnessEnv) -> None:
    path = write_user_settings(env)
    HARNESS.apply(env, ENDPOINT)
    assert HARNESS.plan(env, ENDPOINT) == []
    second = Endpoint("http://127.0.0.1:9090", "sk-egida-second", "qwen3:8b")
    HARNESS.apply(env, second)
    block = json.loads(path.read_text())["env"]
    assert block["ANTHROPIC_AUTH_TOKEN"] == second.key
    assert block["ANTHROPIC_BASE_URL"] == "http://127.0.0.1:9090"
    assert HARNESS.enabled(env)
    HARNESS.remove(env)
    assert json.loads(path.read_text()) == USER_SETTINGS


def test_remove_keeps_values_the_user_changed_after_apply(env: HarnessEnv) -> None:
    path = write_user_settings(env)
    HARNESS.apply(env, ENDPOINT)
    data = json.loads(path.read_text())
    data["env"]["ANTHROPIC_MODEL"] = "user-choice"
    path.write_text(json.dumps(data))
    HARNESS.remove(env)
    restored = json.loads(path.read_text())
    assert restored["env"] == {"ANTHROPIC_MODEL": "user-choice", "MY_VAR": "keep"}


def test_enabled_is_false_when_the_user_points_elsewhere(env: HarnessEnv) -> None:
    path = write_user_settings(env)
    HARNESS.apply(env, ENDPOINT)
    data = json.loads(path.read_text())
    data["env"]["ANTHROPIC_BASE_URL"] = "https://api.anthropic.com"
    path.write_text(json.dumps(data))
    assert not HARNESS.enabled(env)


@pytest.mark.parametrize("text", ["{not json", '{"env": "oops"}'])
def test_invalid_file_is_refused_and_untouched(env: HarnessEnv, text: str) -> None:
    path = settings(env)
    path.parent.mkdir(parents=True)
    path.write_text(text)
    with pytest.raises(HarnessError, match=str(path)):
        HARNESS.apply(env, ENDPOINT)
    assert path.read_text() == text
    assert Ledger(env).get(HARNESS.id) is None
    assert not HARNESS.enabled(env)


def test_claude_config_dir_is_honoured(env: HarnessEnv, tmp_path: Path) -> None:
    custom = HarnessEnv(
        env.home, env.config_dir, {"CLAUDE_CONFIG_DIR": str(tmp_path / "cc")}, env.which
    )
    HARNESS.apply(custom, ENDPOINT)
    assert (tmp_path / "cc" / "settings.json").exists()
    assert not settings(env).exists()


def test_launch_is_refused_for_config_mode(env: HarnessEnv) -> None:
    with pytest.raises(HarnessError, match="not started through Egida"):
        HARNESS.launch(env, [])
