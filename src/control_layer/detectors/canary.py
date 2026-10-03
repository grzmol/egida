"""C22: system-prompt canary in the model output (prompt leak), LLM07:2025.

The pipeline injects `cl-canary-<16 hex>` into the system message just before the model call
(core/canary.py). This detector reads the token back from that system message and blocks an
output that repeats it: exactly, without the prefix, split by spaces or zero-width characters,
upper-cased, with look-alike letters, or base64-encoded. Inputs are never scanned: there the
client's own system prompt would match itself.
"""

import re
from typing import ClassVar, Final

from pydantic import BaseModel, ConfigDict

from control_layer.core.canary import CANARY_PREFIX, CANARY_RE
from control_layer.core.models import Category, Finding, Side, Span
from control_layer.core.ports import ScanContext
from control_layer.core.texts import iter_texts
from control_layer.detectors.normalize import decoded_segments, normalize

CANARY_TAGS: Final = ("owasp.llm07-2025", "atlas.AML.T0056")


class CanaryParams(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    match_bare_hex: bool = True  # the 16 hex digits alone are a leak too


class CanaryDetector:
    kind: ClassVar[str] = "canary"
    Params: ClassVar[type[BaseModel]] = CanaryParams

    async def scan(self, ctx: ScanContext) -> list[Finding]:
        params = ctx.params
        if not isinstance(params, CanaryParams):
            raise TypeError(f"expected CanaryParams, got {type(params).__name__}")
        if ctx.side is not Side.OUTPUT:
            return []  # injected after input controls; on input it would match the client itself
        tokens = {
            m.group(0)
            for message in ctx.interaction.messages
            if message.role == "system"
            for m in CANARY_RE.finditer(message.content)
        }
        if not tokens:
            return []
        spans: list[Span] = []
        how: list[str] = []
        for target, text in iter_texts(ctx.interaction, Side.OUTPUT):
            folded = "".join(normalize(text).split())
            for token in tokens:
                hex_ = token.removeprefix(CANARY_PREFIX)
                exact = [
                    Span(target, m.start(), m.end(), "canary")
                    for m in re.finditer(re.escape(token), text, re.I)
                ]
                if (
                    not exact and params.match_bare_hex
                ):  # the hex inside a full token is no 2nd leak
                    exact = [
                        Span(target, m.start(), m.end(), "canary")
                        for m in re.finditer(re.escape(hex_), text, re.I)
                    ]
                if exact:
                    spans += exact
                    how.append(f"{target} (exact)")
                elif (hex_ if params.match_bare_hex else token) in folded:
                    how.append(f"{target} (normalized)")
                elif any(hex_ in seg.casefold() for seg in decoded_segments(text)):
                    how.append(f"{target} (base64)")
        if not how:
            return []
        return [
            Finding(
                control_id=ctx.control_id,
                category=Category.EXFILTRATION,
                score=1.0,
                spans=tuple(spans),
                evidence=("system prompt canary in " + ", ".join(how))[:200],
                tags=CANARY_TAGS,
            )
        ]
