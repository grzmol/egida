"""Hot-reloading policy file (A2, R1, C19)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import BaseModel, ConfigDict

from control_layer.adapters.policy_file import PolicyFile
from control_layer.core.audit import AuditEvent
from control_layer.core.errors import PolicyError
from control_layer.core.models import Action

pytestmark = pytest.mark.anyio


class Params(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    level: int = 1


class Sink:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    async def emit(self, event: AuditEvent) -> None:
        self.events.append(event)

    def types(self) -> list[str]:
        return [e.type for e in self.events]


def _write(path: Path, policy: dict[str, Any] | str) -> None:
    text = policy if isinstance(policy, str) else yaml.safe_dump(policy)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)  # how editors save: temp file + rename


@pytest.fixture
def policy(policy_dict: dict[str, Any]) -> dict[str, Any]:
    policy_dict["controls"] = [
        {"id": "pii", "kind": "pii", "sides": ["input"], "action": "redact", "threshold": 0.5}
    ]
    return policy_dict


@pytest.fixture
def setup(tmp_path: Path, policy: dict[str, Any], clock: Any) -> tuple[PolicyFile, Path, Sink]:
    path = tmp_path / "policy.yaml"
    _write(path, policy)
    sink = Sink()
    return PolicyFile(path, {"pii": Params}, sink, clock), path, sink


async def test_changed_action_is_applied(setup: Any, policy: dict[str, Any]) -> None:
    source, path, sink = setup
    old = source.current()
    policy["controls"][0]["action"] = "block"
    _write(path, policy)
    assert await source.check_once()
    assert source.current().policy.controls[0].action is Action.BLOCK
    assert old.policy.controls[0].action is Action.REDACT  # snapshots are immutable
    assert sink.types() == ["policy_reloaded"]
    assert "~pii (action: redact->block)" in (sink.events[0].detail or "")


async def test_unchanged_file_is_a_no_op(setup: Any) -> None:
    source, _, sink = setup
    assert not await source.check_once()
    assert sink.events == []


@pytest.mark.parametrize(
    "bad",
    [
        "version: [unclosed",
        "version: 1\nagents: {}\n",
        "{}",
        "",
        "- a\n- b\n",
    ],
    ids=["broken-yaml", "schema-error", "empty-mapping", "empty-file", "list-root"],
)
async def test_invalid_policy_is_rejected_once_and_old_stays(setup: Any, bad: str) -> None:
    source, path, sink = setup
    before = source.current()
    _write(path, bad)
    assert not await source.check_once()
    assert not await source.check_once()
    assert source.current() is before
    assert source.last_error()
    assert sink.types() == ["policy_rejected"]


async def test_unknown_kind_and_bad_params_are_rejected(setup: Any, policy: dict[str, Any]) -> None:
    source, path, sink = setup
    policy["controls"][0]["params"] = {"level": "high"}
    _write(path, policy)
    assert not await source.check_once()
    policy["controls"][0]["params"] = {}
    policy["controls"][0]["kind"] = "nope"
    _write(path, policy)
    assert not await source.check_once()
    assert sink.types() == ["policy_rejected", "policy_rejected"]


async def test_fix_after_error_reloads_and_clears_error(setup: Any, policy: dict[str, Any]) -> None:
    source, path, _ = setup
    _write(path, "garbage: [")
    await source.check_once()
    policy["controls"][0]["threshold"] = 0.9
    _write(path, policy)
    assert await source.check_once()
    assert source.last_error() is None


async def test_reverting_bad_edit_clears_error(setup: Any, policy: dict[str, Any]) -> None:
    source, path, _ = setup
    _write(path, "garbage: [")
    await source.check_once()
    _write(path, policy)
    assert not await source.check_once()
    assert source.last_error() is None


async def test_missing_file_tolerated_once_then_rejected(setup: Any) -> None:
    source, path, sink = setup
    path.unlink()
    assert not await source.check_once()
    assert sink.events == []
    assert not await source.check_once()
    assert sink.types() == ["policy_rejected"]
    assert not await source.check_once()
    assert sink.types() == ["policy_rejected"]


async def test_removed_control_is_reported(setup: Any, policy: dict[str, Any]) -> None:
    source, path, sink = setup
    policy["controls"] = []
    _write(path, policy)
    assert await source.check_once()
    assert source.current().policy.controls == ()
    assert "-pii" in (sink.events[0].detail or "")


def test_invalid_initial_policy_raises(tmp_path: Path, clock: Any) -> None:
    path = tmp_path / "policy.yaml"
    path.write_text("version: 1\n", encoding="utf-8")
    with pytest.raises(PolicyError):
        PolicyFile(path, {}, Sink(), clock)
    with pytest.raises(PolicyError):
        PolicyFile(tmp_path / "missing.yaml", {}, Sink(), clock)
