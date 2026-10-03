"""Compose policy stays in sync with config/policy.yaml. Owner: Maciej (Dev D)."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

from control_layer.app import _build_detectors
from control_layer.core.policy import build_policy
from control_layer.core.ports import DetectorDeps

ROOT = Path(__file__).resolve().parents[3]
NATIVE = ROOT / "config" / "policy.yaml"
COMPOSE = ROOT / "config" / "policy.compose.yaml"


def _load(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return raw


def _without_deploy_fields(raw: dict[str, Any]) -> dict[str, Any]:
    """Drop the only fields allowed to differ between native and Compose runs."""
    policy = copy.deepcopy(raw)
    policy.pop("upstreams", None)
    policy.get("defaults", {}).pop("timeout_ms", None)
    for control in policy.get("controls") or []:
        control.pop("timeout_ms", None)
    return policy


def test_compose_policy_loads() -> None:
    # Same param models as the running app, so control params are validated too.
    detectors = _build_detectors(DetectorDeps())
    build_policy(_load(COMPOSE), {kind: d.Params for kind, d in detectors.items()})


def test_compose_policy_matches_native_except_deploy_fields() -> None:
    assert _without_deploy_fields(_load(COMPOSE)) == _without_deploy_fields(_load(NATIVE))


def test_compose_policy_reaches_ollama_by_service_name() -> None:
    assert _load(COMPOSE)["upstreams"]["ollama"]["base_url"] == "http://ollama:11434/v1"


def test_compose_policy_has_same_upstream_names() -> None:
    assert _load(COMPOSE)["upstreams"].keys() == _load(NATIVE)["upstreams"].keys()
