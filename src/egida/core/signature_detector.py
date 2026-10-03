"""SignatureDetector: the signature feed as an ordinary Detector (`kind: signature`, A5).

Timeout, on_error, threshold (a severity filter), action, redaction and audit come from the
pipeline unchanged. The scan runs in a worker thread that is abandoned on timeout, so a slow
regex cannot hold a request past the control's timeout_ms.
"""

from __future__ import annotations

from functools import partial
from typing import ClassVar

import anyio
from pydantic import BaseModel

from egida.core.models import Category, Finding
from egida.core.ports import ScanContext, SignatureFeed
from egida.core.signatures import (
    SEVERITY_SCORE,
    SIGNATURE_KIND,
    SignatureParams,
    scan_feed,
)
from egida.core.texts import iter_scoped_texts

__all__ = ["SignatureDetector"]

EVIDENCE_MAX = 200


class SignatureDetector:
    kind: ClassVar[str] = SIGNATURE_KIND
    Params: ClassVar[type[BaseModel]] = SignatureParams

    def __init__(self, feed: SignatureFeed) -> None:
        self._feed = feed

    async def scan(self, ctx: ScanContext) -> list[Finding]:
        params = ctx.params
        if not isinstance(params, SignatureParams):
            raise TypeError(f"expected SignatureParams, got {type(params).__name__}")
        snapshot = self._feed.current()
        items = tuple(iter_scoped_texts(ctx.interaction, ctx.side))
        hits = await anyio.to_thread.run_sync(
            partial(
                scan_feed,
                snapshot.feed,
                items,
                rule_action=params.rule_action,
                disabled=frozenset(params.disabled_rules),
            ),
            abandon_on_cancel=True,
        )
        return [
            Finding(
                control_id=ctx.control_id,
                category=Category.SIGNATURE,
                score=SEVERITY_SCORE[hit.rule.severity],
                spans=hit.spans,
                # rule id, title, scope and targets only: never the matched text
                evidence=f"{hit.rule.id}: {hit.rule.title} [{hit.scope}: {', '.join(hit.targets)}]"[
                    :EVIDENCE_MAX
                ],
                tags=(*hit.rule.tags, f"sig.{hit.rule.id}", f"feed.{snapshot.version}"),
            )
            for hit in hits
        ]
