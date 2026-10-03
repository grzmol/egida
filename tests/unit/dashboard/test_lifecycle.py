"""B9 audit D9/D10: dashboard resources on aborted downloads, damaged audit files, sparse events."""

import contextlib
import csv
import dataclasses
import gc
import io
import json
import os
from pathlib import Path
from typing import get_args

import anyio
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from control_layer.adapters.metrics_memory import MetricsMemory
from control_layer.core.audit import AuditEvent, AuditEventType
from control_layer.core.models import Action
from control_layer.dashboard import build_router

FD_DIR = Path("/dev/fd")


def audit_lines(n: int) -> str:
    event = AuditEvent(type="decision", ts=1.0, decision=Action.ALLOW).to_dict()
    return "".join(json.dumps({**event, "seq": i, "hash": f"h{i}"}) + "\n" for i in range(n))


def dashboard_app(audit: Path) -> FastAPI:
    app = FastAPI()
    app.include_router(build_router(MetricsMemory(), audit, audit.parent / "selftest.json"))
    return app


async def abort_after_first_chunk(app: FastAPI, spec_version: str) -> None:
    """GET the CSV export like uvicorn does and hang up after the first body chunk.

    ASGI < 2.4 (uvicorn 0.54 sends 2.3): disconnect arrives via receive(). >= 2.4: send() raises.
    """
    first_chunk = anyio.Event()
    asked = False

    async def receive() -> dict[str, object]:
        nonlocal asked
        if not asked:
            asked = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await first_chunk.wait()
        return {"type": "http.disconnect"}

    async def send(message: dict[str, object]) -> None:
        if message["type"] != "http.response.body":
            return
        if first_chunk.is_set() and spec_version == "2.4":
            raise OSError("client disconnected")
        first_chunk.set()

    scope = {
        "type": "http", "asgi": {"version": "3.0", "spec_version": spec_version},
        "http_version": "1.1", "method": "GET", "scheme": "http", "root_path": "",
        "path": "/api/audit/export", "raw_path": b"/api/audit/export",
        "query_string": b"format=csv", "headers": [], "client": ("127.0.0.1", 50000),
        "server": ("127.0.0.1", 8080),
    }  # fmt: skip
    with contextlib.suppress(Exception):  # ClientDisconnect on ASGI 2.4 is expected
        await app(scope, receive, send)


@pytest.mark.skipif(not FD_DIR.is_dir(), reason="counts descriptors in /dev/fd (macOS/Linux)")
@pytest.mark.anyio
@pytest.mark.parametrize(
    "spec_version",
    ["2.3", "2.4"],
)
async def test_aborted_csv_export_closes_the_audit_file(tmp_path: Path, spec_version: str) -> None:
    audit = tmp_path / "audit.jsonl"
    audit.write_text(audit_lines(500))  # several CSV batches
    app = dashboard_app(audit)
    gc.disable()  # the file must close by itself, not whenever the cyclic GC happens to run
    try:
        await abort_after_first_chunk(app, spec_version)  # warm-up: worker threads, imports
        await anyio.sleep(0.05)  # let the loop run async-generator finalizers
        before = len(os.listdir(FD_DIR))
        for _ in range(20):
            await abort_after_first_chunk(app, spec_version)
        await anyio.sleep(0.05)
        after = len(os.listdir(FD_DIR))
    finally:
        gc.enable()
    assert after == before


@pytest.mark.parametrize(
    "tail",
    [
        '{"seq": 3, "ts": 1.0, "ty',  # crash mid-write: no newline
        '{"seq": 3, "ts": 1.0, "ty\n',  # partial write, then the next append adds "\n"
    ],
)
def test_truncated_audit_line_never_breaks_the_export(tmp_path: Path, tail: str) -> None:
    audit = tmp_path / "audit.jsonl"
    audit.write_text(audit_lines(3) + tail)
    client = TestClient(dashboard_app(audit))
    jsonl = client.get("/api/audit/export?format=jsonl")
    assert jsonl.status_code == 200
    assert jsonl.text == audit.read_text()
    response = client.get("/api/audit/export?format=csv")
    assert response.status_code == 200
    assert [row["seq"] for row in csv.DictReader(io.StringIO(response.text))][:3] == ["0", "1", "2"]


NONE_FIELDS = {f.name: None for f in dataclasses.fields(AuditEvent) if f.default is None}


@pytest.mark.anyio
@pytest.mark.parametrize("event_type", get_args(AuditEventType))
async def test_emit_accepts_every_event_type_with_none_fields(event_type: str) -> None:
    metrics = MetricsMemory()
    await metrics.emit(AuditEvent(type=event_type, ts=1.0, **NONE_FIELDS))  # type: ignore[arg-type]
    # decision set, but no agent, cost, budget, usage: the decision branch must cope
    sparse = {**NONE_FIELDS, "decision": Action.BLOCK}
    await metrics.emit(AuditEvent(type=event_type, ts=2.0, **sparse))  # type: ignore[arg-type]
    stats = metrics.stats()
    assert isinstance(stats["requests"], dict)
    assert len(metrics.events(control="pii")) == 0
    assert len(metrics.events()) == 2
