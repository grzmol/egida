from __future__ import annotations

from pathlib import Path

import pytest

from egida.console.harnesses.aider import Aider
from egida.console.harnesses.base import Endpoint, HarnessEnv, HarnessError
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
    harness = Aider()
    planned = harness.plan(env, ENDPOINT)
    assert not harness.enabled(env)
    changes = harness.apply(env, ENDPOINT)
    assert planned == changes
    assert [c.action for c in changes] == ["create"] * len(changes)
    assert harness.enabled(env)
    assert harness.plan(env, ENDPOINT) == []


def test_remove_deletes_files_egida_created(env: HarnessEnv) -> None:
    harness = Aider()
    harness.apply(env, ENDPOINT)
    harness.remove(env)
    for path in harness.config_paths(env):
        assert not path.exists()
    assert not harness.enabled(env)
    assert Ledger(env).get(harness.id) is None


def test_invalid_file_is_refused_and_untouched(env: HarnessEnv) -> None:
    harness = Aider()
    path = harness.config_paths(env)[0]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("a: [unclosed\n", encoding="utf-8")
    with pytest.raises(HarnessError):
        harness.apply(env, ENDPOINT)
    assert path.read_text(encoding="utf-8") == "a: [unclosed\n"
    assert Ledger(env).get(harness.id) is None


def test_apply_over_user_file_backs_up_and_remove_restores_exactly(env: HarnessEnv) -> None:
    harness = Aider()
    originals = write_user_files(env)
    harness.apply(env, ENDPOINT)
    assert backups(env, harness.id)
    check_user_keys_kept(env)
    harness.remove(env)
    for path, text in originals.items():
        assert path.read_text(encoding="utf-8") == text
    assert not harness.enabled(env)


def test_reapply_replaces_key_in_place(env: HarnessEnv) -> None:
    harness = Aider()
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
    harness = Aider()
    harness.apply(env, ENDPOINT)
    for path in harness.config_paths(env):
        path.write_text(
            path.read_text(encoding="utf-8").replace("127.0.0.1:8080", "example.test"),
            encoding="utf-8",
        )
    assert not harness.enabled(env)


USER_TEXT = """# my aider settings
model: gpt-4o
dark-mode: true  # easier on the eyes
"""


def write_user_files(env: HarnessEnv) -> dict[Path, str]:
    path = Aider().config_paths(env)[0]
    path.write_text(USER_TEXT, encoding="utf-8")
    return {path: USER_TEXT}


def check_user_keys_kept(env: HarnessEnv) -> None:
    text = Aider().config_paths(env)[0].read_text(encoding="utf-8")
    assert "# my aider settings" in text
    assert "dark-mode: true  # easier on the eyes" in text


def test_values(env: HarnessEnv) -> None:
    Aider().apply(env, ENDPOINT)
    text = (env.home / ".aider.conf.yml").read_text(encoding="utf-8")
    assert "model: openai/llama3.2:3b" in text
    assert "openai-api-base: http://127.0.0.1:8080/v1" in text
    assert "openai-api-key: sk-egida-one" in text


def test_installed_by_binary_or_config_file(env: HarnessEnv) -> None:
    assert not Aider().installed(env)
    write_user_files(env)
    assert Aider().installed(env)
    which_env = HarnessEnv(
        env.home, env.config_dir, {}, lambda name: "/bin/aider" if name == "aider" else None
    )
    assert Aider().state(which_env).detail.startswith("found aider on PATH")
