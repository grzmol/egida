"""Hash-chained JSONL audit (A1, C20) and its verifier (A6 §6)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from control_layer.adapters.audit_fanout import FanoutAuditSink
from control_layer.adapters.audit_jsonl import AuditError, AuditJsonl, line_hash, verify_file
from control_layer.core.audit import AuditEvent
from control_layer.core.models import Action

pytestmark = pytest.mark.anyio


def _event(i: int) -> AuditEvent:
    return AuditEvent(type="decision", ts=float(i), request_id=f"req_{i}", decision=Action.ALLOW)


@pytest.fixture
async def log(tmp_path: Path, anyio_backend: str) -> Path:
    """A valid chain of three events (seq 1..3)."""
    path = tmp_path / "audit.jsonl"
    sink = AuditJsonl(path)
    for i in range(1, 4):
        await sink.emit(_event(i))
    return path


def _lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def _write(path: Path, lines: list[str]) -> None:
    path.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")


def _cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 (fixed argv, no shell)
        [sys.executable, "-m", "control_layer.adapters.audit_jsonl", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_intact_chain_reports_count_last_seq_and_head(log: Path) -> None:
    result = verify_file(log)
    last = json.loads(_lines(log)[-1])
    assert (result.ok, result.events, result.last_seq, result.error) == (True, 3, 3, None)
    assert result.head_hash == last["hash"]


def test_deleted_middle_line_is_seq_error(log: Path) -> None:
    lines = _lines(log)
    _write(log, [lines[0], lines[2]])
    result = verify_file(log)
    assert result.error is not None
    assert (result.error.line, result.error.seq, result.error.kind) == (2, 3, "seq")
    assert (result.ok, result.events, result.last_seq) == (False, 1, 1)


def test_swapped_lines_are_seq_error(log: Path) -> None:
    lines = _lines(log)
    _write(log, [lines[0], lines[2], lines[1]])
    error = verify_file(log).error
    assert error is not None
    assert (error.line, error.kind) == (2, "seq")


def test_rewritten_prev_hash_with_recomputed_hash_is_prev_hash_error(log: Path) -> None:
    lines = _lines(log)
    record = json.loads(lines[1])
    record["prev_hash"] = "f" * 64
    record["hash"] = line_hash(record)
    lines[1] = json.dumps(record)
    _write(log, lines)
    error = verify_file(log).error
    assert error is not None
    assert (error.line, error.seq, error.kind) == (2, 2, "prev_hash")


def test_changed_field_is_hash_error(log: Path) -> None:
    lines = _lines(log)
    head = json.loads(lines[0])["hash"]
    lines[1] = lines[1].replace("req_2", "req_X")
    _write(log, lines)
    result = verify_file(log)
    assert result.error is not None
    assert (result.error.line, result.error.seq, result.error.kind) == (2, 2, "hash")
    assert (result.events, result.last_seq, result.head_hash) == (1, 1, head)


@pytest.mark.parametrize("cut", [1, 40], ids=["missing-newline", "half-written-line"])
def test_truncated_last_line(log: Path, cut: int) -> None:
    log.write_bytes(log.read_bytes()[:-cut])
    error = verify_file(log).error
    assert error is not None
    assert (error.line, error.kind) == (3, "truncated")

    tolerant = verify_file(log, allow_partial_tail=True)
    assert (tolerant.ok, tolerant.events, tolerant.last_seq) == (True, 2, 2)


def test_missing_file_is_io_error(tmp_path: Path) -> None:
    result = verify_file(tmp_path / "missing.jsonl")
    assert result.error is not None
    assert (result.ok, result.error.kind) == (False, "io")


def test_non_object_and_incomplete_records_are_schema_errors(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    for body in (
        "[1, 2]",
        '{"seq": 1, "hash": "x"}',
        '{"schema":"audit.v1","seq":"1","prev_hash":"0","hash":"x"}',
    ):
        _write(path, [body])
        error = verify_file(path).error
        assert error is not None
        assert (error.line, error.kind) == (1, "schema")


def test_new_log_is_empty_and_verifies(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    AuditJsonl(path)
    result = verify_file(path)
    assert (result.ok, result.events, result.last_seq, result.head_hash) == (True, 0, None, None)


async def test_restart_continues_chain(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    await AuditJsonl(path).emit(_event(1))
    await AuditJsonl(path).emit(_event(2))
    result = verify_file(path)
    assert result.ok
    assert result.events == 2


def test_corrupted_last_line_refuses_to_start(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    path.write_text('{"seq": 1, "hash": "x"}\n{broken', encoding="utf-8")
    with pytest.raises(AuditError):
        AuditJsonl(path)


def test_cli_exit_codes(log: Path, tmp_path: Path) -> None:
    head = json.loads(_lines(log)[-1])["hash"][:12]
    ok = _cli("verify", str(log))
    assert (ok.returncode, ok.stdout) == (0, f"OK 3 events, last seq 3, head {head}\n")

    log.write_text(log.read_text(encoding="utf-8").replace("req_2", "req_X"), encoding="utf-8")
    broken = _cli("verify", str(log))
    assert (broken.returncode, broken.stdout) == (1, "BROKEN line 2 (seq 2): hash mismatch\n")

    missing = _cli("verify", str(tmp_path / "missing.jsonl"))
    assert (missing.returncode, missing.stdout) == (2, "")
    assert "missing.jsonl" in missing.stderr

    assert _cli().returncode == 2


class _Failing:
    async def emit(self, event: AuditEvent) -> None:
        raise OSError("disk full")


class _Collecting:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    async def emit(self, event: AuditEvent) -> None:
        self.events.append(event)


async def test_fanout_delivers_to_healthy_sinks_and_reraises() -> None:
    good = _Collecting()
    fanout = FanoutAuditSink([_Failing(), good])
    with pytest.raises(OSError, match="disk full"):
        await fanout.emit(_event(1))
    assert len(good.events) == 1
