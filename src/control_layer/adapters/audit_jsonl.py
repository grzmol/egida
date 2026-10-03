"""Append-only JSONL audit log with a sha256 hash chain (C20).

Each line: {"seq": n, ...audit.v1 event..., "prev_hash": h(n-1), "hash": sha256(line without hash)}.
The first line chains from 64 zeros. Restart continues seq and chain from the last line.

CLI: python -m control_layer.adapters.audit_jsonl verify <file>
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import anyio

from control_layer.core.audit import AuditEvent
from control_layer.core.errors import ControlLayerError

__all__ = ["GENESIS_HASH", "AuditError", "AuditJsonl", "VerifyResult", "verify_file"]

GENESIS_HASH = "0" * 64


class AuditError(ControlLayerError):
    """The audit log cannot be continued safely (e.g. corrupted last line)."""


def _canonical(record: dict[str, Any]) -> str:
    return json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _hash(record_without_hash: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(record_without_hash).encode("utf-8")).hexdigest()


def _last_line(path: Path) -> str | None:
    with path.open("rb") as fh:
        fh.seek(0, 2)
        end = fh.tell()
        chunk = 4096
        pos = end
        buf = b""
        while pos > 0:
            step = min(chunk, pos)
            pos -= step
            fh.seek(pos)
            buf = fh.read(step) + buf
            stripped = buf.rstrip(b"\n")
            if b"\n" in stripped:
                return stripped.rsplit(b"\n", 1)[1].decode("utf-8")
        stripped = buf.rstrip(b"\n")
        return stripped.decode("utf-8") if stripped else None


class AuditJsonl:
    """AuditSink writing a hash-chained JSONL file. Raw content never reaches this layer."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = asyncio.Lock()
        self._seq = 0
        self._prev = GENESIS_HASH
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            last = _last_line(path)
            if last is not None:
                try:
                    record = json.loads(last)
                    self._seq = int(record["seq"])
                    self._prev = str(record["hash"])
                except (ValueError, KeyError, TypeError) as exc:
                    raise AuditError(
                        f"{path}: last line is not a valid audit record; refusing to start a new "
                        f"chain on top of it ({exc})"
                    ) from exc

    @property
    def path(self) -> Path:
        return self._path

    async def emit(self, event: AuditEvent) -> None:
        async with self._lock:
            record: dict[str, Any] = {
                "seq": self._seq + 1,
                **event.to_dict(),
                "prev_hash": self._prev,
            }
            record["hash"] = _hash(record)
            line = _canonical(record) + "\n"
            await anyio.to_thread.run_sync(self._append, line)
            self._seq = record["seq"]
            self._prev = record["hash"]

    def _append(self, line: str) -> None:
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(line)
            fh.flush()


@dataclass(frozen=True, slots=True)
class VerifyResult:
    ok: bool
    events: int
    bad_line: int | None = None
    reason: str | None = None


def verify_file(path: Path) -> VerifyResult:
    """Recompute the chain. Returns the first broken line (1-based) and why."""
    prev = GENESIS_HASH
    count = 0
    with path.open(encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, start=1):
            if not raw.strip():
                continue
            try:
                record = json.loads(raw)
            except ValueError as exc:
                return VerifyResult(False, count, lineno, f"invalid JSON: {exc}")
            if not isinstance(record, dict) or "hash" not in record:
                return VerifyResult(False, count, lineno, "missing hash")
            claimed = record.pop("hash")
            if record.get("seq") != count + 1:
                return VerifyResult(False, count, lineno, f"seq {record.get('seq')} != {count + 1}")
            if record.get("prev_hash") != prev:
                return VerifyResult(False, count, lineno, "prev_hash does not match previous line")
            if _hash(record) != claimed:
                return VerifyResult(False, count, lineno, "hash mismatch (line was modified)")
            prev = claimed
            count += 1
    return VerifyResult(True, count)


def _main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[0] != "verify":
        print("usage: python -m control_layer.adapters.audit_jsonl verify <file>", file=sys.stderr)
        return 2
    path = Path(argv[1])
    try:
        result = verify_file(path)
    except OSError as exc:
        print(f"cannot read {path}: {exc}", file=sys.stderr)
        return 2
    if result.ok:
        print(f"OK {result.events} events")
        return 0
    print(f"BROKEN at line {result.bad_line}: {result.reason}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
