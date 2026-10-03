"""No orphans after shutdown (PLAN §8): background tasks and file descriptors end with the app."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from control_layer.adapters.fake_model import FakeGuardModelClient, FakeModelClient
from control_layer.app import Settings, create_app

pytestmark = pytest.mark.anyio

ROOT = Path(__file__).resolve().parents[3]


async def test_lifespan_leaves_no_tasks_or_open_files(tmp_path: Path) -> None:
    settings = Settings(
        policy_path=ROOT / "config" / "policy.yaml",
        audit_path=tmp_path / "audit.jsonl",
        policy_poll_s=0.01,
        feed_path=ROOT / "signatures" / "feed.yaml",
    )
    app = create_app(settings, model_client=FakeModelClient(), guard_client=FakeGuardModelClient())
    tasks_before = asyncio.all_tasks()
    fds_before = len(os.listdir("/dev/fd"))
    async with app.router.lifespan_context(app):
        await asyncio.sleep(0.05)  # let the policy and feed pollers run a few rounds
        assert len(asyncio.all_tasks() - tasks_before) >= 1  # pollers are running
    assert asyncio.all_tasks() - tasks_before == set()
    assert len(os.listdir("/dev/fd")) == fds_before
