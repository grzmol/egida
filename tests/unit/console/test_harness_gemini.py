"""Gemini CLI (~/.gemini/.env) and Antigravity CLI (settings.json, launch env), temporary home."""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from egida.console.harnesses.base import Endpoint, HarnessEnv, HarnessError
from egida.console.harnesses.files import Ledger, read_dotenv
from egida.console.harnesses.gemini import AntigravityCli, GeminiCli

ENDPOINT = Endpoint("http://127.0.0.1:8080", "sk-egida-first", "llama3.2:3b")
GEMINI = GeminiCli()
AGY = AntigravityCli()

USER_DOTENV = "# my gemini settings\nGEMINI_API_KEY=AIza-user\nGEMINI_SANDBOX=true\n"


@pytest.fixture
def env(tmp_path: Path) -> HarnessEnv:
    home = tmp_path / "home"
    home.mkdir()
    return HarnessEnv(
        home=home, config_dir=tmp_path / "egida", environ={}, which=lambda _name: None
    )


def dotenv(env: HarnessEnv) -> Path:
    return env.home / ".gemini" / ".env"


def agy_settings(env: HarnessEnv) -> Path:
    return env.home / ".gemini" / "antigravity-cli" / "settings.json"


def launch_file(env: HarnessEnv) -> Path:
    return env.config_dir / "launch" / "antigravity-cli.env"


def gemini_settings(env: HarnessEnv) -> Path:
    return env.home / ".gemini" / "settings.json"


# --- Gemini CLI -----------------------------------------------------------------------------------


def test_gemini_apply_on_missing_files(env: HarnessEnv) -> None:
    changes = GEMINI.apply(env, ENDPOINT)
    assert [(c.path, c.action) for c in changes] == [
        (dotenv(env), "create"),
        (gemini_settings(env), "create"),
    ]
    assert read_dotenv(dotenv(env)) == {
        "GOOGLE_GEMINI_BASE_URL": "http://127.0.0.1:8080",
        "GEMINI_API_KEY": "sk-egida-first",
        "GEMINI_MODEL": "llama3.2:3b",
    }
    assert json.loads(gemini_settings(env).read_text()) == {
        "security": {"auth": {"selectedType": "gemini-api-key"}}
    }
    assert stat.S_IMODE(dotenv(env).stat().st_mode) == 0o600
    assert GEMINI.enabled(env)
    GEMINI.remove(env)
    assert not dotenv(env).exists() and not gemini_settings(env).exists()
    assert not GEMINI.enabled(env)


def test_gemini_settings_keep_user_keys_and_restore_auth_type(env: HarnessEnv) -> None:
    path = gemini_settings(env)
    path.parent.mkdir(parents=True)
    user = {
        "security": {"auth": {"selectedType": "oauth-personal"}, "folderTrust": {"enabled": True}}
    }
    path.write_text(json.dumps(user))
    GEMINI.apply(env, ENDPOINT)
    data = json.loads(path.read_text())
    assert data["security"]["auth"]["selectedType"] == "gemini-api-key"
    assert data["security"]["folderTrust"] == {"enabled": True}
    GEMINI.remove(env)
    assert json.loads(path.read_text()) == user


