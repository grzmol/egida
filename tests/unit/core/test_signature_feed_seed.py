"""The shipped feed (signatures/feed.yaml) and the W2 demo rule pass their own tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from control_layer.core.signatures import CompiledRule, compile_feed, match_unit_text

ROOT = Path(__file__).resolve().parents[3]
FEED = ROOT / "signatures" / "feed.yaml"
DEMO = ROOT / "signatures" / "demo" / "sig-0005.yaml"


def _with_demo_rule() -> dict[str, Any]:
    """The seed feed with the W2 snippet pasted at the end of `rules`, as done live."""
    snippet = [line for line in DEMO.read_text(encoding="utf-8").splitlines() if line.strip()]
    text = FEED.read_text(encoding="utf-8").rstrip("\n") + "\n" + "\n".join(snippet) + "\n"
    raw = yaml.safe_load(text.replace("feed_version: 1.0.0", "feed_version: 1.1.0"))
    assert isinstance(raw, dict)
    return raw


SEED = compile_feed(yaml.safe_load(FEED.read_text(encoding="utf-8")))
WITH_DEMO = compile_feed(_with_demo_rule())


def test_seed_feed_has_the_expected_rules_and_leaves_sig_0005_for_the_demo() -> None:
    ids = [r.rule.id for r in SEED.rules]
    assert ids == [f"SIG-{n:04d}" for n in (1, 2, 3, 4, 6, 7, 8, 9, 10, 11)]
    assert [r.rule.id for r in WITH_DEMO.rules][-1] == "SIG-0005"


@pytest.mark.parametrize("rule", WITH_DEMO.rules, ids=lambda r: r.rule.id)
def test_every_rule_matches_its_attacks_and_spares_its_benign_examples(rule: CompiledRule) -> None:
    assert rule.rule.tests.positive and rule.rule.tests.negative
    assert all(match_unit_text(rule, text) for text in rule.rule.tests.positive)
    assert not any(match_unit_text(rule, text) for text in rule.rule.tests.negative)
