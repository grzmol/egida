"""Append-only JSONL audit log with a sha256 hash chain (C20).

Each line: {"seq": n, ...audit.v1 event..., "prev_hash": h(n-1), "hash": line_hash(line)}.
`seq` starts at 1; the first line chains from 64 zeros. Restart continues seq and chain from the
last line. The chain is not anchored: whoever can write the file can recompute it, so the
`head_hash` reported by `verify` is only a partial mitigation when recorded elsewhere.

CLI: python -m control_layer.adapters.audit_jsonl verify <file>
  exit 0 = chain intact, 1 = chain broken (first bad line), 2 = file unreadable.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import anyio

from control_layer.core.audit import AuditEvent
from control_layer.core.errors import AuditError

__all__ = [
    "GENESIS_HASH",
    "AuditError",
    "AuditJsonl",
    "VerifyError",
    "VerifyResult",
    "line_hash",
    "verify_file",
]

GENESIS_HASH = "0" * 64
FIRST_SEQ = 1

VerifyErrorKind = Literal["io", "json", "schema", "seq", "prev_hash", "hash", "truncated"]


def _canonical(record: Mapping[str, object]) -> str:
    return json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def line_hash(record: Mapping[str, object]) -> str:
    """sha256 of the canonical JSON of `record` without its `hash` key.

    The single hash formula: the writer and the verifier both call this.
    """
    body = {k: v for k, v in record.items() if k != "hash"}
    return hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()


class AuditJsonl:
    """AuditSink writing a hash-chained JSONL file. Raw content never reaches this layer."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = asyncio.Lock()
        self._seq = FIRST_SEQ - 1
        self._prev = GENESIS_HASH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=True)  # an empty log verifies OK before the first event
        lines = path.read_text(encoding="utf-8").splitlines()
        # ponytail: reads the whole log once at startup; tail-seek if logs grow past ~100 MB
        if lines:
            try:
                record = json.loads(lines[-1])
                self._seq = int(record["seq"])
                self._prev = str(record["hash"])
            except (ValueError, KeyError, TypeError) as exc:
                raise AuditError(
                    f"{path}: last line is not a valid audit record; refusing to start a new "
                    f"chain on top of it ({exc})"
                ) from exc

    async def emit(self, event: AuditEvent) -> None:
        async with self._lock:
            record: dict[str, Any] = {
                "seq": self._seq + 1,
                **event.to_dict(),
                "prev_hash": self._prev,
            }
            record["hash"] = line_hash(record)
            line = _canonical(record) + "\n"
            try:
                await anyio.to_thread.run_sync(self._append, line)
            except OSError as exc:  # disk full, permissions: the request must not get an answer
                raise AuditError(f"cannot write audit log {self._path}: {exc}") from exc
            self._seq = record["seq"]
            self._prev = record["hash"]

    def _append(self, line: str) -> None:
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(line)
            fh.flush()


# --- verification ---------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class VerifyError:
    line: int  # 1-based; 0 for io errors
    seq: int | None  # seq claimed by the bad line, when it could be read
    kind: VerifyErrorKind
    message: str


@dataclass(frozen=True, slots=True)
class VerifyResult:
    ok: bool
    events: int  # valid lines before the first error
    last_seq: int | None  # of the last valid line
    head_hash: str | None  # hash of the last valid line
    error: VerifyError | None


class _Broken(Exception):
    def __init__(self, seq: int | None, kind: VerifyErrorKind, message: str) -> None:
        super().__init__(message)
        self.seq = seq
        self.kind = kind
        self.message = message


def _check_line(raw: bytes, expected_seq: int, prev: str) -> tuple[int, str]:
    """Validate one complete line; returns (seq, hash) or raises _Broken."""
    try:
        record = json.loads(raw.decode("utf-8"))
    except ValueError as exc:  # also UnicodeDecodeError
        raise _Broken(None, "json", f"invalid JSON: {exc}") from exc
    if not isinstance(record, dict):
        raise _Broken(None, "schema", "line is not a JSON object")
    missing = [k for k in ("schema", "seq", "prev_hash", "hash") if k not in record]
    if missing:
        raise _Broken(None, "schema", f"missing fields: {', '.join(missing)}")
    seq, prev_hash, claimed = record["seq"], record["prev_hash"], record["hash"]
    if type(seq) is not int or not isinstance(prev_hash, str) or not isinstance(claimed, str):
        raise _Broken(None, "schema", "seq must be an integer, prev_hash and hash strings")
    if seq != expected_seq:
        raise _Broken(seq, "seq", f"seq {seq}, expected {expected_seq}")
    if prev_hash != prev:
        raise _Broken(seq, "prev_hash", "prev_hash does not match the previous line")
    if line_hash(record) != claimed:
        raise _Broken(seq, "hash", "hash mismatch")
    return seq, claimed


def verify_file(path: Path, *, allow_partial_tail: bool = False) -> VerifyResult:
    """Recompute the chain and stop at the first broken line.

    A last line without a newline is `truncated`; with `allow_partial_tail` (reading a log the
    sink is appending to right now) it is skipped instead.
    """
    events = 0
    last_seq: int | None = None
    prev = GENESIS_HASH

    def broken(line: int, seq: int | None, kind: VerifyErrorKind, message: str) -> VerifyResult:
        error = VerifyError(line, seq, kind, message)
        head = prev if last_seq is not None else None
        return VerifyResult(False, events, last_seq, head, error)

    try:
        with path.open("rb") as fh:
            for lineno, raw in enumerate(fh, start=1):
                if not raw.endswith(b"\n"):
                    if allow_partial_tail:
                        break
                    return broken(lineno, None, "truncated", "last line has no newline")
                try:
                    last_seq, prev = _check_line(raw, FIRST_SEQ + events, prev)
                except _Broken as exc:
                    return broken(lineno, exc.seq, exc.kind, exc.message)
                events += 1
    except OSError as exc:
        return broken(0, None, "io", f"cannot read {path}: {exc}")
    return VerifyResult(True, events, last_seq, prev if last_seq is not None else None, None)


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m control_layer.adapters.audit_jsonl")
    commands = parser.add_subparsers(dest="command", required=True)
    verify = commands.add_parser("verify", help="verify the hash chain of an audit log")
    verify.add_argument("file", type=Path)
    args = parser.parse_args(argv)

    result = verify_file(args.file)
    error = result.error
    if error is None:
        if result.head_hash is None:
            print("OK 0 events (empty log)")
        else:
            print(
                f"OK {result.events} events, last seq {result.last_seq}, "
                f"head {result.head_hash[:12]}"
            )
        return 0
    if error.kind == "io":
        print(error.message, file=sys.stderr)
        return 2
    where = f"line {error.line}" + (f" (seq {error.seq})" if error.seq is not None else "")
    print(f"BROKEN {where}: {error.message}")
    return 1


if __name__ == "__main__":
    sys.exit(_main())
