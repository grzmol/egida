"""Launch-mode harnesses: `egd launch <id>` gets argv and env from the launch env file."""

from __future__ import annotations

import stat
from pathlib import Path

import pytest

from egida.console.harnesses import by_id
from egida.console.harnesses.base import Endpoint, Harness, HarnessEnv, HarnessError
from egida.console.harnesses.copilot import CopilotCli
from egida.console.harnesses.gemini import AntigravityCli

ENDPOINT = Endpoint("http://127.0.0.1:8080", "sk-egida-first", "llama3.2:3b")


def make_env(tmp_path: Path, binaries: dict[str, str]) -> HarnessEnv:
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    return HarnessEnv(home=home, config_dir=tmp_path / "egida", environ={}, which=binaries.get)


def test_copilot_launch_uses_binary_on_path_and_env_file(tmp_path: Path) -> None:
    env = make_env(tmp_path, {"copilot": "/opt/bin/copilot"})
    harness = CopilotCli()
    changes = harness.apply(env, ENDPOINT)
    path = env.config_dir / "launch" / "copilot-cli.env"
    assert [(c.path, c.action) for c in changes] == [(path, "create")]
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    argv, extra = harness.launch(env, ["--resume", "x y"])
    assert argv == ["/opt/bin/copilot", "--resume", "x y"]
    assert extra == {
        "COPILOT_PROVIDER_BASE_URL": "http://127.0.0.1:8080/v1",
        "COPILOT_PROVIDER_API_KEY": "sk-egida-first",
        "COPILOT_MODEL": "llama3.2:3b",
    }
    assert harness.state(env).enabled
    assert list(env.home.iterdir()) == []


def test_copilot_reapply_and_remove(tmp_path: Path) -> None:
    env = make_env(tmp_path, {"copilot": "/opt/bin/copilot"})
    harness = CopilotCli()
    harness.apply(env, ENDPOINT)
    assert harness.plan(env, ENDPOINT) == []
    harness.apply(env, Endpoint("http://127.0.0.1:9090", "sk-egida-second", "qwen3:8b"))
    assert harness.launch(env, [])[1]["COPILOT_PROVIDER_API_KEY"] == "sk-egida-second"
    assert harness.enabled(env)
    assert [c.action for c in harness.plan_remove(env)] == ["delete"]
    harness.remove(env)
    assert not (env.config_dir / "launch" / "copilot-cli.env").exists()
    assert not harness.enabled(env)
    with pytest.raises(HarnessError, match="not set up for Egida"):
        harness.launch(env, [])


def test_agy_launch_falls_back_to_local_bin(tmp_path: Path) -> None:
    env = make_env(tmp_path, {})
    harness = AntigravityCli()
    harness.apply(env, ENDPOINT)
    with pytest.raises(HarnessError, match="agy not found"):
        harness.launch(env, [])
    local = env.home / ".local" / "bin" / "agy"
    local.parent.mkdir(parents=True)
    local.write_text("#!/bin/sh\n")
    argv, extra = harness.launch(env, ["-p", "hi"])
    assert argv == [str(local), "-p", "hi"]
    assert extra["GOOGLE_GEMINI_BASE_URL"] == "http://127.0.0.1:8080"
    assert extra["GEMINI_API_KEY"] == "sk-egida-first"
    assert extra["GEMINI_MODEL"] == "llama3.2:3b"
    assert harness.installed(env)


@pytest.mark.parametrize(
    "harness_id", ["claude-code", "codex", "gemini-cli", "cursor", "antigravity"]
)
def test_launch_refused_outside_launch_mode(tmp_path: Path, harness_id: str) -> None:
    harness: Harness = by_id(harness_id)
    with pytest.raises(HarnessError):
        harness.launch(make_env(tmp_path, {}), [])
