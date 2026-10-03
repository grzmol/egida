"""Egida's run side: the run profile (`config/egida.yaml`) and the proxy process it starts.

The profile mirrors the proxy's own settings (`app.Settings.from_env()`, the prompt-guard model
directory and `make run`'s address), so a default profile runs the proxy exactly like `make run`.
Paths are stored as written; relative paths are resolved by the proxy against its working
directory (the repo root).
"""

from __future__ import annotations

import io
import ipaddress
import json
import os
import shlex
import socket
import subprocess
import sys
import tempfile
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from http.client import HTTPException
from pathlib import Path
from typing import Any, Final, NoReturn

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap
from ruamel.yaml.error import YAMLError

__all__ = [
    "PROFILE_PATH",
    "Health",
    "ProfileError",
    "Proxy",
    "ProxyError",
    "RunProfile",
    "exec_foreground",
    "load_profile",
    "port_in_use",
    "save_profile",
]

PROFILE_PATH: Final = Path("config/egida.yaml")

_HEADER: Final = (
    "Egida run settings: how `egida` starts the AI Control Layer proxy\n"
    "(address, policy, audit log, signature feed, guard URL, model directory).\n"
    "Written by Egida; edit it here or in Egida. Relative paths start at the repo root."
)
_PORT_PROBE_TIMEOUT_S: Final = 0.3
_HEALTH_MAX_BYTES: Final = 1 << 20
_TAIL_BLOCK: Final = 8192


class ProfileError(ValueError):
    """The run profile cannot be read, parsed, validated or written; str() is a user sentence."""


class ProxyError(Exception):
    """The proxy process cannot be started or its log read; str() is a user sentence."""