def test_gemini_launch_passes_egida_variables(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    env = HarnessEnv(home, tmp_path / "egida", {}, {"gemini": "/opt/bin/gemini"}.get)
    with pytest.raises(HarnessError, match="not set up for Egida"):
        GEMINI.launch(env, [])
    path = dotenv(env)
    path.parent.mkdir(parents=True)
    path.write_text(USER_DOTENV)
    GEMINI.apply(env, ENDPOINT)
    argv, extra = GEMINI.launch(env, ["-p", "hi"])
    assert argv == ["/opt/bin/gemini", "-p", "hi"]
    assert extra == {
        "GOOGLE_GEMINI_BASE_URL": "http://127.0.0.1:8080",
        "GEMINI_API_KEY": ENDPOINT.key,
        "GEMINI_MODEL": "llama3.2:3b",
    }


def test_gemini_keeps_user_lines_and_restores_previous_key(env: HarnessEnv) -> None:
    path = dotenv(env)
    path.parent.mkdir(parents=True)
    path.write_text(USER_DOTENV)
    planned = GEMINI.plan(env, ENDPOINT)
    assert path.read_text() == USER_DOTENV
    assert GEMINI.apply(env, ENDPOINT) == planned
    text = path.read_text()
    assert text.startswith(
        "# my gemini settings\nGEMINI_API_KEY=sk-egida-first\nGEMINI_SANDBOX=true\n"
    )
    assert [c.read_text() for c in (env.config_dir / "backups" / GEMINI.id).iterdir()] == [
        USER_DOTENV
    ]
    assert "sk-egida-first" not in Ledger(env).path.read_text()
    GEMINI.remove(env)
    assert path.read_text() == USER_DOTENV


def test_gemini_enabled_tracks_the_base_url(env: HarnessEnv) -> None:
    GEMINI.apply(env, ENDPOINT)
    dotenv(env).write_text(dotenv(env).read_text().replace("127.0.0.1:8080", "example.com"))
    assert not GEMINI.enabled(env)


def test_gemini_reapply_updates_in_place(env: HarnessEnv) -> None:
    path = dotenv(env)
    path.parent.mkdir(parents=True)
    path.write_text(USER_DOTENV)
    GEMINI.apply(env, ENDPOINT)
    GEMINI.apply(env, Endpoint("http://127.0.0.1:9090", "sk-egida-second", "qwen3:8b"))
    values = read_dotenv(path)
    assert values["GEMINI_API_KEY"] == "sk-egida-second"
    assert values["GOOGLE_GEMINI_BASE_URL"] == "http://127.0.0.1:9090"
    assert path.read_text().count("GEMINI_API_KEY=") == 1
    GEMINI.remove(env)
    assert path.read_text() == USER_DOTENV


# --- Antigravity CLI ------------------------------------------------------------------------------


def test_agy_apply_writes_settings_and_private_launch_env(env: HarnessEnv) -> None:
    changes = AGY.apply(env, ENDPOINT)
    assert [(c.path, c.action) for c in changes] == [
        (agy_settings(env), "create"),
        (launch_file(env), "create"),
    ]
    assert json.loads(agy_settings(env).read_text()) == {"modelProvider": "gemini"}
    assert read_dotenv(launch_file(env)) == {
        "GOOGLE_GEMINI_BASE_URL": "http://127.0.0.1:8080",
        "GEMINI_API_KEY": "sk-egida-first",
        "GEMINI_MODEL": "llama3.2:3b",
    }
    assert stat.S_IMODE(launch_file(env).stat().st_mode) == 0o600
    assert stat.S_IMODE(env.config_dir.stat().st_mode) == 0o700
    assert AGY.enabled(env)


def test_agy_remove_restores_settings_and_deletes_launch_env(env: HarnessEnv) -> None:
    path = agy_settings(env)
    path.parent.mkdir(parents=True)
    user = {"modelProvider": "google", "ui": {"theme": "light"}}
    path.write_text(json.dumps(user))
    planned = AGY.plan(env, ENDPOINT)
    assert AGY.apply(env, ENDPOINT) == planned
    assert json.loads(path.read_text()) == {"modelProvider": "gemini", "ui": {"theme": "light"}}
    AGY.remove(env)
    assert json.loads(path.read_text()) == user
    assert not launch_file(env).exists()
    assert not AGY.enabled(env)


def test_agy_invalid_settings_are_refused(env: HarnessEnv) -> None:
    path = agy_settings(env)
    path.parent.mkdir(parents=True)
    path.write_text("{oops")
    with pytest.raises(HarnessError, match="is not valid JSON"):
        AGY.apply(env, ENDPOINT)
    assert path.read_text() == "{oops"
    assert not launch_file(env).exists()
