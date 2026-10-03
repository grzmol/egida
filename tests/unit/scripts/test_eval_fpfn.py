"""scripts/eval_fpfn.py: input validation, outcome classification and metrics (no network)."""

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[3]


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("eval_fpfn", ROOT / "scripts" / "eval_fpfn.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ev = load_script()


def sample(i: int, label: str, text: str = "", lang: str = "en") -> dict[str, str]:
    return {"id": f"s{i}", "text": text or f"text {i}", "label": label, "lang": lang,
            "source": "own", "license": "own"}  # fmt: skip


def write_jsonl(path: Path, rows: list[object]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def test_wilson_interval() -> None:
    assert ev.wilson(0, 0) is None
    low, high = ev.wilson(5, 10)
    assert low < 0.5 < high
    assert ev.wilson(10, 10)[1] == 1.0


def test_load_samples_validates_and_deduplicates(tmp_path: Path) -> None:
    write_jsonl(tmp_path / "deepset.jsonl", [sample(1, "attack", "x"), sample(2, "attack", "x")])
    write_jsonl(tmp_path / "other.jsonl", [sample(3, "benign")])  # not one of the five files
    samples, sources = ev.load_samples(tmp_path)
    assert list(samples) == ["deepset"]
    assert sources[0]["duplicates"] == 1
    assert sources[0]["n"] == 1


@pytest.mark.parametrize(
    "row",
    [
        {**sample(1, "attack"), "extra": 1},
        {**sample(1, "attack"), "label": "maybe"},
        {**sample(1, "attack"), "text": " "},
    ],
)
def test_bad_lines_stop_before_any_request(tmp_path: Path, row: dict[str, object]) -> None:
    write_jsonl(tmp_path / "jbb.jsonl", [row])
    with pytest.raises(ev.InputError, match="jbb.jsonl:1"):
        ev.load_samples(tmp_path)


def test_outcome_does_not_count_budget_or_on_error_blocks() -> None:
    blocked = {"decision": "block", "blocked_by": "injection_heuristics", "request_id": "r1"}
    assert ev.outcome(blocked, set()) == "flagged"
    assert ev.outcome(blocked, {"r1"}) == "error:control_error"
    assert ev.outcome({**blocked, "blocked_by": "budget.requests"}, set()) == "error:budget"
    assert ev.outcome({"decision": "redact", "request_id": "r2"}, set()) == "passed"
    assert ev.outcome({"error": "http_401"}, set()) == "error:http_401"


def test_metrics_and_redact_on_benign() -> None:
    rows = [
        ("f", sample(1, "attack"), {"decision": "block"}, "flagged"),
        ("f", sample(2, "attack"), {"decision": "allow"}, "passed"),
        ("f", sample(3, "benign"), {"decision": "redact"}, "passed"),
        ("f", sample(4, "benign"), {"decision": "block"}, "flagged"),
        ("f", sample(5, "benign"), {}, "error:transport"),
    ]
    m = ev.metrics(rows)
    assert (m["tp"], m["fn"], m["fp"], m["tn"]) == (1, 1, 1, 1)
    assert (m["tpr"], m["fpr"], m["precision"]) == (0.5, 0.5, 0.5)
    assert m["redact_on_benign"] == 1
    assert m["n"] == 5  # errors stay visible in n, outside the confusion matrix


def test_threshold_table_uses_receipt_scores() -> None:
    rows = [
        ("f", sample(1, "attack"), {"scores": {"prompt_guard": 0.99}}, "flagged"),
        ("f", sample(2, "attack"), {"scores": {"prompt_guard": 0.6}}, "passed"),
        ("f", sample(3, "benign"), {"scores": {"prompt_guard": 0.1}}, "passed"),
    ]
    table = ev.threshold_table(rows)
    assert table["0.5"] == {"tpr": 1.0, "fpr": 0.0}
    assert table["0.95"] == {"tpr": 0.5, "fpr": 0.0}
    assert ev.threshold_table([("f", sample(1, "attack"), {}, "passed")]) is None