class RunProfile(BaseModel):
    """How Egida runs the proxy. Defaults equal the proxy's own defaults."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    host: str = Field(default="127.0.0.1", min_length=1)
    port: int = Field(default=8080, ge=1, le=65535)
    policy: Path = Path("config/policy.yaml")
    audit: Path = Path("var/audit.jsonl")
    feed: Path = Path("signatures/feed.yaml")
    guard_url: str = "http://127.0.0.1:11434"
    models_dir: Path = Path("models")

    def env(self) -> dict[str, str]:
        """Environment variables the proxy reads its settings from."""
        return {
            "CONTROL_LAYER_POLICY": str(self.policy),
            "CONTROL_LAYER_AUDIT": str(self.audit),
            "CONTROL_LAYER_FEED": str(self.feed),
            "CONTROL_LAYER_GUARD_URL": self.guard_url,
            "CONTROL_LAYER_MODELS_DIR": str(self.models_dir),
        }

    def command(self) -> list[str]:
        """argv of the proxy (what `make run` starts, with this profile's address)."""
        return [
            sys.executable,
            "-m",
            "uvicorn",
            "control_layer.app:create_app",
            "--factory",
            "--host",
            self.host,
            "--port",
            str(self.port),
        ]

    @property
    def base_url(self) -> str:
        host = f"[{self.host}]" if ":" in self.host else self.host
        return f"http://{host}:{self.port}"

    def is_loopback(self) -> bool:
        """True when only this machine can reach the proxy."""
        if self.host.lower() == "localhost":
            return True
        try:
            return ipaddress.ip_address(self.host).is_loopback
        except ValueError:
            return False


def _yaml() -> YAML:
    yaml = YAML(typ="rt")
    yaml.width = 4096
    return yaml


def _read_mapping(path: Path) -> CommentedMap | None:
    """The YAML mapping in `path`; None when the file is missing or empty."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except UnicodeDecodeError as exc:
        raise ProfileError(f"{path} is not UTF-8 text; fix or delete the file.") from exc
    except OSError as exc:
        raise ProfileError(f"Cannot read {path}: {exc.strerror or exc}.") from exc
    try:
        data = _yaml().load(text)
    except YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = f" at line {mark.line + 1}, column {mark.column + 1}" if mark is not None else ""
        raise ProfileError(f"{path} is not valid YAML{where}; fix or delete the file.") from exc
    if data is None:
        return None
    if not isinstance(data, CommentedMap):
        raise ProfileError(f"{path} must be a mapping of run settings (key: value).")
    return data


def _validate(path: Path, data: Mapping[str, Any]) -> RunProfile:
    try:
        return RunProfile.model_validate(dict(data))
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in err['loc']) or 'profile'}: {err['msg']}"
            for err in exc.errors()
        )
        raise ProfileError(f"Invalid run settings in {path}: {problems}.") from exc


def load_profile(path: Path) -> RunProfile:
    """Run profile from `path`; defaults when the file is missing or empty."""
    data = _read_mapping(path)
    return RunProfile() if data is None else _validate(path, data)


def _plain(value: Any) -> str | int:
    return str(value) if isinstance(value, Path) else value


def save_profile(path: Path, profile: RunProfile) -> None:
    """Write `profile` to `path` atomically. An existing file keeps its comments, key order and
    untouched lines; a new file gets a header comment and every setting."""
    data = _read_mapping(path)
    if data is None:
        data = CommentedMap()
        data.yaml_set_start_comment(_HEADER)
        for name in RunProfile.model_fields:
            data[name] = _plain(getattr(profile, name))
    else:
        try:
            current = RunProfile.model_validate(dict(data))
        except ValidationError:
            current = None
        defaults = RunProfile()
        for key in [key for key in data if key not in RunProfile.model_fields]:
            del data[key]
        for name in RunProfile.model_fields:
            value = getattr(profile, name)
            if name in data:
                if current is None or getattr(current, name) != value:
                    data[name] = _plain(value)
            elif value != getattr(defaults, name):
                data[name] = _plain(value)
    buffer = io.StringIO()
    try:
        _yaml().dump(data, buffer)
    except YAMLError as exc:
        raise ProfileError(f"Cannot serialize run settings: {exc}.") from exc
    _write_atomic(path, buffer.getvalue())


def _write_atomic(path: Path, text: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        mode = path.stat().st_mode & 0o7777 if path.exists() else 0o644
        fd, temp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    except OSError as exc:
        raise ProfileError(f"Cannot write {path}: {exc.strerror or exc}.") from exc
    temp = Path(temp_name)
    done = False
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp, mode)
        os.replace(temp, path)
        done = True
    except OSError as exc:
        raise ProfileError(f"Cannot write {path}: {exc.strerror or exc}.") from exc
    finally:
        if not done:
            temp.unlink(missing_ok=True)


@dataclass(frozen=True, slots=True)
class Health:
    """What a running proxy reports about its policy."""

    policy_version: int
    policy_sha256: str
    policy_source: str
    policy_error: str | None


def port_in_use(host: str, port: int) -> bool:
    """True when something accepts TCP connections on host:port (IPv4 or IPv6)."""
    try:
        with socket.create_connection((host, port), timeout=_PORT_PROBE_TIMEOUT_S):
            return True
    except OSError:  # refused, unreachable, timeout, unresolvable host: nothing listens there
        return False


def _get_json(url: str, timeout: float) -> dict[str, Any] | None:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url, timeout=timeout) as response:
            if response.status != 200:
                return None
            data = json.loads(response.read(_HEALTH_MAX_BYTES))
    except (OSError, HTTPException, ValueError):  # URLError/HTTPError/timeouts are OSError
        return None
    return data if isinstance(data, dict) else None


class Proxy:
    """The proxy process Egida started (at most one), with its output appended to a log file."""

    def __init__(self, log_path: Path = Path("var/egida-proxy.log")) -> None:
        self.log_path = log_path
        self._process: subprocess.Popen[bytes] | None = None
        self._log: io.BufferedWriter | None = None
        self._profile: RunProfile | None = None
        self._exit_code: int | None = None

    @property
    def running(self) -> bool:
        return self._poll()

    def _poll(self) -> bool:
        """True while the process lives; records the exit code once it ended on its own."""
        if self._process is None:
            return False
        code = self._process.poll()
        if code is None:
            return True
        self._exit_code = code
        self._release()
        return False

    @property
    def pid(self) -> int | None:
        return self._process.pid if self.running and self._process is not None else None

    @property
    def profile(self) -> RunProfile | None:
        return self._profile if self.running else None

    @property
    def exit_code(self) -> int | None:
        self._poll()
        return self._exit_code

    def start(self, profile: RunProfile) -> None:
        if self.running and self._process is not None:
            pid = self._process.pid
            raise ProxyError(f"The proxy is already running (pid {pid}); stop it first.")
        if port_in_use(profile.host, profile.port):
            raise ProxyError(
                f"Port {profile.port} on {profile.host} is already in use; "
                "stop the other process or choose another port."
            )
        command = profile.command()
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            log = open(self.log_path, "ab")  # noqa: SIM115 (closed in _release or on spawn failure)
        except OSError as exc:
            reason = exc.strerror or exc
            raise ProxyError(f"Cannot open the log {self.log_path}: {reason}.") from exc
        try:
            stamp = datetime.now().astimezone().isoformat(timespec="seconds")
            log.write(f"\n── {stamp} egida start: {shlex.join(command)}\n".encode())
            log.flush()
            process = subprocess.Popen(  # noqa: S603 (argv from a validated profile, no shell)
                command,
                env=os.environ | profile.env(),
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                close_fds=True,
            )
        except OSError as exc:
            log.close()
            raise ProxyError(f"Cannot start the proxy: {exc.strerror or exc}.") from exc
        self._process = process
        self._log = log
        self._profile = profile
        self._exit_code = None

    def stop(self, timeout: float = 5.0) -> None:
        if not self.running or self._process is None:
            return
        process = self._process
        try:
            process.terminate()
            try:
                process.wait(timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        finally:
            self._exit_code = None
            self._release()

    def restart(self, profile: RunProfile) -> None:
        self.stop()
        self.start(profile)

    def _release(self) -> None:
        if self._log is not None:
            self._log.close()
        self._log = None
        self._process = None
        self._profile = None

    def health(self, profile: RunProfile, timeout: float = 0.3) -> Health | None:
        """Policy state of whatever proxy listens on the profile's address; None if unreachable
        or the answer is not the proxy's."""
        status = _get_json(f"{profile.base_url}/healthz", timeout)
        if status is None:
            return None
        policy = _get_json(f"{profile.base_url}/api/policy", timeout)
        if policy is None:
            return None
        version = status.get("policy_version")
        sha256 = status.get("policy_sha256")
        source = policy.get("source")
        error = policy.get("last_error")
        if (
            not isinstance(version, int)
            or isinstance(version, bool)
            or not isinstance(sha256, str)
            or not isinstance(source, str)
            or not (error is None or isinstance(error, str))
        ):
            return None
        return Health(version, sha256, source, error)

    def log_tail(self, lines: int = 200) -> list[str]:
        """Last `lines` lines of the log, read from the end; [] when there is no log yet."""
        if lines <= 0:
            return []
        try:
            with open(self.log_path, "rb") as handle:
                end = handle.seek(0, os.SEEK_END)
                data = b""
                position = end
                while position > 0 and data.count(b"\n") <= lines:
                    step = min(_TAIL_BLOCK, position)
                    position -= step
                    handle.seek(position)
                    data = handle.read(step) + data
        except FileNotFoundError:
            return []
        except OSError as exc:
            reason = exc.strerror or exc
            raise ProxyError(f"Cannot read the log {self.log_path}: {reason}.") from exc
        return data.decode("utf-8", errors="replace").splitlines()[-lines:]


def exec_foreground(profile: RunProfile) -> NoReturn:
    """Replace this process with the proxy (`egida run`), using the profile's environment."""
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        os.execve(sys.executable, profile.command(), os.environ | profile.env())  # noqa: S606
    except OSError as exc:
        raise ProxyError(f"Cannot start the proxy: {exc.strerror or exc}.") from exc
