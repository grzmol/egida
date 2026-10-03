"""FeedFile (A5, C18): hot reload, last valid feed, rollback guard, audit events."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
import yaml

from control_layer.adapters.feed_file import FeedFile
from control_layer.core.audit import AuditEvent
from control_layer.core.errors import FeedError
from control_layer.core.ports import Clock

pytestmark = pytest.mark.anyio


class Sink:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    async def emit(self, event: AuditEvent) -> None:
        self.events.append(event)

    def types(self) -> list[str]:
        return [e.type for e in self.events]


def _rule(rid: str, word: str) -> dict[str, Any]:
    return {
        "id": rid,
        "title": f"rule {rid}",
        "status": "stable",
        "severity": "high",
        "action": "block",
        "scope": ["input"],
        "matchers": {"w": {"contains_any": [word]}},
        "condition": "any",
        "tests": {"positive": [f"has {word}"], "negative": ["benign"]},
    }


def _feed(version: str, *rules: dict[str, Any]) -> dict[str, Any]:
    return {
        "feed_version": version,
        "generated_at": "2026-10-03T20:00:00Z",
        "source": "test",
        "rules": list(rules) or [_rule("SIG-0001", "attack")],
    }


def _write(path: Path, content: dict[str, Any] | str) -> None:
    text = content if isinstance(content, str) else yaml.safe_dump(content, allow_unicode=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)  # editors save like this


@pytest.fixture
def feed_path(tmp_path: Path) -> Path:
    path = tmp_path / "feed.yaml"
    _write(path, _feed("1.0.0"))
    return path


@pytest.fixture
def sink() -> Sink:
    return Sink()


@pytest.fixture
def feed(feed_path: Path, sink: Sink, clock: Clock) -> FeedFile:
    return FeedFile.load_initial(feed_path, sink, clock)


async def test_added_rule_goes_live_with_a_diff_in_the_audit(
    feed: FeedFile, feed_path: Path, sink: Sink
) -> None:
    _write(feed_path, _feed("1.1.0", _rule("SIG-0001", "attack"), _rule("SIG-0005", "yaml")))
    assert await feed.check_once() is True
    assert feed.current().version == "1.1.0"
    (event,) = sink.events
    assert event.type == "feed_reloaded"
    assert event.feed_version == "1.1.0"
    assert "added=[SIG-0005] removed=[] changed=[]" in (event.detail or "")
    assert "(previous 1.0.0)" in (event.detail or "")


@pytest.mark.parametrize(
    "content",
    [
        "feed_version: [broken",
        "- just a list",
        {**_feed("1.1.0"), "rules": [{**_rule("SIG-0002", "x"), "severity": "extreme"}]},
        _feed(
            "1.1.0", {**_rule("SIG-0002", "x"), "tests": {"positive": ["no"], "negative": ["b"]}}
        ),
    ],
    ids=["bad-yaml", "not-a-mapping", "schema", "own-test-fails"],
)
async def test_bad_feed_is_rejected_once_and_the_old_one_stays(
    feed: FeedFile, feed_path: Path, sink: Sink, content: Any
) -> None:
    _write(feed_path, content)
    assert await feed.check_once() is False
    assert feed.current().version == "1.0.0"
    assert feed.last_error()
    assert sink.types() == ["feed_rejected"]
    assert sink.events[0].feed_version == "1.0.0"
    assert await feed.check_once() is False
    assert sink.types() == ["feed_rejected"]  # same bad file: no second event


async def test_rejection_detail_does_not_echo_rule_test_payloads(
    feed: FeedFile, feed_path: Path, sink: Sink
) -> None:
    bad = {
        **_rule("SIG-0002", "x"),
        "severity": "extreme",
        "tests": {"positive": ["PAYLOAD-123"], "negative": ["b"]},
    }
    _write(feed_path, _feed("1.1.0", bad))
    await feed.check_once()
    assert "PAYLOAD-123" not in (sink.events[0].detail or "")


async def test_version_rollback_is_rejected(feed_path: Path, sink: Sink, clock: Clock) -> None:
    _write(feed_path, _feed("1.2.0"))
    feed = FeedFile.load_initial(feed_path, sink, clock)
    _write(feed_path, _feed("1.10.0"))  # numeric, not string, comparison
    assert await feed.check_once() is True
    _write(feed_path, _feed("1.9.0", _rule("SIG-0001", "other")))
    assert await feed.check_once() is False
    assert feed.last_error() == "feed_version 1.9.0 < active 1.10.0"


async def test_same_version_with_new_content_reloads_with_a_note(
    feed: FeedFile, feed_path: Path, sink: Sink
) -> None:
    _write(feed_path, _feed("1.0.0", _rule("SIG-0001", "changed")))
    assert await feed.check_once() is True
    assert "changed=[SIG-0001]" in (sink.events[0].detail or "")
    assert (sink.events[0].detail or "").endswith("without a feed_version bump")


async def test_oversized_file_is_rejected(feed: FeedFile, feed_path: Path, sink: Sink) -> None:
    _write(feed_path, "# " + "x" * (1 << 20) + "\n" + yaml.safe_dump(_feed("1.1.0")))
    assert await feed.check_once() is False
    assert "larger than" in (feed.last_error() or "")


async def test_missing_file_is_reported_on_the_second_check(
    feed: FeedFile, feed_path: Path, sink: Sink
) -> None:
    os.unlink(feed_path)
    assert await feed.check_once() is False
    assert sink.events == []
    assert await feed.check_once() is False
    assert sink.types() == ["feed_rejected"]


@pytest.mark.parametrize("content", [None, "feed_version: [broken"], ids=["missing", "bad"])
def test_startup_without_a_valid_feed_fails(
    tmp_path: Path, clock: Clock, content: str | None
) -> None:
    path = tmp_path / "feed.yaml"
    if content is not None:
        path.write_text(content, encoding="utf-8")
    with pytest.raises(FeedError):
        FeedFile.load_initial(path, Sink(), clock)
