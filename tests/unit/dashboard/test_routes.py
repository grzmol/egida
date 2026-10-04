import csv
import io
import json
from collections.abc import Iterator
from pathlib import Path

import anyio
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from egida.adapters.metrics_memory import MetricsMemory
from egida.core.audit import AuditEvent, FindingSummary
from egida.core.models import Action, Category
from egida.dashboard import build_router

EVENT = AuditEvent(
    type="decision",
    ts=1.0,
    request_id="req_1",
    agent_id="demo-agent",
    model="llama3.2:3b",
    decision=Action.BLOCK,
    blocked_by="pii",
    findings=(FindingSummary("pii", Category.PII, 1.0, Action.BLOCK, (), "pesel 44*******59"),),
    cost=0.001,
    latency_ms={"total": 12.5},
)


def audit_line(seq: int) -> str:
    return json.dumps({**EVENT.to_dict(), "seq": seq, "prev_hash": "0", "hash": f"h{seq}"})


@pytest.fixture
def paths(tmp_path: Path) -> tuple[Path, Path]:
    audit = tmp_path / "audit.jsonl"
    audit.write_text("\n".join(audit_line(i) for i in range(3)) + "\n" + '{"partial": ')
    return audit, tmp_path / "selftest.json"


@pytest.fixture
def client(paths: tuple[Path, Path]) -> Iterator[TestClient]:
    metrics = MetricsMemory()
    anyio.run(metrics.emit, EVENT)
    app = FastAPI()
    app.include_router(build_router(metrics, paths[0], paths[1]))
    with TestClient(app) as test_client:
        yield test_client


def test_dashboard_page_is_html(client: TestClient) -> None:
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<table" in response.text
    assert "cdn" not in response.text.lower()  # must work offline
    assert "innerHTML" not in response.text  # file and policy data go through textContent only
    assert "setInterval" not in response.text  # a slow poll must not overlap the next one


def test_stats_include_metrics_and_selftest(client: TestClient, paths: tuple[Path, Path]) -> None:
    assert client.get("/api/stats").json()["selftest"] is None
    paths[1].write_text(json.dumps({"passed": 3, "failed": 0, "skipped": 1, "per_control": {}}))
    stats = client.get("/api/stats").json()
    assert stats["requests"]["block"] == 1
    assert stats["selftest"]["passed"] == 3
    assert "mtime" in stats["selftest"]


def test_events_filter_and_limit_validation(client: TestClient) -> None:
    assert [e["blocked_by"] for e in client.get("/api/events?decision=block").json()] == ["pii"]
    assert client.get("/api/events?decision=allow").json() == []
    assert client.get("/api/events?limit=501").status_code == 422


def test_export_jsonl_streams_the_audit_file(client: TestClient, paths: tuple[Path, Path]) -> None:
    response = client.get("/api/audit/export?format=jsonl")
    assert response.status_code == 200
    assert response.text == paths[0].read_text()


def test_export_csv_has_one_row_per_complete_line(client: TestClient) -> None:
    response = client.get("/api/audit/export?format=csv")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert len(rows) == 3  # the partial last line is skipped
    assert rows[0]["seq"] == "0"
    assert rows[0]["controls"] == "pii:block"
    assert rows[0]["latency_total_ms"] == "12.5"
    assert rows[2]["hash"] == "h2"


def test_export_errors(client: TestClient, paths: tuple[Path, Path]) -> None:
    assert client.get("/api/audit/export?format=xml").status_code == 400
    paths[0].unlink()
    response = client.get("/api/audit/export?format=csv")
    assert response.status_code == 404
    assert "audit" in response.json()["detail"]


def test_no_endpoint_returns_message_content(client: TestClient) -> None:
    for url in ("/api/stats", "/api/events", "/api/audit/export?format=csv"):
        assert "44051401359" not in client.get(url).text


def evidence_client(tmp_path: Path) -> tuple[TestClient, Path, Path]:
    redteam, evaluation = tmp_path / "summary.json", tmp_path / "eval.json"
    app = FastAPI()
    app.include_router(
        build_router(
            MetricsMemory(), tmp_path / "audit.jsonl", tmp_path / "selftest.json",
            redteam_path=redteam, eval_path=evaluation,
        )
    )  # fmt: skip
    return TestClient(app), redteam, evaluation


def test_evidence_is_null_without_files(tmp_path: Path) -> None:
    client, _, _ = evidence_client(tmp_path)
    stats = client.get("/api/stats").json()
    assert stats["redteam"] is None
    assert stats["eval"] is None


def test_evidence_is_served_with_mtime(tmp_path: Path) -> None:
    client, redteam, evaluation = evidence_client(tmp_path)
    redteam.write_text(json.dumps({"schema": "redteam.v1", "totals": {"direct_asr": 0.4}}))
    evaluation.write_text(json.dumps({"schema": "eval.v1", "files": {}}))
    stats = client.get("/api/stats").json()
    assert stats["redteam"]["totals"]["direct_asr"] == 0.4
    assert "mtime" in stats["eval"]


@pytest.mark.parametrize(
    "content",
    [
        "{broken",
        json.dumps({"schema": "other.v9"}),
        json.dumps({"schema": "eval.v1", "x": "a" * 1_100_000}),
    ],
)
def test_bad_evidence_is_an_error_not_a_500(tmp_path: Path, content: str) -> None:
    client, _, evaluation = evidence_client(tmp_path)
    evaluation.write_text(content)
    response = client.get("/api/stats")
    assert response.status_code == 200
    assert "error" in response.json()["eval"]
