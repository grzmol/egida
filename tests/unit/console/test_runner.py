"""Run profile persistence and the proxy process manager."""

from __future__ import annotations

import json
import socket
import sys
import threading
import time
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from egida.app import Settings
from egida.console.runner import (
    Health,
    ProfileError,
    Proxy,
    ProxyError,
    RunProfile,
    load_profile,
    port_in_use,
    save_profile,
)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for(condition: Callable[[], bool], timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return condition()


# ── profile ──────────────────────────────────────────────────────────────


def test_defaults_match_proxy_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "EGIDA_POLICY",
        "EGIDA_AUDIT",
        "EGIDA_GUARD_URL",
        "EGIDA_FEED",
    ):
        monkeypatch.delenv(name, raising=False)
    settings = Settings.from_env()
    profile = RunProfile()
    assert profile.policy == settings.policy_path
    assert profile.audit == settings.audit_path
    assert profile.feed == settings.feed_path
    assert profile.guard_url == settings.guard_url
    assert profile.models_dir == Path("models")
    assert (profile.host, profile.port) == ("127.0.0.1", 8080)


def test_env_keeps_relative_paths_and_command_uses_address() -> None:
    profile = RunProfile(
        host="0.0.0.0",  # noqa: S104 (value under test)
        port=9001,
        policy=Path("config/policy.strict.yaml"),
        audit=Path("/tmp/a.jsonl"),  # noqa: S108 (value under test)
        models_dir=Path("other/models"),
    )
    assert profile.env() == {
        "EGIDA_POLICY": "config/policy.strict.yaml",
        "EGIDA_AUDIT": "/tmp/a.jsonl",  # noqa: S108 (value under test)
        "EGIDA_FEED": "signatures/feed.yaml",
        "EGIDA_GUARD_URL": "http://127.0.0.1:11434",
        "EGIDA_MODELS_DIR": "other/models",
    }
    assert profile.command() == [
        sys.executable,
        "-m",
        "uvicorn",
        "egida.app:create_app",
        "--factory",
        "--host",
        "0.0.0.0",  # noqa: S104 (value under test)
        "--port",
        "9001",
    ]


@pytest.mark.parametrize(
    ("host", "url"),
    [
        ("127.0.0.1", "http://127.0.0.1:8080"),
        ("::1", "http://[::1]:8080"),
        ("localhost", "http://localhost:8080"),
    ],
)
def test_base_url(host: str, url: str) -> None:
    assert RunProfile(host=host).base_url == url


@pytest.mark.parametrize(
    ("host", "loopback"),
    [
        ("127.0.0.1", True),
        ("::1", True),
        ("localhost", True),
        ("0.0.0.0", False),  # noqa: S104 (value under test)
        ("192.168.1.10", False),
        ("example.org", False),
    ],
)
def test_is_loopback(host: str, loopback: bool) -> None:
    assert RunProfile(host=host).is_loopback() is loopback


def test_load_missing_file_gives_defaults(tmp_path: Path) -> None:
    assert load_profile(tmp_path / "egida.yaml") == RunProfile()


@pytest.mark.parametrize(
    "text",
    ["port: [8080\n", "host: 127.0.0.1\ncolour: red\n", "port: 70000\n", "- a\n- b\n"],
    ids=["bad-yaml", "unknown-field", "port-out-of-range", "not-a-mapping"],
)
def test_load_rejects_invalid_files(tmp_path: Path, text: str) -> None:
    path = tmp_path / "egida.yaml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ProfileError):
        load_profile(path)


def test_load_names_the_bad_field(tmp_path: Path) -> None:
    path = tmp_path / "egida.yaml"
    path.write_text("port: 70000\n", encoding="utf-8")
    with pytest.raises(ProfileError, match="port"):
        load_profile(path)


def test_save_new_file_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "egida.yaml"
    profile = RunProfile(host="::1", port=9000, policy=Path("config/policy.lenient.yaml"))
    save_profile(path, profile)
    assert load_profile(path) == profile
    text = path.read_text(encoding="utf-8")
    assert text.startswith("#")
    assert "policy: config/policy.lenient.yaml" in text
    assert sorted(p.name for p in path.parent.iterdir()) == ["egida.yaml"]


def test_save_existing_file_changes_only_the_edited_line(tmp_path: Path) -> None:
    path = tmp_path / "egida.yaml"
    original = (
        "# my settings\n"
        "port: 8080  # demo port\n"
        "\n"
        "# where the policy lives\n"
        "policy: ./config/policy.yaml\n"
        "host: 127.0.0.1\n"
    )
    path.write_text(original, encoding="utf-8")
    save_profile(path, load_profile(path).model_copy(update={"port": 9090}))
    expected = original.replace("port: 8080  # demo port", "port: 9090  # demo port")
    assert path.read_text(encoding="utf-8") == expected
    assert sorted(p.name for p in tmp_path.iterdir()) == ["egida.yaml"]


def test_save_refuses_to_overwrite_unparsable_file(tmp_path: Path) -> None:
    path = tmp_path / "egida.yaml"
    path.write_text("port: [8080\n", encoding="utf-8")
    with pytest.raises(ProfileError):
        save_profile(path, RunProfile())
    assert path.read_text(encoding="utf-8") == "port: [8080\n"


# ── proxy process ────────────────────────────────────────────────────────


@pytest.fixture
def script(monkeypatch: pytest.MonkeyPatch) -> Callable[[str], None]:
    def use(code: str) -> None:
        monkeypatch.setattr(RunProfile, "command", lambda self: [sys.executable, "-c", code])

    return use


