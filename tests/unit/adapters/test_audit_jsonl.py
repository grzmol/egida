"""Hash-chained JSONL audit (A1, C20)."""

from __future__ import annotations

from pathlib import Path

import pytest

from control_layer.adapters.audit_fanout import FanoutAuditSink
from control_layer.adapters.audit_jsonl import AuditError, AuditJsonl, _main, verify_file
from control_layer.core.audit import AuditEvent
from control_layer.core.models import Action

pytestmark = pytest.mark.anyio


def _event(i: int) -> AuditEvent:
    return AuditEvent(type="decision", ts=float(i), request_id=f"req_{i}", decision=Action.ALLOW)


async def test_chain_verifies_and_detects_tampering(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    sink = AuditJsonl(path)
    for i in range(3):
        await sink.emit(_event(i))
    assert verify_file(path).ok
    assert verify_file(path).events == 3

    lines = path.read_text(encoding="utf-8").splitlines()
    lines[1] = lines[1].replace("req_1", "req_X")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = verify_file(path)
    assert not result.ok
    assert result.bad_line == 2


async def test_deleted_line_breaks_chain(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    sink = AuditJsonl(path)
    for i in range(3):
        await sink.emit(_event(i))
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text(lines[0] + "\n" + lines[2] + "\n", encoding="utf-8")
    assert verify_file(path).bad_line == 2


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


async def test_cli_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "audit.jsonl"
    await AuditJsonl(path).emit(_event(1))
    assert _main(["verify", str(path)]) == 0
    path.write_text(path.read_text(encoding="utf-8").replace("req_1", "req_2"), encoding="utf-8")
    assert _main(["verify", str(path)]) == 1
    assert _main(["verify", str(tmp_path / "missing.jsonl")]) == 2
    assert _main([]) == 2


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
