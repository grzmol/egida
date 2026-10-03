from __future__ import annotations

import json
from pathlib import Path

import pytest

from egida.console.harnesses.base import Endpoint, HarnessEnv, HarnessError
from egida.console.harnesses.files import Ledger
from egida.console.harnesses.pi import Pi

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
    harness = Pi()
    planned = harness.plan(env, ENDPOINT)
    assert not harness.enabled(env)
    changes = harness.apply(env, ENDPOINT)
    assert planned == changes
    assert [c.action for c in changes] == ["create"] * len(changes)
    assert harness.enabled(env)
    assert harness.plan(env, ENDPOINT) == []


def test_remove_deletes_files_egida_created(env: HarnessEnv) -> None:
    harness = Pi()
    harness.apply(env, ENDPOINT)
    harness.remove(env)
    for path in harness.config_paths(env):
        assert not path.exists()
    assert not harness.enabled(env)
    assert Ledger(env).get(harness.id) is None


def test_invalid_file_is_refused_and_untouched(env: HarnessEnv) -> None:
    harness = Pi()
    path = harness.config_paths(env)[0]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{bad}", encoding="utf-8")
    with pytest.raises(HarnessError):
        harness.apply(env, ENDPOINT)
    assert path.read_text(encoding="utf-8") == "{bad}"
    assert Ledger(env).get(harness.id) is None


def test_apply_over_user_file_backs_up_and_remove_restores_exactly(env: HarnessEnv) -> None:
    harness = Pi()
    originals = write_user_files(env)
    harness.apply(env, ENDPOINT)
    assert backups(env, harness.id)
    check_user_keys_kept(env)
    harness.remove(env)
    for path, text in originals.items():
        assert path.read_text(encoding="utf-8") == text
    assert not harness.enabled(env)


def test_reapply_replaces_key_in_place(env: HarnessEnv) -> None:
    harness = Pi()
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
    harness = Pi()
    harness.apply(env, ENDPOINT)
    for path in harness.config_paths(env):
        path.write_text(
            path.read_text(encoding="utf-8").replace("127.0.0.1:8080", "example.test"),
            encoding="utf-8",
        )
    assert not harness.enabled(env)


def write_user_files(env: HarnessEnv) -> dict[Path, str]:
    models, settings = Pi().config_paths(env)
    models.parent.mkdir(parents=True)
    texts = {
        models: json.dumps(
            {"providers": {"local": {"baseUrl": "http://x.test/v1", "models": [{"id": "m"}]}}},
            indent=2,
        )
        + "\n",
        settings: json.dumps({"defaultProvider": "anthropic", "theme": "dark"}, indent=2) + "\n",
    }
    for path, text in texts.items():
        path.write_text(text, encoding="utf-8")
    return texts


def check_user_keys_kept(env: HarnessEnv) -> None:
    models, settings = Pi().config_paths(env)
    assert "local" in json.loads(models.read_text(encoding="utf-8"))["providers"]
    assert json.loads(settings.read_text(encoding="utf-8"))["theme"] == "dark"


def test_provider_and_defaults(env: HarnessEnv) -> None:
    Pi().apply(env, ENDPOINT)
    agent = env.home / ".pi" / "agent"
    models = json.loads((agent / "models.json").read_text(encoding="utf-8"))
    assert models["providers"]["egida"] == {
        "baseUrl": "http://127.0.0.1:8080/v1",
        "api": "openai-completions",
        "apiKey": "sk-egida-one",
        "models": [{"id": "llama3.2:3b"}],
    }
    settings = json.loads((agent / "settings.json").read_text(encoding="utf-8"))
    assert settings == {"defaultProvider": "egida", "defaultModel": "llama3.2:3b"}


def test_restores_absent_default_model_key(env: HarnessEnv) -> None:
    write_user_files(env)
    Pi().apply(env, ENDPOINT)
    Pi().remove(env)
    settings = json.loads(Pi().config_paths(env)[1].read_text(encoding="utf-8"))
    assert settings == {"defaultProvider": "anthropic", "theme": "dark"}


def test_agent_dir_from_environment(tmp_path: Path) -> None:
    env = HarnessEnv(
        home=tmp_path,
        config_dir=tmp_path / "egida",
        environ={"PI_CODING_AGENT_DIR": "~/pi"},
        which=lambda _n: None,
    )
    assert Pi().config_paths(env)[0] == tmp_path / "pi" / "models.json"
