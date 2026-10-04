"""System Clock adapter."""

from __future__ import annotations

import time

__all__ = ["SystemClock"]


class SystemClock:
    def now(self) -> float:
        return time.time()

    def monotonic(self) -> float:
        return time.monotonic()
