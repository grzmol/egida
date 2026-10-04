"""harness_policy on copies of config/policy.yaml: agents, budget, limits, model, removal."""

from __future__ import annotations

import hashlib
import shutil
from collections.abc import Sequence
from pathlib import Path

import pytest

from egida.console.document import DocumentError, PolicyDocument
from egida.console.harness_policy import BUDGET, BUDGET_LIMITS, apply_policy, plan_policy
from egida.console.harnesses.base import Change, Endpoint, Harness, HarnessEnv
from egida.console.schema import detector_params

REPO = Path(__file__).resolve().parents[3]


class _Fake(Harness):
    protocol = "openai-chat"
    mode = "config"
    note = "fake"

    def enabled(self, env: HarnessEnv) -> bool:
        return False

    def plan(self, env: HarnessEnv, endpoint: Endpoint) -> list[Change]:
        return []

    def apply(self, env: HarnessEnv, endpoint: Endpoint) -> list[Change]:
        return []

    def remove(self, env: HarnessEnv) -> list[Change]:
        return []


class Alpha(_Fake):
    id = "alpha"
    name = "Alpha"


class Beta(_Fake):
    id = "beta"
    name = "Beta"


REGISTRY: Sequence[Harness] = (Alpha(), Beta())
KEYS = {"alpha": "sk-egida-alpha", "beta": "sk-egida-beta"}


@pytest.fixture
def doc(tmp_path: Path) -> PolicyDocument:
    target = tmp_path / "policy.yaml"
    shutil.copyfile(REPO / "config" / "policy.yaml", target)
    return PolicyDocument.open(target)


def _sha(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def test_apply_writes_agents_budget_limits_and_stays_valid(doc: PolicyDocument) -> None:
    apply_policy(doc, [REGISTRY[0]], "llama3.2:3b", KEYS, registry=REGISTRY)

    assert doc.get(("agents", "alpha")) == {
        "key_sha256": _sha("sk-egida-alpha"),
        "allowed_models": ["llama3.2:3b"],
        "allowed_tools": ["*"],
        "budget": BUDGET,
    }
    assert "# harness: Alpha, managed by egd" in doc.render()
    assert doc.get(("budgets", BUDGET)) == dict(BUDGET_LIMITS)
    assert doc.get(("limits",)) == {
        "max_input_chars": 2_000_000,
        "max_messages": 2000,
        "max_tokens": 32000,
    }
    assert "beta" not in doc.names("agents")
    assert doc.validate(detector_params()) == []
    doc.save()
    assert PolicyDocument.open(doc.path).get(("agents", "alpha", "budget")) == BUDGET


def test_new_model_goes_to_the_first_upstream_with_price_zero(doc: PolicyDocument) -> None:
    apply_policy(doc, REGISTRY, "qwen3-coder:30b", KEYS, registry=REGISTRY)

    assert doc.get(("models", "qwen3-coder:30b")) == {
        "upstream": "ollama",
        "price_in_per_1k": 0.0,
        "price_out_per_1k": 0.0,
    }
    assert doc.get(("agents", "beta", "allowed_models")) == ["qwen3-coder:30b"]
    assert doc.validate(detector_params()) == []


def test_limits_are_never_lowered_and_budget_kept(doc: PolicyDocument) -> None:
    doc.set(("limits", "max_messages"), 5000)
    doc.add_entry("budgets", BUDGET, {**BUDGET_LIMITS, "max_requests": 7})

    apply_policy(doc, [REGISTRY[0]], "llama3.2:3b", KEYS, registry=REGISTRY)

    assert doc.get(("limits", "max_messages")) == 5000
    assert doc.get(("budgets", BUDGET, "max_requests")) == 7


def test_unselected_registry_agents_are_deleted_others_kept(doc: PolicyDocument) -> None:
    apply_policy(doc, REGISTRY, "llama3.2:3b", KEYS, registry=REGISTRY)
    others = [name for name in doc.names("agents") if name not in KEYS]

    apply_policy(doc, [REGISTRY[1]], "llama3.2:3b", KEYS, registry=REGISTRY)

    assert "alpha" not in doc.names("agents")
    assert [name for name in doc.names("agents") if name not in KEYS] == others
    assert "beta" in doc.names("agents")


def test_reapply_replaces_the_key_and_keeps_one_comment(doc: PolicyDocument) -> None:
    apply_policy(doc, [REGISTRY[0]], "llama3.2:3b", KEYS, registry=REGISTRY)
    apply_policy(doc, [REGISTRY[0]], "llama3.2:3b", {"alpha": "sk-new"}, registry=REGISTRY)

    assert doc.get(("agents", "alpha", "key_sha256")) == _sha("sk-new")
    assert doc.render().count("managed by egd") == 1


def test_plan_lists_changes_without_touching_the_document(doc: PolicyDocument) -> None:
    apply_policy(doc, [REGISTRY[0]], "llama3.2:3b", KEYS, registry=REGISTRY)
    revision = doc.revision

    lines = plan_policy(doc, [REGISTRY[1]], "qwen3:8b", KEYS, registry=REGISTRY)

    assert doc.revision == revision
    assert lines == [
        "add model qwen3:8b (upstream ollama, price 0)",
        "add agent beta with a new key, model qwen3:8b, any tool",
        "remove agent alpha",
    ]


def test_missing_key_is_refused(doc: PolicyDocument) -> None:
    with pytest.raises(DocumentError, match="No API key"):
        apply_policy(doc, [REGISTRY[0]], "llama3.2:3b", {}, registry=REGISTRY)
    assert "alpha" not in doc.names("agents")
