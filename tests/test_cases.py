"""Runs tests/cases/*.yaml offline through ASGI, or against a live instance with --target URL.

Schema: tests/cases/README.md. Results per control go to var/selftest.json (dashboard).
"""

import copy
import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml
from fastapi.testclient import TestClient

from control_layer.adapters.fake_model import FakeModelClient
from control_layer.app import Settings, create_app
from control_layer.detectors import REGISTRY

ROOT = Path(__file__).resolve().parents[1]
CASES_DIR = ROOT / "tests" / "cases"
POLICY_PATH = ROOT / "config" / "policy.yaml"
REPORT_PATH = ROOT / "var" / "selftest.json"
DEFAULT_MODEL = "llama3.2:3b"
AGENT_KEYS: dict[str, str] = json.loads(
    os.environ.get(
        "CONTROL_LAYER_TEST_KEYS",
        '{"demo-agent": "sk-demo-agent", "ci-agent": "sk-ci-agent"}',
    )
)

Case = dict[str, Any]


def load_cases() -> list[Case]:
    cases: list[Case] = []
    for path in sorted(CASES_DIR.glob("*.yaml")):
        cases.extend(yaml.safe_load(path.read_text(encoding="utf-8")))
    return cases


CASES = load_cases()


def enabled_controls() -> set[str]:
    policy = yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))
    return {c["id"] for c in policy.get("controls", []) if c.get("enabled", True)}


def merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Deep merge; `controls` (a list) is patched by id, `None` removes the control."""
    merged = copy.deepcopy(base)
    for key, value in patch.items():
        if key == "controls":
            controls = {c["id"]: c for c in merged.get("controls", [])}
            for control_id, change in value.items():
                if change is None:
                    controls.pop(control_id, None)
                else:
                    controls[control_id] = merge(controls[control_id], change)
            merged["controls"] = list(controls.values())
        elif isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def build_request(case: Case) -> dict[str, Any]:
    """httpx/TestClient keyword arguments for one case."""
    body = copy.deepcopy(case.get("request"))
    headers = dict(case.get("headers", {}))
    agent = "demo-agent"
    if body is not None:
        agent = body.pop("agent", agent)
        body.setdefault("model", DEFAULT_MODEL)
        if "fill" in case:
            body["messages"][-1]["content"] = "a" * case["fill"]
    key = case["api_key"] if "api_key" in case else (AGENT_KEYS[agent] if agent else None)
    if key is not None:
        headers["Authorization"] = f"Bearer {key}"
    kwargs: dict[str, Any] = {
        "method": case.get("method", "POST"),
        "url": case.get("path", "/v1/chat/completions"),
        "headers": headers,
    }
    if "raw_body" in case:
        kwargs["content"] = case["raw_body"]
        headers["Content-Type"] = "application/json"
    elif body is not None:
        kwargs["json"] = body
    return kwargs


def parse_response(response: httpx.Response) -> tuple[str, dict[str, Any] | None, str | None]:
    """(content, control_layer, finish_reason) for JSON or SSE chat completions."""
    if response.headers.get("content-type", "").startswith("text/event-stream"):
        content, control_layer, finish = "", None, None
        for line in response.text.splitlines():
            if not line.startswith("data: ") or line == "data: [DONE]":
                continue
            chunk = json.loads(line[len("data: ") :])
            choice = chunk["choices"][0] if chunk.get("choices") else {}
            content += choice.get("delta", {}).get("content") or ""
            finish = choice.get("finish_reason") or finish
            control_layer = chunk.get("control_layer", control_layer)
        return content, control_layer, finish
    data = response.json()
    choice = data["choices"][0] if data.get("choices") else {}
    content = (choice.get("message") or {}).get("content") or ""
    return content, data.get("control_layer"), choice.get("finish_reason")


def check(case: Case, response: httpx.Response, fake: FakeModelClient | None) -> None:
    expect = case["expect"]
    assert response.status_code == expect.get("http_status", 200), response.text[:300]
    if "decision" not in expect:
        return
    assert response.headers.get("X-Control-Decision") == expect["decision"]
    content, control_layer, finish = parse_response(response)
    if expect["decision"] == "block":
        assert finish == "content_filter"
    if "control_id" in expect:
        assert control_layer is not None, "response has no control_layer field"
        ids = {c["id"] for c in control_layer.get("controls", [])}
        assert expect["control_id"] in ids | {control_layer.get("blocked_by")}, control_layer
    for text in expect.get("response_not_contains", []):
        assert text not in content
    if fake is not None and fake.last_interaction is not None:
        sent = json.dumps([m.content for m in fake.last_interaction.messages], ensure_ascii=False)
        for text in expect.get("upstream_not_contains", []):
            assert text not in sent
        if "upstream_max_tokens" in expect:
            assert fake.last_interaction.max_tokens == expect["upstream_max_tokens"]


def run_offline(case: Case, tmp_path: Path) -> None:
    policy = yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text(yaml.safe_dump(merge(policy, case.get("policy_patch", {}))))
    fake = FakeModelClient(reply=case.get("model_reply") or "OK")
    settings = Settings(policy_path=policy_path, audit_path=tmp_path / "audit.jsonl")
    with TestClient(create_app(settings, model_client=fake)) as client:
        for _ in range(case.get("repeat", 1)):
            response = client.request(**build_request(case))
    check(case, response, fake)


def run_live(case: Case, client: httpx.Client) -> None:
    for _ in range(case.get("repeat", 1)):
        response = client.request(**build_request(case))
    check(case, response, None)


@pytest.fixture(scope="session")
def report() -> Iterator[dict[str, tuple[Case, str]]]:
    results: dict[str, tuple[Case, str]] = {}
    yield results
    per_control: dict[str, dict[str, int]] = {}
    for case, outcome in results.values():
        row = per_control.setdefault(
            case["control"], {"negative_pass": 0, "positive_pass": 0, "total": 0}
        )
        row["total"] += 1
        if outcome == "passed":
            row[f"{case['polarity']}_pass"] += 1
    outcomes = [outcome for _, outcome in results.values()]
    summary = {k: outcomes.count(k) for k in ("passed", "failed", "skipped")}
    REPORT_PATH.parent.mkdir(exist_ok=True)
    REPORT_PATH.write_text(json.dumps({**summary, "per_control": per_control}, indent=2))


@pytest.fixture(scope="session")
def live_client(pytestconfig: pytest.Config) -> Iterator[httpx.Client | None]:
    target: str | None = pytestconfig.getoption("--target")
    if target is None:
        yield None
        return
    with httpx.Client(base_url=target, timeout=60) as client:
        yield client


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_case(
    case: Case,
    tmp_path: Path,
    live_client: httpx.Client | None,
    report: dict[str, tuple[Case, str]],
    request: pytest.FixtureRequest,
) -> None:
    tags = case.get("tags", [])
    if live_client is not None and "offline-only" in tags:
        report[case["id"]] = (case, "skipped")
        pytest.skip("offline-only")
    if case["control"] in REGISTRY and case["control"] not in enabled_controls():
        report[case["id"]] = (case, "skipped")
        pytest.skip(f"control {case['control']} is not enabled in {POLICY_PATH}")
    if "needs-budget-store" in tags:  # strict: turns red once budgets work, then drop the tag
        request.applymarker(pytest.mark.xfail(reason="budget store lands in A3", strict=True))
    if "known-gap" in tags:  # strict: turns red once a detector catches it, then drop the tag
        request.applymarker(
            pytest.mark.xfail(reason="known detector gap (tests/cases/README.md)", strict=True)
        )
    outcome = "failed"
    try:
        if live_client is None:
            run_offline(case, tmp_path)
        else:
            run_live(case, live_client)
        outcome = "passed"
    finally:
        report[case["id"]] = (case, outcome)


def test_every_enabled_control_has_both_polarities() -> None:
    enabled = enabled_controls()
    covered = {(c["control"], c["polarity"]) for c in CASES}
    missing = sorted(
        f"{control}:{polarity}"
        for control in enabled
        for polarity in ("negative", "positive")
        if (control, polarity) not in covered
    )
    assert not missing
