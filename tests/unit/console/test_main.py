"""`egd launch <id>`: argument errors, an unreachable proxy, and the exec of a launch harness."""

from __future__ import annotations

from pathlib import Path

import pytest

from egida.console import __main__ as egd
from egida.console.harnesses import by_id
from egida.console.harnesses.base import Endpoint, HarnessEnv
from egida.console.runner import Health


@pytest.fixture
def profile(tmp_path: Path) -> Path:
    path = tmp_path / "egida.yaml"
    path.write_text("port: 1\n")
    return path


def test_unknown_harness_lists_launch_ids(
    profile: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert egd.main(["--profile", str(profile), "launch", "vim"]) == 2
    err = capsys.readouterr().err
    assert "unknown harness 'vim'" in err
    assert "antigravity-cli" in err and "copilot-cli" in err


def test_config_harness_says_how_it_starts(
    profile: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert egd.main(["--profile", str(profile), "launch", "claude-code"]) == 2
    assert "run `claude`" in capsys.readouterr().err


def test_unavailable_harness_gives_its_reason(
    profile: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert egd.main(["--profile", str(profile), "launch", "cursor"]) == 2
    assert "Cursor's servers" in capsys.readouterr().err


def test_unreachable_proxy_exits_2(
    profile: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr("shutil.which", lambda name: f"/bin/{name}")
    endpoint = Endpoint("http://127.0.0.1:1", "sk-egida-x", "m")
    by_id("copilot-cli").apply(HarnessEnv.current(), endpoint)
    assert egd.main(["--profile", str(profile), "launch", "copilot-cli"]) == 2
    assert "proxy not reachable at http://127.0.0.1:1" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("harness_id", "key_var"),
    [("copilot-cli", "COPILOT_PROVIDER_API_KEY"), ("gemini-cli", "GEMINI_API_KEY")],
)
def test_launch_execs_the_harness_with_its_env(
    harness_id: str,
    key_var: str,
    profile: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    health = Health(policy_version=1, policy_sha256="0" * 64, policy_source="p", policy_error=None)
    monkeypatch.setattr(
        "egida.console.runner.Proxy.health", lambda self, profile, timeout=0.3: health
    )
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr("shutil.which", lambda name: f"/bin/{name}")
    calls: list[tuple[str, list[str], dict[str, str]]] = []

    def fake_exec(file: str, argv: list[str], env: dict[str, str]) -> None:
        calls.append((file, argv, env))
        raise SystemExit(0)

    monkeypatch.setattr("os.execvpe", fake_exec)
    args = ["--profile", str(profile), "launch", harness_id, "--help"]
    assert egd.main(args) == 2  # not set up yet: no exec
    assert "not set up for Egida" in capsys.readouterr().err
    env = HarnessEnv.current()
    by_id(harness_id).apply(env, Endpoint("http://127.0.0.1:1", "sk-egida-x", "m"))
    with pytest.raises(SystemExit):
        egd.main(args)

    [(file, argv, environ)] = calls
    assert argv[-1] == "--help" and file == argv[0]
    assert environ["HOME"] == str(tmp_path)
    assert environ[key_var] == "sk-egida-x"