@pytest.fixture
def proxy(tmp_path: Path) -> Iterator[Proxy]:
    instance = Proxy(tmp_path / "logs" / "proxy.log")
    yield instance
    instance.stop(timeout=1.0)


def test_start_logs_output_and_stop(proxy: Proxy, script: Callable[[str], None]) -> None:
    script("import sys, time; print('hello from proxy', flush=True); time.sleep(30)")
    profile = RunProfile(port=_free_port())
    proxy.start(profile)
    assert proxy.running
    assert isinstance(proxy.pid, int)
    assert proxy.profile == profile
    assert _wait_for(lambda: "hello from proxy" in proxy.log_tail())
    with pytest.raises(ProxyError):
        proxy.start(profile)
    proxy.stop(timeout=2.0)
    assert not proxy.running
    assert proxy.pid is None
    assert proxy.profile is None
    assert proxy.exit_code is None


def test_stop_kills_a_process_ignoring_sigterm(proxy: Proxy, script: Callable[[str], None]) -> None:
    script(
        "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN);"
        " print('ready', flush=True); time.sleep(30)"
    )
    proxy.start(RunProfile(port=_free_port()))
    assert _wait_for(lambda: "ready" in proxy.log_tail())
    proxy.stop(timeout=0.2)
    assert not proxy.running


def test_exit_on_its_own_records_exit_code(proxy: Proxy, script: Callable[[str], None]) -> None:
    script("import sys; print('bye'); sys.exit(3)")
    proxy.start(RunProfile(port=_free_port()))
    assert _wait_for(lambda: not proxy.running)
    assert proxy.exit_code == 3
    assert proxy.pid is None
    assert "bye" in proxy.log_tail()


def test_restart_appends_to_the_log(proxy: Proxy, script: Callable[[str], None]) -> None:
    script("import time; print('run', flush=True); time.sleep(30)")
    profile = RunProfile(port=_free_port())
    proxy.start(profile)
    first = proxy.pid
    assert _wait_for(lambda: "run" in proxy.log_tail())
    proxy.restart(profile)
    assert proxy.running
    assert proxy.pid != first
    assert _wait_for(lambda: proxy.log_tail().count("run") == 2)


def test_log_tail_returns_last_lines_of_large_log(tmp_path: Path) -> None:
    path = tmp_path / "proxy.log"
    path.write_text("".join(f"line {i}\n" for i in range(20000)), encoding="utf-8")
    proxy = Proxy(path)
    assert proxy.log_tail(3) == ["line 19997", "line 19998", "line 19999"]
    assert proxy.log_tail(0) == []
    assert Proxy(tmp_path / "missing.log").log_tail() == []


def test_port_in_use_and_start_refuses(proxy: Proxy, script: Callable[[str], None]) -> None:
    script("import time; time.sleep(30)")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = int(listener.getsockname()[1])
        assert port_in_use("127.0.0.1", port)
        with pytest.raises(ProxyError, match=str(port)):
            proxy.start(RunProfile(port=port))
        assert not proxy.running
    assert not port_in_use("127.0.0.1", port)


def test_port_in_use_ipv6() -> None:
    if not socket.has_ipv6:
        pytest.skip("no IPv6")
    with socket.socket(socket.AF_INET6) as listener:
        try:
            listener.bind(("::1", 0))
        except OSError:
            pytest.skip("no IPv6 loopback")
        listener.listen()
        port = int(listener.getsockname()[1])
        assert port_in_use("::1", port)


# ── health ───────────────────────────────────────────────────────────────


def _serve(responses: dict[str, tuple[int, bytes]]) -> tuple[ThreadingHTTPServer, threading.Thread]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 (http.server API)
            status, body = responses.get(self.path, (404, b"{}"))
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002 (base signature)
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


@pytest.fixture
def http_server() -> Iterator[Callable[[dict[str, tuple[int, bytes]]], int]]:
    started: list[tuple[ThreadingHTTPServer, threading.Thread]] = []

    def start(responses: dict[str, tuple[int, bytes]]) -> int:
        server, thread = _serve(responses)
        started.append((server, thread))
        return int(server.server_address[1])

    yield start
    for server, thread in started:
        server.shutdown()
        server.server_close()
        thread.join()


HEALTHZ = json.dumps({"status": "ok", "policy_version": 4, "policy_sha256": "ab12"}).encode()
API_POLICY = json.dumps(
    {
        "version": 4,
        "sha256": "ab12",
        "loaded_at": "x",
        "source": "config/policy.yaml",
        "last_error": None,
    }
).encode()
ServerFactory = Callable[[dict[str, tuple[int, bytes]]], int]


def test_health_reads_policy_state(http_server: ServerFactory) -> None:
    port = http_server({"/healthz": (200, HEALTHZ), "/api/policy": (200, API_POLICY)})
    health = Proxy().health(RunProfile(port=port), timeout=2.0)
    assert health == Health(4, "ab12", "config/policy.yaml", None)


@pytest.mark.parametrize(
    "responses",
    [
        {"/healthz": (200, b"not json"), "/api/policy": (200, API_POLICY)},
        {"/healthz": (200, HEALTHZ), "/api/policy": (200, b'{"version": 4}')},
        {"/healthz": (503, HEALTHZ), "/api/policy": (200, API_POLICY)},
    ],
    ids=["bad-json", "missing-keys", "not-200"],
)
def test_health_none_for_unexpected_answers(
    http_server: Callable[[dict[str, tuple[int, bytes]]], int],
    responses: dict[str, tuple[int, bytes]],
) -> None:
    port = http_server(responses)
    assert Proxy().health(RunProfile(port=port), timeout=2.0) is None


def test_health_none_for_closed_port() -> None:
    assert Proxy().health(RunProfile(port=_free_port())) is None
