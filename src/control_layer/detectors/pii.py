"""C04: PII finder (EN/PL) with checksum validation.

Returns spans on the original text. Numbers are accepted only with a valid
checksum (PESEL, NIP, IBAN mod 97, card Luhn), so look-alike order or invoice
numbers pass.
"""

import re
from collections.abc import Callable, Iterator
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

Finder = Callable[[str], Iterator[tuple[int, int]]]
Pattern = tuple[str, Finder]
# Digit guards: no digit, and no "digit-" / "-digit", next to the number. A lone hyphen is
# fine ("PESEL-44051401359"), but the number must not be a slice of a longer one.
_NOT_AFTER, _NOT_BEFORE = r"(?<!\d)(?<!\d-)", r"(?!\d)(?!-\d)"
_DIGIT_GROUPS = re.compile(rf"{_NOT_AFTER}\d+(?:[ -]\d+)*{_NOT_BEFORE}")
_GROUP = re.compile(r"\d+")


def regex_finder(rx: str, is_valid: Callable[[str], bool] | None = None, group: int = 0) -> Finder:
    pattern = re.compile(rx)

    def find(text: str) -> Iterator[tuple[int, int]]:
        for m in pattern.finditer(text):
            if is_valid is None or is_valid(m.group(group)):
                yield m.span(group)

    return find


def card_spans(text: str) -> Iterator[tuple[int, int]]:
    """Card = a whole run of digit groups, or the run minus short leading numbers (<= 3 digits,
    space-separated) such as a quantity: "qty 2 4111 1111 1111 1111" yields only the card.
    Never a slice from the middle of a longer number (account numbers would hit Luhn by chance).
    """
    for run in _DIGIT_GROUPS.finditer(text):
        groups = [m.span() for m in _GROUP.finditer(text, run.start(), run.end())]
        if len(groups) > 7:  # a card has at most 5 groups, plus up to 2 short leading numbers
            continue
        for i in range(len(groups)):
            if i and (groups[i - 1][1] - groups[i - 1][0] > 3 or text[groups[i][0] - 1] != " "):
                break
            digits = "".join(text[s:e] for s, e in groups[i:])
            if 13 <= len(digits) <= 19 and is_card(digits):
                yield groups[i][0], groups[-1][1]
                break


# Order matters: earlier patterns win on overlapping spans (an IBAN is not also a card).
PATTERNS: tuple[Pattern, ...] = (
    ("iban", regex_finder(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,3})?\b", is_iban)),
    (
        "iban",  # Polish NRB: IBAN without the "PL" prefix
        regex_finder(
            rf"{_NOT_AFTER}\d{{2}}(?: ?\d{{4}}){{6}}{_NOT_BEFORE}",
            lambda m: is_iban("PL" + strip_separators(m)),
        ),
    ),
    ("card", card_spans),
    (
        "nip",
        regex_finder(
            rf"{_NOT_AFTER}\d{{3}}[ -]?\d{{3}}[ -]?\d{{2}}[ -]?\d{{2}}{_NOT_BEFORE}",
            lambda m: is_nip(strip_separators(m)),
        ),
    ),
    (
        "pesel",
        regex_finder(
            rf"{_NOT_AFTER}\d{{6}}[ -]?\d{{5}}{_NOT_BEFORE}",
            lambda m: is_pesel(strip_separators(m)),
        ),
    ),
    (
        "phone",
        regex_finder(
            r"(?<![\w+])(?:\+\d{2,3}[ -]?)?\d{3}[ -]\d{3}[ -]\d{3}(?!\d)|\+\d{2,3}\d{9}(?!\d)"
        ),
    ),
    (
        "phone",  # bare 9 digits only next to a phone keyword, else order numbers would match
        regex_finder(
            r"(?i)\b(?:tel|telefon\w*|phone|mobile|kom[oó]rk\w*|numer\w*|zadzwo\w*|call)\b"
            r"[^\d\n]{0,15}((?:\+\d{2,3} ?)?\d{9})(?!\d)",
            group=1,
        ),
    ),
    (
        "email",
        regex_finder(r"(?<![\w.%+-])[\w.%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b"),
    ),
)
ENTITIES = frozenset(label for label, _ in PATTERNS)
TAGS = ("owasp.llm02-2025", "atlas.AML.T0057")
Entity = Literal["email", "phone", "pesel", "nip", "iban", "card"]


def find_pii(
    text: str, entities: frozenset[str] = ENTITIES, extra: tuple[Pattern, ...] = ()
) -> list[tuple[str, int, int]]:
    """(label, start, end) for each PII item of the given entity types, sorted by position."""
    hits: list[tuple[str, int, int]] = []
    taken = bytearray(len(text))
    for label, finder in (*PATTERNS, *extra):
        if label not in entities:
            continue
        for start, end in finder(text):
            if start < end and not any(taken[start:end]):
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
    extra = tuple((label, regex_finder(rx)) for label, rx in params.extra_patterns.items())
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
