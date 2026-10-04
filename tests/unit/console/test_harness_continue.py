from __future__ import annotations

from pathlib import Path

import pytest

from egida.console.harnesses.base import Endpoint, HarnessEnv, HarnessError
from egida.console.harnesses.continue_dev import ContinueDev
from egida.console.harnesses.files import Ledger

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
    harness = ContinueDev()
    planned = harness.plan(env, ENDPOINT)
    assert not harness.enabled(env)
    changes = harness.apply(env, ENDPOINT)
    assert planned == changes
    assert [c.action for c in changes] == ["create"] * len(changes)
    assert harness.enabled(env)
    assert harness.plan(env, ENDPOINT) == []


def test_remove_deletes_files_egida_created(env: HarnessEnv) -> None:
    harness = ContinueDev()
    harness.apply(env, ENDPOINT)
    harness.remove(env)
    for path in harness.config_paths(env):
        assert not path.exists()
    assert not harness.enabled(env)
    assert Ledger(env).get(harness.id) is None


def test_invalid_file_is_refused_and_untouched(env: HarnessEnv) -> None:
    harness = ContinueDev()
    path = harness.config_paths(env)[0]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("a: [unclosed\n", encoding="utf-8")
    with pytest.raises(HarnessError):
        harness.apply(env, ENDPOINT)
    assert path.read_text(encoding="utf-8") == "a: [unclosed\n"
    assert Ledger(env).get(harness.id) is None


def test_apply_over_user_file_backs_up_and_remove_restores_exactly(env: HarnessEnv) -> None:
    harness = ContinueDev()
    originals = write_user_files(env)
    harness.apply(env, ENDPOINT)
    assert backups(env, harness.id)
    check_user_keys_kept(env)
    harness.remove(env)
    for path, text in originals.items():
        assert path.read_text(encoding="utf-8") == text
    assert not harness.enabled(env)


def test_reapply_replaces_key_in_place(env: HarnessEnv) -> None:
    harness = ContinueDev()
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
    harness = ContinueDev()
    harness.apply(env, ENDPOINT)
    for path in harness.config_paths(env):
        path.write_text(
            path.read_text(encoding="utf-8").replace("127.0.0.1:8080", "example.test"),
            encoding="utf-8",
        )
    assert not harness.enabled(env)


USER_TEXT = """name: Mine
version: 1.0.0
schema: v1
# models
models:
  - name: GPT
    provider: openai
    model: gpt-4o
"""


def write_user_files(env: HarnessEnv) -> dict[Path, str]:
    path = ContinueDev().config_paths(env)[0]
    path.parent.mkdir(parents=True)
    path.write_text(USER_TEXT, encoding="utf-8")
    return {path: USER_TEXT}


def check_user_keys_kept(env: HarnessEnv) -> None:
    text = ContinueDev().config_paths(env)[0].read_text(encoding="utf-8")
    assert "# models" in text
    assert "name: GPT" in text


def test_new_file_has_scaffold_and_model(env: HarnessEnv) -> None:
    from egida.console.harnesses.files import load_yaml, plain

    ContinueDev().apply(env, ENDPOINT)
    data = plain(load_yaml(env.home / ".continue" / "config.yaml"))
    assert data == {
        "name": "Local Config",
        "version": "1.0.0",
        "schema": "v1",
        "models": [
            {
                "name": "Egida llama3.2:3b",
                "provider": "openai",
                "model": "llama3.2:3b",
                "apiBase": "http://127.0.0.1:8080/v1",
                "apiKey": "sk-egida-one",
                "roles": ["chat", "edit", "apply"],
            }
        ],
    }


def test_reapply_keeps_one_entry(env: HarnessEnv) -> None:
    from egida.console.harnesses.files import load_yaml, plain

    write_user_files(env)
    ContinueDev().apply(env, ENDPOINT)
    ContinueDev().apply(env, Endpoint(ENDPOINT.base_url, "sk-egida-two", "qwen3:8b"))
    names = [m["name"] for m in plain(load_yaml(env.home / ".continue" / "config.yaml"))["models"]]
    assert names == ["GPT", "Egida qwen3:8b"]
