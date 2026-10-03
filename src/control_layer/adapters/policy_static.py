"""PolicySource loaded once from a file (A1). Replaced by the hot-reloading PolicyFile in A2."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path

import yaml
from pydantic import BaseModel

from control_layer.core.errors import PolicyError
from control_layer.core.policy import build_policy
from control_layer.core.ports import PolicySnapshot

__all__ = ["StaticPolicySource", "load_policy_file"]


def load_policy_file(
    path: Path, param_models: Mapping[str, type[BaseModel]], loaded_at: float
) -> PolicySnapshot:
    """Read, parse and validate a policy file. Raises PolicyError (also for I/O and YAML errors)."""
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise PolicyError([f"{path}: cannot read ({exc.strerror or exc})"]) from exc
    try:
        raw = yaml.safe_load(data)
    except yaml.YAMLError as exc:
        raise PolicyError([f"{path}: invalid YAML ({exc})"]) from exc
    policy = build_policy(raw, param_models)
    return PolicySnapshot(
        policy=policy,
        sha256=hashlib.sha256(data).hexdigest(),
        loaded_at=loaded_at,
        source=str(path),
    )


class StaticPolicySource:
    def __init__(self, snapshot: PolicySnapshot) -> None:
        self._snapshot = snapshot

    def current(self) -> PolicySnapshot:
        return self._snapshot

    def last_error(self) -> str | None:
        return None
