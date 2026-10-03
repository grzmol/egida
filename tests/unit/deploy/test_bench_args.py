"""scripts/bench.py: argument parsing and aggregation on synthetic timings. Owner: Maciej."""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[3]


def _load_bench() -> ModuleType:
    spec = importlib.util.spec_from_file_location("bench", ROOT / "scripts" / "bench.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["bench"] = module  # dataclasses resolve annotations through sys.modules
    spec.loader.exec_module(module)
    return module


bench = _load_bench()


def nearest_rank(values: Sequence[float], q: float) -> float | None:
    """Stand-in for control_layer.adapters.telemetry.percentile (A6) with a known result."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, -(-len(ordered) * q // 100))
    return ordered[int(rank) - 1]


def _summary(samples: list[object], wall_s: float = 10.0) -> dict[str, object]:
    return bench.summarize(
        samples, wall_s, nearest_rank, target="http://t", model="m", concurrency=4
    )


def test_defaults_match_spec() -> None:
    args = bench.build_parser().parse_args([])
    assert (args.target, args.key, args.model) == (
        "http://127.0.0.1:8080",
        "sk-bench-agent",
        "llama3.2:3b",
    )
    assert (args.requests, args.concurrency, args.max_tokens, args.warmup) == (60, 4, 16, 2)
    assert args.out == Path("var/bench.json")


@pytest.mark.parametrize(
    "argv", [["--requests", "0"], ["--concurrency", "-1"], ["--warmup", "-1"], ["--requests", "x"]]
)
def test_rejects_bad_numbers(argv: list[str]) -> None:
    with pytest.raises(SystemExit):
        bench.build_parser().parse_args(argv)


def test_prompts_rotate_and_are_unique() -> None:
    prompts = [bench.prompt_for(i) for i in range(6)]
    assert len(set(prompts)) == 6  # unique, or max_identical blocks the repeats
    assert prompts[0].startswith(bench.PROMPTS[0]) and prompts[3].startswith(bench.PROMPTS[0])
    assert "44051401359" in prompts[1] and "Ignore all previous" in prompts[2]
    assert prompts[4].endswith("#4")


def test_summary_splits_by_decision_and_counts_errors() -> None:
    s = bench.Sample
    samples = [
        s(1000.0, "allow"),
        s(3000.0, "allow"),
        s(1200.0, "redact"),
        s(5.0, "block"),
        s(7.0, "block"),
        s(120000.0, None, "ReadTimeout"),
        s(3.0, None, "http_401"),
        s(4.0, None, "http_401"),
    ]
    result = _summary(samples)
    assert result["schema"] == "bench.v1"
    assert result["requests"] == 8 and result["rps"] == 0.8
    assert result["errors"] == {"total": 3, "ReadTimeout": 1, "http_401": 2}
    assert result["by_decision"] == {
        "allow": {"n": 2, "p50": 1000.0, "p95": 3000.0},
        "block": {"n": 2, "p50": 5.0, "p95": 7.0},
        "redact": {"n": 1, "p50": 1200.0, "p95": 1200.0},
    }
    # Failed requests do not distort the latency of answered ones.
    assert result["latency_ms"] == {"p50": 1000.0, "p95": 3000.0, "max": 3000.0}


def test_summary_without_successes() -> None:
    result = _summary([bench.Sample(1.0, None, "ConnectError")], wall_s=0.0)
    assert result["latency_ms"] == {"p50": None, "p95": None, "max": None}
    assert result["by_decision"] == {} and result["rps"] is None
