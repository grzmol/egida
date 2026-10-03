"""PolicySource backed by a YAML file with hot reload (R1, ADR-0003).

Polls the file's sha256 every `interval_s` (survives editors that save via temp file + rename).
A new valid policy replaces the snapshot with one assignment; an invalid one is rejected, the
last valid policy stays active and the reason is exposed via `last_error()` and the audit log.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Mapping
from pathlib import Path

import anyio
import yaml
from pydantic import BaseModel

from control_layer.core.audit import AuditEvent, AuditEventType
from control_layer.core.errors import PolicyError
from control_layer.core.policy import Policy, build_policy
from control_layer.core.ports import AuditSink, Clock, PolicySnapshot

__all__ = ["PolicyFile", "parse_policy"]

log = logging.getLogger(__name__)


def parse_policy(data: bytes, param_models: Mapping[str, type[BaseModel]]) -> Policy:
    """YAML bytes → validated Policy. Raises PolicyError (YAML errors included)."""
    try:
        raw = yaml.safe_load(data)
    except yaml.YAMLError as exc:
        raise PolicyError([f"invalid YAML: {exc}"]) from exc
    return build_policy(raw, param_models)


class PolicyFile:
    def __init__(
        self,
        path: Path,
        param_models: Mapping[str, type[BaseModel]],
        audit: AuditSink,
        clock: Clock,
        interval_s: float = 1.0,
    ) -> None:
        """Loads the initial policy; raises PolicyError so an invalid start policy stops the app."""
        self._path = path
        self._param_models = param_models
        self._audit = audit
        self._clock = clock
        self._interval_s = interval_s
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise PolicyError([f"{path}: cannot read ({exc.strerror or exc})"]) from exc
        self._snapshot = self._snapshot_of(parse_policy(data, param_models), data)
        self._last_error: str | None = None
        self._rejected_sha: str | None = None
        self._missing = False

    def current(self) -> PolicySnapshot:
        return self._snapshot

    def last_error(self) -> str | None:
        return self._last_error

    async def run(self) -> None:
        while True:
            try:
                await self.check_once()
            except Exception as exc:  # noqa: BLE001 (keep hot reload alive; failure is audited)
                log.exception("policy reload check failed")
                self._last_error = f"reload check failed: {type(exc).__name__}: {exc}"
            await anyio.sleep(self._interval_s)

    async def check_once(self) -> bool:
        """Return True when a new policy became active."""
        try:
            data = await anyio.to_thread.run_sync(self._path.read_bytes)
        except FileNotFoundError:
            if not self._missing:  # editors briefly remove the file while saving
                self._missing = True
                return False
            return await self._reject(None, f"{self._path}: file not found")
        except OSError as exc:
            return await self._reject(None, f"{self._path}: cannot read ({exc.strerror or exc})")
        self._missing = False
        sha = hashlib.sha256(data).hexdigest()
        if sha == self._snapshot.sha256:  # unchanged, or a bad edit was reverted
            self._last_error = None
            self._rejected_sha = None
            return False
        if sha == self._rejected_sha:
            return False
        try:
            policy = parse_policy(data, self._param_models)
        except PolicyError as exc:
            return await self._reject(sha, "; ".join(exc.errors))
        old = self._snapshot.policy
        self._snapshot = self._snapshot_of(policy, data)
        self._last_error = None
        self._rejected_sha = None
        await self._emit("policy_reloaded", _diff(old, policy))
        return True

    async def _reject(self, sha: str | None, reason: str) -> bool:
        if sha is not None and sha == self._rejected_sha:
            return False
        already_reported = sha is None and self._last_error == reason
        self._rejected_sha = sha
        self._last_error = reason
        if not already_reported:
            await self._emit("policy_rejected", reason)
        return False

    async def _emit(self, kind: AuditEventType, detail: str) -> None:
        await self._audit.emit(
            AuditEvent(
                type=kind,
                ts=self._clock.now(),
                policy_version=self._snapshot.policy.version,
                policy_sha256=self._snapshot.sha256,
                detail=detail[:2000],
            )
        )

    def _snapshot_of(self, policy: Policy, data: bytes) -> PolicySnapshot:
        return PolicySnapshot(
            policy=policy,
            sha256=hashlib.sha256(data).hexdigest(),
            loaded_at=self._clock.now(),
            source=str(self._path),
        )


def _diff(old: Policy, new: Policy) -> str:
    before = {c.id: c for c in old.controls}
    after = {c.id: c for c in new.controls}
    parts = [f"+{cid}" for cid in after if cid not in before]
    parts += [f"-{cid}" for cid in before if cid not in after]
    for cid in sorted(after.keys() & before.keys()):
        b, a = before[cid], after[cid]
        if a != b:
            changes = [
                f"{name}: {getattr(b, name)}->{getattr(a, name)}"
                for name in ("enabled", "action", "threshold", "on_error", "timeout_ms")
                if getattr(a, name) != getattr(b, name)
            ]
            parts.append(f"~{cid} ({', '.join(changes) or 'sides/params'})")
    sections = [
        name
        for name in Policy.model_fields
        if name != "controls" and getattr(old, name) != getattr(new, name)
    ]
    text = "controls: " + (" ".join(parts) or "unchanged")
    return text + (f"; sections changed: {', '.join(sections)}" if sections else "")
