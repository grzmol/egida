"""SignatureFeed backed by a YAML file with hot reload (A5, C18).

Same pattern as PolicyFile (sha256 polling, last valid stays). Additionally: a feed whose
feed_version is lower than the active one is rejected (rule rollback), and every rule must pass
its own tests before the feed goes live (compile_feed).
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import anyio
import yaml

from egida.core.audit import AuditEvent, AuditEventType
from egida.core.errors import FeedError
from egida.core.ports import AuditSink, Clock, FeedSnapshot
from egida.core.signatures import CompiledFeed, compile_feed

__all__ = ["MAX_FEED_BYTES", "FeedFile"]

log = logging.getLogger(__name__)

MAX_FEED_BYTES = 1 << 20


def _parse(data: bytes) -> CompiledFeed:
    if len(data) > MAX_FEED_BYTES:
        raise FeedError([f"file larger than {MAX_FEED_BYTES} bytes"])
    try:
        raw = yaml.safe_load(data)  # never yaml.load: the feed itself must not deserialize objects
    except yaml.YAMLError as exc:
        raise FeedError([f"invalid YAML: {exc}"]) from exc
    if not isinstance(raw, dict):
        raise FeedError(["root: must be a mapping"])
    return compile_feed(raw)


def _version(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("."))


class FeedFile:
    def __init__(
        self,
        path: Path,
        feed: CompiledFeed,
        data: bytes,
        audit: AuditSink,
        clock: Clock,
        interval_s: float,
    ) -> None:
        self._path = path
        self._audit = audit
        self._clock = clock
        self._interval_s = interval_s
        self._snapshot = self._snapshot_of(feed, data)
        self._last_error: str | None = None
        self._rejected_sha: str | None = None
        self._missing = False

    @classmethod
    def load_initial(
        cls, path: Path, audit: AuditSink, clock: Clock, interval_s: float = 1.0
    ) -> FeedFile:
        """Raises FeedError: starting with an empty feed would fail open."""
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise FeedError([f"{path}: cannot read ({exc.strerror or exc})"]) from exc
        return cls(path, _parse(data), data, audit, clock, interval_s)

    def current(self) -> FeedSnapshot:
        return self._snapshot

    def last_error(self) -> str | None:
        return self._last_error

    async def run(self) -> None:
        while True:
            try:
                await self.check_once()
            except Exception as exc:  # noqa: BLE001 (keep hot reload alive; failure is audited)
                log.exception("signature feed reload check failed")
                await self._reject(None, f"reload check failed: {type(exc).__name__}: {exc}")
            await anyio.sleep(self._interval_s)

    async def check_once(self) -> bool:
        """Return True when a new feed became active."""
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
            feed = _parse(data)
        except FeedError as exc:
            return await self._reject(sha, "; ".join(exc.errors))
        old = self._snapshot
        new_version = feed.document.feed_version
        if _version(new_version) < _version(old.version):
            return await self._reject(sha, f"feed_version {new_version} < active {old.version}")
        self._snapshot = self._snapshot_of(feed, data)
        self._last_error = None
        self._rejected_sha = None
        detail = (
            f"sha256={sha[:12]} rules={len(feed.rules)} {_diff(old.feed, feed)} "
            f"(previous {old.version})"
        )
        if new_version == old.version:
            detail += " without a feed_version bump"
        await self._emit("feed_reloaded", detail)
        return True

    async def _reject(self, sha: str | None, reason: str) -> bool:
        if sha is not None and sha == self._rejected_sha:
            return False
        already_reported = sha is None and self._last_error == reason
        self._rejected_sha = sha
        self._last_error = reason
        if not already_reported:
            await self._emit("feed_rejected", reason)
        return False

    async def _emit(self, kind: AuditEventType, detail: str) -> None:
        await self._audit.emit(
            AuditEvent(
                type=kind,
                ts=self._clock.now(),
                feed_version=self._snapshot.version,
                detail=detail[:2000],
            )
        )

    def _snapshot_of(self, feed: CompiledFeed, data: bytes) -> FeedSnapshot:
        return FeedSnapshot(
            feed=feed,
            version=feed.document.feed_version,
            sha256=hashlib.sha256(data).hexdigest(),
            loaded_at=self._clock.now(),
            source=str(self._path),
        )


def _diff(old: CompiledFeed, new: CompiledFeed) -> str:
    before = {r.rule.id: r.rule.model_dump() for r in old.rules}
    after = {r.rule.id: r.rule.model_dump() for r in new.rules}
    added = sorted(after.keys() - before.keys())
    removed = sorted(before.keys() - after.keys())
    changed = sorted(rid for rid in after.keys() & before.keys() if after[rid] != before[rid])
    return (
        f"added=[{', '.join(added)}] removed=[{', '.join(removed)}] changed=[{', '.join(changed)}]"
    )
