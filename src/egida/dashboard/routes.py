"""Operator dashboard: static page plus JSON/CSV endpoints over audit events.

Policy state is not duplicated here: the page reads GET /api/policy (Dev A).
Endpoints have no agent key: the proxy listens on 127.0.0.1 only.
"""

import csv
import io
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse

from egida.adapters.metrics_memory import MetricsMemory

STATIC = Path(__file__).parent / "static"
CSV_COLUMNS = (
    "seq", "ts", "type", "request_id", "agent_id", "model", "decision", "blocked_by",
    "controls", "cost", "latency_total_ms", "hash",
)  # fmt: skip


CSV_BATCH = 200


def csv_row(line: bytes) -> list[object]:
    """One CSV row per JSONL line; a broken line becomes an `invalid_line` row, not an error."""
    try:
        event = json.loads(line)
        controls = ";".join(f"{x['control_id']}:{x['action']}" for x in event["findings"])
        return [
            event.get("seq"), event["ts"], event["type"], event.get("request_id"),
            event.get("agent_id"), event.get("model"), event.get("decision"),
            event.get("blocked_by"), controls, event.get("cost"),
            event.get("latency_ms", {}).get("total"), event.get("hash"),
        ]  # fmt: skip
    except (ValueError, KeyError, TypeError, AttributeError):
        return ["", "", "invalid_line", *[""] * (len(CSV_COLUMNS) - 3)]


def csv_rows(audit_path: Path) -> Iterator[str]:
    """CSV text in batches; a partially written last JSONL line (no newline) is skipped.

    The file is reopened for every batch and never open across a `yield`: an aborted download
    stops the generator without closing it, and an open file would leak until the next GC.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CSV_COLUMNS)
    offset = 0
    while True:
        with audit_path.open("rb") as f:
            f.seek(offset)
            lines = [line for line in (f.readline() for _ in range(CSV_BATCH)) if line]
            offset = f.tell()
        complete = [line for line in lines if line.endswith(b"\n")]
        writer.writerows(csv_row(line) for line in complete)
        yield buffer.getvalue()
        buffer.seek(0)
        buffer.truncate()
        if len(complete) < CSV_BATCH:
            return


def read_selftest(path: Path) -> dict[str, object] | None:
    if not path.is_file():
        return None
    try:
        report: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:  # pytest may be writing it right now
        return {"error": f"unreadable selftest report: {e}"}
    return {**report, "mtime": path.stat().st_mtime}


EVIDENCE_MAX_BYTES = 1_000_000


def read_evidence(path: Path, schema: str) -> dict[str, object] | None:
    """Offline evidence (B8) for the dashboard; a bad file is reported, never a 500."""
    if not path.is_file():
        return None
    if path.stat().st_size > EVIDENCE_MAX_BYTES:
        return {"error": f"{path.name} is larger than {EVIDENCE_MAX_BYTES} bytes"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return {"error": f"unreadable {path.name}: {e}"}
    if not isinstance(data, dict) or data.get("schema") != schema:
        return {"error": f"{path.name}: expected schema {schema}"}
    return {**data, "mtime": path.stat().st_mtime}


def build_router(
    metrics: MetricsMemory,
    audit_path: Path,
    selftest_path: Path = Path("var/selftest.json"),
    *,
    redteam_path: Path = Path("var/redteam/summary.json"),
    eval_path: Path = Path("var/eval.json"),
) -> APIRouter:
    router = APIRouter()

    @router.get("/dashboard", include_in_schema=False)
    async def dashboard() -> FileResponse:
        return FileResponse(STATIC / "index.html", media_type="text/html")

    @router.get("/api/stats")
    def stats() -> dict[str, object]:  # reads var/selftest.json: threadpool
        return {
            **metrics.stats(),
            "selftest": read_selftest(selftest_path),
            "redteam": read_evidence(redteam_path, "redteam.v1"),
            "eval": read_evidence(eval_path, "eval.v1"),
        }

    @router.get("/api/events")
    async def events(
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
        decision: Literal["allow", "redact", "block"] | None = None,
        control: str | None = None,
    ) -> list[dict[str, object]]:
        return metrics.events(limit, decision, control)

    @router.get("/api/audit/export", response_model=None)
    def export(format: str = "jsonl") -> FileResponse | StreamingResponse:
        if format not in ("jsonl", "csv"):
            raise HTTPException(400, "format must be jsonl or csv")
        if not audit_path.is_file():
            raise HTTPException(404, f"audit log not found: {audit_path}")
        if format == "jsonl":
            return FileResponse(
                audit_path, media_type="application/x-ndjson", filename="audit.jsonl"
            )
        return StreamingResponse(
            csv_rows(audit_path),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="audit.csv"'},
        )

    return router
