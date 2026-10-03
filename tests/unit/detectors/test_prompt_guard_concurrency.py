"""B9 audit D7: prompt_guard under control timeouts, with a fake slow ONNX session (no model)."""

import threading
import time
from pathlib import Path

import anyio
import numpy as np
import pytest

from egida.core.models import Interaction, Message, Side
from egida.core.ports import ScanContext
from egida.detectors import prompt_guard
from egida.detectors.prompt_guard import PromptGuardDetector, PromptGuardParams

INFERENCE_S, TIMEOUT_S = 0.4, 0.05


class SlowSession:
    """ONNX session stand-in: every run() takes INFERENCE_S; tracks concurrent runs."""

    def __init__(self) -> None:
        self.active = self.peak = 0
        self._changed = threading.Condition()

    def run(self, _outputs: None, feeds: dict[str, np.ndarray]) -> list[np.ndarray]:
        with self._changed:
            self.active += 1
            self.peak = max(self.peak, self.active)
        time.sleep(INFERENCE_S)
        with self._changed:
            self.active -= 1
            self._changed.notify_all()
        return [np.zeros((len(feeds["input_ids"]), 2), dtype=np.float32)]

    def wait_idle(self) -> bool:
        with self._changed:
            return self._changed.wait_for(lambda: self.active == 0, timeout=5)


class FakeTokenizer:
    class _Encoding:
        ids = [5, 6, 7]

    def token_to_id(self, token: str) -> int:
        return {"[CLS]": 1, "[SEP]": 2}[token]

    def encode(self, _text: str, add_special_tokens: bool = False) -> "_Encoding":
        return self._Encoding()


@pytest.fixture
def slow(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> tuple[PromptGuardDetector, SlowSession]:
    session = SlowSession()
    monkeypatch.setattr(prompt_guard, "load_model", lambda _root: (session, FakeTokenizer()))
    return PromptGuardDetector(tmp_path), session


def ctx(n: int) -> ScanContext:
    # One sentence per text (no sentence pass); distinct texts so the lru_cache never answers.
    message = Message(role="user", content=f"probe number {n}")
    i = Interaction(request_id=f"r{n}", agent_id="a", model="m", messages=(message,))
    return ScanContext(i, Side.INPUT, "prompt_guard", PromptGuardParams())


async def timed_out_scans(detector: PromptGuardDetector, numbers: range) -> int:
    timeouts = 0

    async def one(n: int) -> None:
        nonlocal timeouts
        try:
            with anyio.fail_after(TIMEOUT_S):
                await detector.scan(ctx(n))
        except TimeoutError:
            timeouts += 1

    async with anyio.create_task_group() as tg:
        for n in numbers:
            tg.start_soon(one, n)
    return timeouts


@pytest.mark.anyio
async def test_timeout_bounds_wait_and_frees_the_slots(
    slow: tuple[PromptGuardDetector, SlowSession],
) -> None:
    detector, session = slow
    started = time.perf_counter()
    assert await timed_out_scans(detector, range(20)) == 20
    elapsed = time.perf_counter() - started
    assert elapsed < INFERENCE_S  # bounded by the timeout, not by 20 / 2 inferences (~4 s)
    assert await anyio.to_thread.run_sync(session.wait_idle)  # abandoned threads finish
    for _ in range(prompt_guard.CONCURRENT_SCANS):  # every slot is free again
        assert detector._slots.acquire(blocking=False)


@pytest.mark.anyio
async def test_abandoned_inference_still_holds_its_slot(
    slow: tuple[PromptGuardDetector, SlowSession],
) -> None:
    detector, session = slow
    try:
        await timed_out_scans(detector, range(2))  # both threads still run for ~INFERENCE_S
        await timed_out_scans(detector, range(2, 4))  # next request's scans
        assert session.peak <= 2
    finally:
        assert await anyio.to_thread.run_sync(session.wait_idle)
