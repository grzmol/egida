"""Metadata checks for tests/cases/*.yaml (PLAN Z5): every control has both polarities."""

from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

CASES_DIR = Path(__file__).parents[2] / "cases"
CASE_KEYS = {
    "id", "control", "polarity", "tags", "request", "api_key", "headers", "method", "path",
    "raw_body", "fill", "model_reply", "policy_patch", "repeat", "expect",
}  # fmt: skip
EXPECT_KEYS = {
    "http_status", "decision", "control_id", "response_not_contains",
    "upstream_not_contains", "upstream_max_tokens",
}  # fmt: skip


def load_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for path in sorted(CASES_DIR.glob("*.yaml")):
        cases.extend(yaml.safe_load(path.read_text(encoding="utf-8")))
    return cases


def test_cases_are_well_formed() -> None:
    cases = load_cases()
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids)), "duplicate case id"
    for case in cases:
        assert set(case) <= CASE_KEYS, case["id"]
        assert set(case["expect"]) <= EXPECT_KEYS, case["id"]
        assert case["polarity"] in {"negative", "positive"}, case["id"]
        assert "decision" in case["expect"] or "http_status" in case["expect"], case["id"]
        if "model_reply" in case or "policy_patch" in case:
            assert "offline-only" in case.get("tags", []), case["id"]


def test_every_control_has_negative_and_positive_case() -> None:
    polarities: defaultdict[str, set[str]] = defaultdict(set)
    for case in load_cases():
        polarities[case["control"]].add(case["polarity"])
    missing = {c: p for c, p in polarities.items() if p != {"negative", "positive"}}
    assert not missing
