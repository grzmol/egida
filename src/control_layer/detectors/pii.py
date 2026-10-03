"""C04: PII finder (EN/PL) with checksum validation.

Returns spans on the original text. Numbers are accepted only with a valid
checksum (PESEL, NIP, IBAN mod 97, card Luhn), so look-alike order or invoice
numbers pass.
"""

import re
from collections.abc import Callable
from typing import ClassVar, Literal

import anyio
from pydantic import BaseModel, ConfigDict, field_validator

from control_layer.core.models import Category, Finding
from control_layer.core.ports import ScanContext
from control_layer.core.texts import iter_texts
from control_layer.detectors.common import Hit, mask, span_finding
from control_layer.detectors.validators import (
    is_card,
    is_iban,
    is_nip,
    is_pesel,
    strip_separators,
)

Pattern = tuple[str, re.Pattern[str], Callable[[str], bool] | None]

# Order matters: earlier patterns win on overlapping spans (an IBAN is not also a card).
PATTERNS: tuple[Pattern, ...] = (
    (
        "iban",
        re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,3})?\b"),
        is_iban,
    ),
    (
        "iban",  # Polish NRB: IBAN without the "PL" prefix
        re.compile(r"(?<![\d-])\d{2}(?: ?\d{4}){6}(?![\d-])"),
        lambda m: is_iban("PL" + strip_separators(m)),
    ),
    (
        "card",
        re.compile(r"(?<![\d-])(?:\d[ -]?){12,18}\d(?![\d-])"),
        lambda m: is_card(strip_separators(m)),
    ),
    (
        "nip",
        re.compile(r"(?<![\d-])\d{3}[ -]?\d{3}[ -]?\d{2}[ -]?\d{2}(?![\d-])"),
        lambda m: is_nip(strip_separators(m)),
    ),
    (
        "pesel",
        re.compile(r"(?<![\d-])\d{6}[ -]?\d{5}(?![\d-])"),
        lambda m: is_pesel(strip_separators(m)),
    ),
    (
        "phone",
        re.compile(
            r"(?<![\w+])(?:\+\d{2,3}[ -]?)?\d{3}[ -]\d{3}[ -]\d{3}(?!\d)|\+\d{2,3}\d{9}(?!\d)"
        ),
        None,
    ),
    (
        "email",
        re.compile(r"(?<![\w.%+-])[\w.%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b"),
        None,
    ),
)
ENTITIES = frozenset(label for label, _, _ in PATTERNS)
TAGS = ("owasp.llm02-2025", "atlas.AML.T0057")
Entity = Literal["email", "phone", "pesel", "nip", "iban", "card"]


def find_pii(
    text: str, entities: frozenset[str] = ENTITIES, extra: tuple[Pattern, ...] = ()
) -> list[tuple[str, int, int]]:
    """(label, start, end) for each PII item of the given entity types, sorted by position."""
    hits: list[tuple[str, int, int]] = []
    taken = bytearray(len(text))
    for label, pattern, is_valid in (*PATTERNS, *extra):
        if label not in entities:
            continue
        for m in pattern.finditer(text):
            start, end = m.span()
            if (
                start < end
                and not any(taken[start:end])
                and (is_valid is None or is_valid(m.group()))
            ):
                taken[start:end] = b"\x01" * (end - start)
                hits.append((label, start, end))
    return sorted(hits, key=lambda h: h[1])


class PiiParams(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    entities: tuple[Entity, ...] = ("email", "phone", "pesel", "nip", "iban", "card")
    extra_patterns: dict[str, str] = {}  # label -> regex on the original text

    @field_validator("extra_patterns")
    @classmethod
    def _compiles(cls, patterns: dict[str, str]) -> dict[str, str]:
        for label, rx in patterns.items():
            try:
                compiled = re.compile(rx)
            except re.error as e:
                raise ValueError(f"extra_patterns.{label}: {e}") from e
            if compiled.search("") is not None:
                raise ValueError(f"extra_patterns.{label}: must not match the empty string")
            if label in ENTITIES:
                raise ValueError(f"extra_patterns.{label}: clashes with a built-in entity")
        return patterns


def _scan(control_id: str, texts: list[tuple[str, str]], params: PiiParams) -> list[Finding]:
    extra = tuple((label, re.compile(rx), None) for label, rx in params.extra_patterns.items())
    entities = frozenset(params.entities) | frozenset(params.extra_patterns)
    hits: list[Hit] = []
    evidence: list[str] = []
    for target, text in texts:
        for label, start, end in find_pii(text, entities, extra):
            hits.append((target, label, 1.0, start, end))
            evidence.append(f"{label} {mask(text[start:end])}@{target}")
    return span_finding(control_id, Category.PII, hits, TAGS, evidence)


class PiiDetector:
    kind: ClassVar[str] = "pii"
    Params: ClassVar[type[BaseModel]] = PiiParams

    async def scan(self, ctx: ScanContext) -> list[Finding]:
        if not isinstance(ctx.params, PiiParams):
            raise TypeError(f"expected PiiParams, got {type(ctx.params).__name__}")
        texts = list(iter_texts(ctx.interaction, ctx.side))
        return await anyio.to_thread.run_sync(
            _scan, ctx.control_id, texts, ctx.params, abandon_on_cancel=True
        )
