"""AuditSink that forwards each event to several sinks (JSONL file, metrics, telemetry)."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from egida.core.audit import AuditEvent
from egida.core.ports import AuditSink

__all__ = ["FanoutAuditSink"]

log = logging.getLogger(__name__)


class FanoutAuditSink:
    def __init__(self, sinks: Sequence[AuditSink]) -> None:
        self._sinks = tuple(sinks)

    async def emit(self, event: AuditEvent) -> None:
        """Deliver to every sink; if any fails, the others still receive it, then the first error
        is re-raised so a lost audit record is never silent."""
        first_error: Exception | None = None
        for sink in self._sinks:
            try:
                await sink.emit(event)
            except Exception as exc:  # noqa: BLE001 (isolate sinks, re-raised below)
                log.error("audit sink %s failed: %s", type(sink).__name__, exc)
                first_error = first_error or exc
        if first_error is not None:
            raise first_error
