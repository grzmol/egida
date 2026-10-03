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

from control_layer.adapters.metrics_memory import MetricsMemory

STATIC = Path(__file__).parent / "static"
CSV_COLUMNS = (
    "seq", "ts", "type", "request_id", "agent_id", "model", "decision", "blocked_by",
    "controls", "cost", "latency_total_ms", "hash",
)  # fmt: skip


def csv_rows(audit_path: Path) -> Iterator[str]:
    """CSV text line by line; a partially written last JSONL line is skipped."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CSV_COLUMNS)
    with audit_path.open(encoding="utf-8") as f:
        for line in f:
            if not line.endswith("\n"):
                break
            event = json.loads(line)
            controls = ";".join(f"{x['control_id']}:{x['action']}" for x in event["findings"])
            writer.writerow(
                [
                    event.get("seq"), event["ts"], event["type"], event.get("request_id"),
                    event.get("agent_id"), event.get("model"), event.get("decision"),
                    event.get("blocked_by"), controls, event.get("cost"),
                    event.get("latency_ms", {}).get("total"), event.get("hash"),
                ]
            )  # fmt: skip
            yield buffer.getvalue()
            buffer.seek(0)
            buffer.truncate()
    yield buffer.getvalue()


def read_selftest(path: Path) -> dict[str, object] | None:
    if not path.is_file():
        return None
    try:
        report: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:  # pytest may be writing it right now
        return {"error": f"unreadable selftest report: {e}"}
    return {**report, "mtime": path.stat().st_mtime}


def build_router(
    metrics: MetricsMemory, audit_path: Path, selftest_path: Path = Path("var/selftest.json")
) -> APIRouter:
    router = APIRouter()

    @router.get("/dashboard", include_in_schema=False)
    async def dashboard() -> FileResponse:
        return FileResponse(STATIC / "index.html", media_type="text/html")

    @router.get("/api/stats")
    def stats() -> dict[str, object]:  # reads var/selftest.json: threadpool
        return {**metrics.stats(), "selftest": read_selftest(selftest_path)}

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
